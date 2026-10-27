"""GR-45: componentes de edição; original deve vir da GR-43 após autorização.

Não recupera dados de hidden inputs, persiste análise ou confirma movimento.
As regras de correção e revalidação são as oficiais F-2/F-3 do backend.
"""
from copy import deepcopy
from dataclasses import dataclass

from django.core.exceptions import ValidationError

from cadastros.models import Classificacao, Status, TipoClassificacao
from .conferencia import NotaConferida, conferir_nota
from .correcoes import validar_correcoes
from .forms_conferencia import ConferenciaForm, ParcelasConferenciaFormSet


@dataclass(frozen=True)
class RevisaoFormulario:
    original: dict
    correcoes: dict
    nota: NotaConferida


def preparar_conferencia(original):
    """Preenche sem inventar vencimentos nem escolher documentos ambíguos."""
    fornecedor, faturado = original.get('fornecedor') or {}, original.get('faturado') or {}
    categoria = Classificacao.objects.filter(tipo=TipoClassificacao.DESPESA,
        status=Status.ATIVO, codigo=original.get('tipo_despesa')).first()
    documentos = [fornecedor.get(k) for k in ('cpf', 'cnpj') if fornecedor.get(k)]
    initial = {
        'fornecedor_nome': fornecedor.get('razao_social') or fornecedor.get('nome_fantasia'),
        'fornecedor_documento': documentos[0] if len(documentos) == 1 else None,
        'faturado_nome': faturado.get('nome'), 'faturado_cpf': faturado.get('cpf'),
        'faturado_cnpj': faturado.get('cnpj'), 'classificacao': categoria.pk if categoria else None,
        'numero_nota': original.get('numero_nota'), 'data_emissao': original.get('data_emissao'),
        'valor_total': original.get('valor_total'),
    }
    cpf, cnpj = faturado.get('cpf'), faturado.get('cnpj')
    if bool(cpf) != bool(cnpj):
        initial['documento_faturado'] = 'CPF' if cpf else 'CNPJ'
    parcelas = [{'data_vencimento': p.get('data_vencimento'), 'valor': p.get('valor')}
                for p in original.get('parcelas', [])]
    return ConferenciaForm(initial=initial), ParcelasConferenciaFormSet(initial=parcelas, prefix='parcelas')


def validar_conferencia(original, dados):
    """Devolve formulários e revisão; nota.problemas mantém bloqueios da F-3.

Uma revisão produzida aqui não autoriza lançamento. A futura rota deverá
validar sessão/TTL/versão otimista e chamar registrar_correcoes da GR-43.
"""
    if not isinstance(original, dict):
        raise ValidationError('Recupere a análise original do servidor.')
    permitidos = set(ConferenciaForm.base_fields) | {'csrfmiddlewaretoken'}
    for campo in dados:
        gerenciamento = campo in {f'parcelas-{k}' for k in
            ('TOTAL_FORMS', 'INITIAL_FORMS', 'MIN_NUM_FORMS', 'MAX_NUM_FORMS')}
        partes = campo.split('-')
        parcela = len(partes) == 3 and partes[0] == 'parcelas' and partes[1].isdigit() and partes[2] in {'valor', 'data_vencimento'}
        if campo not in permitidos and not gerenciamento and not parcela:
            raise ValidationError('A conferência contém campos não editáveis.', code='campo_nao_editavel')
    form = ConferenciaForm(dados)
    parcelas = ParcelasConferenciaFormSet(dados, prefix='parcelas')
    ok_form, ok_parcelas = form.is_valid(), parcelas.is_valid()
    if not ok_form or not ok_parcelas:
        return form, parcelas, None
    c = form.cleaned_data
    proposta = {
        'fornecedor.razao_social': c['fornecedor_nome'],
        'fornecedor.documento': c['fornecedor_documento'],
        'faturado.nome': c['faturado_nome'],
        'faturado.documento': c['faturado_documento_escolhido'],
        'tipo_despesa': c['classificacao'].codigo, 'valor_total': str(c['valor_total']),
        'parcelas': [{'numero': n, 'data_vencimento': p.cleaned_data['data_vencimento'].isoformat(),
                     'valor': str(p.cleaned_data['valor'])} for n, p in enumerate(parcelas.forms, 1)],
    }
    for campo, origem in (('numero_nota', 'numero_nota'), ('serie', 'serie_nota'), ('data_emissao', 'data_emissao')):
        if c.get(origem) not in (None, ''):
            proposta[campo] = c[origem].isoformat() if campo == 'data_emissao' else c[origem]
    normalizadas, invalidos = validar_correcoes(proposta)
    if invalidos:
        # O backend fornece só nomes dos campos, sem refletir o valor recebido.
        form.add_error(None, 'Há campos incompatíveis com as regras de correção do backend.')
        return form, parcelas, None
    nota = conferir_nota(original, normalizadas)
    if any(p.campo == 'parcelas' for p in nota.problemas):
        form.add_error('valor_total', 'Confira a numeração, os valores e vencimentos das parcelas.')
        return form, parcelas, None
    # A F-3 calcula as diferenças; não marcar todo formulário como corrigido.
    correcoes = {k: v for k, v in normalizadas.items() if k in nota.campos_alterados}
    return form, parcelas, RevisaoFormulario(deepcopy(original), correcoes, nota)
