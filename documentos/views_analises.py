"""Fluxo de conferência GR-45/43: apenas análise e correções, sem lançamento."""
import json
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods, require_POST

from usuarios.demo import demo_login_required
from cadastros.models import TipoClassificacao
from .analises import CHAVE_DA_SESSAO, AnaliseError, criar_analise, obter_analise, registrar_correcoes, cancelar_analise
from .conferencia import conferir_nota
from .forms import DocumentoUploadForm
from .forms_classificacao_nota import ClassificacaoNaNotaForm
from .interface_conferencia import preparar_conferencia, validar_conferencia
from .processamento import ProcessamentoError, processar_pdf
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
    codigo = request.session.get(CHAVE_DA_SESSAO)
    if not isinstance(codigo, str) or not codigo:
        return _erro_analise(request, AnaliseError('sessao_sem_codigo'))
    form = DocumentoUploadForm(request.POST, request.FILES,
        upload_interrompido=getattr(request, "pdf_upload_interrompido", False))
    contexto = {'form': form, 'limite_upload_mb': settings.MAX_PDF_UPLOAD_SIZE_MB}
    if not form.is_valid():
        return render(request, 'documentos/inicio.html', contexto, status=400)
    try:
        gemini_api_key = form.cleaned_data['gemini_api_key']
        arquivo = form.cleaned_data['arquivo']
        processamento = processar_pdf(arquivo.read(), gemini_api_key, versao_dados=2)
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
        return _falha(request, 'Não foi possível guardar a análise agora. Tente novamente.', 503)
    return redirect('analise_conferencia', analise_id=analise.id)


@sensitive_post_parameters()
@demo_login_required
@require_http_methods(['GET', 'POST'])
def analise_conferencia(request, analise_id):
    try:
        analise = obter_analise(request.session, analise_id)
        erro_tela, salvo, status = None, False, 200
        cadastro_criado = None
        nova_classificacao = ClassificacaoNaNotaForm(prefix='nova', use_required_attribute=False,
            initial={'tipo': TipoClassificacao.DESPESA,
                     'codigo': (analise.correcoes or {}).get('tipo_despesa', analise.dados.get('tipo_despesa'))})
        versao_tela = analise.versao_correcoes
        if request.method == 'POST':
            if any(len(request.POST.getlist(c)) > 1 for c in request.POST):
                return _falha(request, 'A conferência contém campos repetidos.', 400)
            dados = request.POST.copy()
            acao = dados.get('acao', 'salvar')
            dados.pop('acao', None)
            if acao not in {'salvar', 'criar_classificacao'}:
                return _falha(request, 'Ação de conferência inválida.', 400)
            for campo in nova_classificacao.fields:
                dados.pop(nova_classificacao.add_prefix(campo), None)
            versao_tela = dados.get('versao_correcoes', '')
            dados.pop('versao_correcoes', None)
            if not isinstance(versao_tela, str) or not versao_tela.isascii() or not versao_tela.isdecimal() or len(versao_tela) > 10:
                return _falha(request, 'Recarregue a conferência antes de salvar.', 400)
            try:
                form, parcelas, revisao = validar_conferencia(analise.dados, dados, analise.correcoes)
            except ValidationError:
                return _falha(request, 'A conferência contém campos não autorizados.', 400)
            if acao == 'criar_classificacao':
                if int(versao_tela) != analise.versao_correcoes:
                    return _falha(request, 'Recarregue a conferência: outra aba alterou as correções.', 409)
                nova_classificacao = ClassificacaoNaNotaForm(request.POST, prefix='nova', use_required_attribute=False)
                if nova_classificacao.is_valid():
                    try:
                        # Cadastro administrativo independente, como na GR-47.
                        # Não altera análise/correções nem inicia lançamento.
                        with transaction.atomic():
                            classificacao = nova_classificacao.save()
                    except IntegrityError:
                        nova_classificacao.add_error(None, 'Já existe uma classificação com este tipo e código. Atualize a consulta; não foi criado outro cadastro.')
                        status = 409
                    except ValidationError as erro:
                        nova_classificacao.add_error(None, erro.messages)
                        status = 400
                    else:
                        cadastro_criado = classificacao
                        # Mantém todo o rascunho enviado, sem salvá-lo implicitamente.
                        dados['classificacao'] = str(classificacao.pk)
                        form, parcelas, revisao = validar_conferencia(analise.dados, dados, analise.correcoes)
                        nova_classificacao = ClassificacaoNaNotaForm(prefix='nova', use_required_attribute=False,
                            initial={'tipo': TipoClassificacao.DESPESA})
                else:
                    status = 400
            elif revisao is not None:
                try:
                    registrar_correcoes(request.session, analise.id, revisao.correcoes, int(versao_tela))
                except AnaliseError as erro:
                    # Conserva a versão enviada: não habilitar sobrescrita silenciosa de outra aba.
                    erro_tela, status = erro.mensagem, 409
                else:
                    return redirect('analise_conferencia_salva', analise_id=analise.id)
            else:
                status = 400
        else:
            form, parcelas = preparar_conferencia(analise.dados, analise.correcoes)
            revisao = SimpleNamespace(nota=conferir_nota(analise.dados, analise.correcoes))
            salvo = request.resolver_match.url_name == 'analise_conferencia_salva'
        nota = revisao.nota if revisao is not None else conferir_nota(analise.dados, analise.correcoes)
        consultas = SimpleNamespace(fornecedor=nota.fornecedor.consulta,
            faturado=nota.faturado.consulta, classificacao=nota.classificacao)
        from .views_confirmacao import pendencias_da_nota
        return render(request, 'documentos/conferencia.html', {
            'form': form, 'parcelas': parcelas, 'revisao': SimpleNamespace(nota=nota),
            'json_original': json.dumps(analise.dados, ensure_ascii=False, indent=2),
            'analise_id': analise.id, 'versao_correcoes': versao_tela,
            'expira_em': analise.expira_em, 'erro_tela': erro_tela,
            'correcoes_salvas': salvo, 'consultas': _linhas_consultas(consultas),
            'pendencias': pendencias_da_nota(nota),
            'nova_classificacao': nova_classificacao, 'cadastro_criado': cadastro_criado,
        }, status=status)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, 'Não foi possível acessar a análise agora. Tente novamente.', 503)


@sensitive_post_parameters()
@demo_login_required
@require_POST
def analise_cancelar(request, analise_id):
    try:
        cancelar_analise(request.session, analise_id)
    except AnaliseError as erro:
        return _erro_analise(request, erro)
    except DatabaseError:
        return _falha(request, 'Não foi possível cancelar a análise agora. Tente novamente.', 503)
    return _falha(request, 'Análise cancelada. Os dados da nota foram apagados.', 200)
