"""P08/GR-48: monta solicitação explícita e delega ao serviço oficial."""
import uuid

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from documentos.analises import CHAVE_DA_SESSAO, garantir_dono
from usuarios.demo import demo_login_required
from .forms_manuais import ContaManualForm, ParcelasManuaisFormSet
from .manual import ClassificacaoManual, ContaManual, ParcelaManual, registrar_conta_manual
from .models import TipoMovimento
from .servicos import MAXIMO_DE_PARCELAS
from .views_consultas import _erros_de_banco

SAL = "financeiro.formulario-manual.v1"


def _dono(request):
    codigo = request.session.get(CHAVE_DA_SESSAO)
    if not isinstance(codigo, str) or not codigo:
        return None
    # O token não expõe o código bruto usado para autorizar as análises.
    return salted_hmac(SAL, codigo).hexdigest()


def _solicitacao_valida(request, form, tipo):
    try:
        dados = signing.loads(form.cleaned_data["solicitacao"], salt=SAL)
        return (isinstance(dados, dict) and dados["chave"] == str(form.cleaned_data["chave_idempotencia"])
            and dados["tipo"] == tipo and isinstance(dados["dono"], str)
            and _dono(request) is not None and constant_time_compare(dados["dono"], _dono(request)))
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return False


@never_cache
@demo_login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
@_erros_de_banco
def conta_manual_nova(request):
    post = request.method == "POST"
    tipo = (request.POST if post else request.GET).get("tipo", TipoMovimento.APAGAR)
    if tipo not in TipoMovimento.values:
        return render(request, "financeiro/conta_detalhe.html", {"erro": "Tipo de conta inválido."}, status=400)
    initial = None
    if not post:
        if _dono(request) is None:
            garantir_dono(request.session)
        chave = uuid.uuid4()
        initial = {"tipo": tipo, "chave_idempotencia": chave,
            "solicitacao": signing.dumps({"chave": str(chave), "tipo": tipo, "dono": _dono(request)}, salt=SAL)}
    form = ContaManualForm(request.POST if post else None, tipo=tipo, initial=initial)
    parcelas = ParcelasManuaisFormSet(request.POST if post else None, prefix="parcelas")
    status = 200
    if post:
        valida = form.is_valid()
        parcelas_validas = parcelas.is_valid()
        permitidos = set(form.fields) | {"csrfmiddlewaretoken"}
        permitidos |= {parcelas.add_prefix(c) for c in parcelas.management_form.fields}
        permitidos |= {p.add_prefix(c) for p in parcelas.forms for c in p.fields}
        if set(request.POST) - permitidos or any(len(request.POST.getlist(c)) > 1 for c in request.POST if c != "classificacoes"):
            form.add_error(None, "Pedido inválido. Recarregue o formulário e confira os campos.")
            valida = False
        if not _solicitacao_valida(request, form, tipo):
            form.add_error(None, "A solicitação não é válida nesta sessão. Abra uma nova conta pelo formulário.")
            valida = False
        if valida and parcelas_validas:
            d = form.cleaned_data
            conta = ContaManual(tipo=d["tipo"], contraparte_id=d["contraparte"].pk,
                faturado_id=d["faturado"].pk if d["faturado"] else None, valor_total=d["valor_total"],
                classificacoes=tuple(ClassificacaoManual(c.pk, principal=c.pk == d["principal"].pk) for c in d["classificacoes"]),
                parcelas=tuple(ParcelaManual(p["data_vencimento"], p["valor"]) for p in parcelas.cleaned_data if p and not p.get("DELETE")),
                chave_idempotencia=d["chave_idempotencia"])
            try:
                movimento = registrar_conta_manual(conta)
            except ValidationError as erro:
                mensagem = ("Esta solicitação já registrou outra conta. Para uma nova conta, abra um novo formulário."
                    if getattr(erro, "code", None) == "solicitacao_ja_registrada" else erro.messages)
                form.add_error(None, mensagem)
                status = 400
            except DatabaseError:
                form.add_error(None, "Não foi possível concluir agora. Reenvie esta mesma solicitação para evitar duplicidade.")
                status = 503
            else:
                return redirect("conta_detalhe", movimento_id=movimento.id)
        else:
            status = 400
    return render(request, "financeiro/conta_manual.html", {"form": form, "parcelas": parcelas,
        "tipo_rotulo": TipoMovimento(tipo).label, "maximo_parcelas": MAXIMO_DE_PARCELAS}, status=status)
