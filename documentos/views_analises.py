"""Fluxo de conferência GR-45/43: apenas análise e correções, sem lançamento."""
import json
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, Error as DBError, IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import content_disposition_header
from django.utils.text import slugify
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from config.erros_banco import mensagem_de_banco, verificar_banco
from usuarios.demo import demo_login_required
from cadastros.models import TipoClassificacao
from .categorias import categorias_de_despesa
from .analises import (
    AnaliseError, criar_analise, obter_analise, registrar_correcoes, cancelar_analise,
)
from comum.sessao import codigo_do_dono
from .conferencia import conferir_nota
from .forms import DocumentoUploadForm
from .forms_classificacao_nota import ClassificacaoNaNotaForm
from .interface_conferencia import preparar_conferencia, validar_conferencia
from .processamento import ProcessamentoError, processar_pdf
from .pendencias_conferencia import resumir_pendencias
from .resumo_nota import ficha_da_nota
from .views import SUGESTOES_ERRO, SUGESTAO_ERRO_PADRAO, _linhas_consultas


def _falha(request, mensagem, status):
    return render(request, 'documentos/analise_mensagem.html', {'mensagem': mensagem}, status=status)


def _erro_analise(request, erro):
    status = 404 if erro.codigo == 'analise_nao_encontrada' else 409
    return _falha(request, erro.mensagem, status)


@sensitive_post_parameters()
@demo_login_required
@require_POST
@sensitive_variables('gemini_api_key', 'processamento')
def analise_criar(request):
    if codigo_do_dono(request.session) is None:
        return _erro_analise(request, AnaliseError('sessao_sem_codigo'))
    form = DocumentoUploadForm(request.POST, request.FILES,
        upload_interrompido=getattr(request, "pdf_upload_interrompido", False))
    contexto = {'form': form, 'limite_upload_mb': settings.MAX_PDF_UPLOAD_SIZE_MB}
    if not form.is_valid():
        return render(request, 'documentos/inicio.html', contexto, status=400)
    # O resultado só vale se puder ser guardado: sem banco, nada de Gemini nem de gasto da chave.
    # As categorias de despesa (classificações ativas) também vêm do banco e são lidas antes.
    try:
        verificar_banco()
        categorias = categorias_de_despesa()
    except DBError:
        return _falha(
            request,
            'O banco de dados está indisponível no momento. A nota não foi enviada ao Gemini; tente novamente em instantes.',
            503,
        )
    try:
        gemini_api_key = form.cleaned_data['gemini_api_key']
        arquivo = form.cleaned_data['arquivo']
        contexto['nome_arquivo'] = arquivo.name
        processamento = processar_pdf(arquivo.read(), gemini_api_key, versao_dados=2, categorias=categorias)
        analise = criar_analise(request.session, processamento.resultado)
    except ProcessamentoError as erro:
        contexto.update(form=DocumentoUploadForm(), erro={
            'mensagem': erro.mensagem,
            'sugestao': SUGESTOES_ERRO.get(erro.codigo, SUGESTAO_ERRO_PADRAO),
        })
        return render(request, 'documentos/inicio.html', contexto, status=400)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, mensagem_de_banco('guardar a análise'), 503)
    return redirect('analise_conferencia', analise_id=analise.id)


class _EnvioRecusado(Exception):
    """POST da conferência recusado antes de qualquer gravação; vira uma página de mensagem."""

    def __init__(self, mensagem, status):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def _formulario_nova_classificacao(analise):
    return ClassificacaoNaNotaForm(prefix='nova', use_required_attribute=False,
        initial={'tipo': TipoClassificacao.DESPESA,
                 'codigo': (analise.correcoes or {}).get('tipo_despesa', analise.dados.get('tipo_despesa'))})


def _ler_envio(request, nova_classificacao):
    """(ação, dados da conferência, versão lida na tela) do POST; _EnvioRecusado se a forma é inválida."""
    if any(len(request.POST.getlist(c)) > 1 for c in request.POST):
        raise _EnvioRecusado('A conferência contém campos repetidos.', 400)
    dados = request.POST.copy()
    acao = dados.get('acao', 'salvar')
    dados.pop('acao', None)
    if acao not in {'salvar', 'criar_classificacao'}:
        raise _EnvioRecusado('Ação de conferência inválida.', 400)
    for campo in nova_classificacao.fields:
        dados.pop(nova_classificacao.add_prefix(campo), None)
    versao_tela = dados.get('versao_correcoes', '')
    dados.pop('versao_correcoes', None)
    if not isinstance(versao_tela, str) or not versao_tela.isascii() or not versao_tela.isdecimal() or len(versao_tela) > 10:
        raise _EnvioRecusado('Recarregue a conferência antes de salvar.', 400)
    return acao, dados, versao_tela


def _criar_classificacao(request, analise, dados, versao_tela, validacao):
    """Cadastra a classificação enviada na conferência, sem salvar o rascunho.

    Devolve (formulário da classificação, cadastro criado ou None, status, validação da conferência).
    Cadastro administrativo independente, como na GR-47: não altera análise/correções nem inicia lançamento.
    """
    if int(versao_tela) != analise.versao_correcoes:
        raise _EnvioRecusado('Recarregue a conferência: outra aba alterou as correções.', 409)
    nova = ClassificacaoNaNotaForm(request.POST, prefix='nova', use_required_attribute=False)
    if not nova.is_valid():
        return nova, None, 400, validacao
    try:
        with transaction.atomic():
            classificacao = nova.save()
    except IntegrityError:
        nova.add_error(None, 'Já existe uma classificação com este tipo e código. Atualize a consulta; não foi criado outro cadastro.')
        return nova, None, 409, validacao
    except ValidationError as erro:
        nova.add_error(None, erro.messages)
        return nova, None, 400, validacao
    # Mantém todo o rascunho enviado, sem salvá-lo implicitamente.
    dados['classificacao'] = str(classificacao.pk)
    validacao = validar_conferencia(analise.dados, dados, analise.correcoes)
    vazio = ClassificacaoNaNotaForm(prefix='nova', use_required_attribute=False,
        initial={'tipo': TipoClassificacao.DESPESA})
    return vazio, classificacao, 200, validacao


def _conferencia(request, analise):
    erro_tela, salvo, status, cadastro_criado = None, False, 200, None
    nova_classificacao = _formulario_nova_classificacao(analise)
    versao_tela = analise.versao_correcoes
    if request.method == 'POST':
        acao, dados, versao_tela = _ler_envio(request, nova_classificacao)
        try:
            validacao = validar_conferencia(analise.dados, dados, analise.correcoes)
        except ValidationError:
            raise _EnvioRecusado('A conferência contém campos não autorizados.', 400) from None
        if acao == 'criar_classificacao':
            nova_classificacao, cadastro_criado, status, validacao = _criar_classificacao(
                request, analise, dados, versao_tela, validacao)
        elif validacao[2] is not None:
            try:
                registrar_correcoes(request.session, analise.id, validacao[2].correcoes, int(versao_tela))
            except AnaliseError as erro:
                # Conserva a versão enviada: não habilitar sobrescrita silenciosa de outra aba.
                erro_tela, status = erro.mensagem, 409
            else:
                return redirect('analise_conferencia_salva', analise_id=analise.id)
        else:
            status = 400
        form, parcelas, revisao = validacao
    else:
        form, parcelas = preparar_conferencia(analise.dados, analise.correcoes)
        revisao = SimpleNamespace(nota=conferir_nota(analise.dados, analise.correcoes))
        salvo = request.resolver_match.url_name == 'analise_conferencia_salva'
    nota = revisao.nota if revisao is not None else conferir_nota(analise.dados, analise.correcoes)
    consultas = SimpleNamespace(fornecedor=nota.fornecedor.consulta,
        faturado=nota.faturado.consulta, classificacao=nota.classificacao)
    return render(request, 'documentos/conferencia.html', {
        'form': form, 'parcelas': parcelas, 'revisao': SimpleNamespace(nota=nota),
        'json_original': json.dumps(analise.dados, ensure_ascii=False, indent=2),
        'analise_id': analise.id, 'versao_correcoes': versao_tela,
        'expira_em': analise.expira_em, 'erro_tela': erro_tela,
        'correcoes_salvas': salvo, 'consultas': _linhas_consultas(consultas),
        'pendencias': resumir_pendencias(nota, form, parcelas), 'ficha': ficha_da_nota(nota),
        'nova_classificacao': nova_classificacao, 'cadastro_criado': cadastro_criado,
    }, status=status)


@sensitive_post_parameters()
@demo_login_required
@require_http_methods(['GET', 'POST'])
def analise_conferencia(request, analise_id):
    try:
        return _conferencia(request, obter_analise(request.session, analise_id))
    except _EnvioRecusado as erro:
        return _falha(request, erro.mensagem, erro.status)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, mensagem_de_banco('acessar a análise'), 503)


@sensitive_post_parameters()
@demo_login_required
@require_POST
def analise_cancelar(request, analise_id):
    try:
        cancelar_analise(request.session, analise_id)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, mensagem_de_banco('cancelar a análise'), 503)
    return _falha(request, 'Análise cancelada. Os dados da nota foram apagados.', 200)


def _nome_do_arquivo_json(analise):
    """Nome que identifica a nota: número, fornecedor e emissão (ou o início do id)."""
    dados = analise.dados
    fornecedor = dados.get('fornecedor') or {}
    origem = (dados.get('numero_nota'), fornecedor.get('razao_social') or fornecedor.get('nome_fantasia'),
              dados.get('data_emissao'))
    partes = [slugify(str(valor))[:40] for valor in origem if valor]
    partes = [parte for parte in partes if parte] or [str(analise.id)[:8]]
    return '_'.join(['nota-fiscal', *partes, 'dados-extraidos']) + '.json'


@demo_login_required
@require_GET
def analise_json(request, analise_id):
    """Baixa os dados extraídos originalmente (os mesmos mostrados na conferência), só para a sessão dona."""
    try:
        analise = obter_analise(request.session, analise_id)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, mensagem_de_banco('acessar a análise'), 503)
    resposta = HttpResponse(json.dumps(analise.dados, ensure_ascii=False, indent=2))
    resposta['Content-Type'] = 'application/json; charset=utf-8'
    resposta['Content-Disposition'] = content_disposition_header(True, _nome_do_arquivo_json(analise))
    return resposta
