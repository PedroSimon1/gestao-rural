"""Armazenamento temporário da análise até a confirmação (GR-43, T-04/C-10).

Decisões aprovadas por Pedro Simon em 27/10/2026:

- A análise fica em AnalisePendente (PostgreSQL), no app documentos.
- Guarda o JSON final completo de montar_resultado (ContextoProjeto 17.3),
  apagado ao confirmar, cancelar ou expirar.
- Validade de 30 minutos.
- O id da análise é o analise_origem_id do movimento: confirmar duas vezes a
  mesma análise nunca cria dois movimentos (idempotência da GR-37).

A sessão (cookie assinado) guarda só um código aleatório por navegador,
criado no login (garantir_dono); a análise guarda o hash dele. Outra sessão
recebe "análise não encontrada", sem saber se a análise existe. Sessão sem
código (cookie anterior à GR-43) não cria análise: precisa de novo login.

Expirar não é apagar: depois de 30 minutos a análise não pode mais ser usada,
mas os dados só são apagados quando ela é acessada, quando qualquer análise é
criada ou quando o comando expirar_analises roda. As linhas nunca são
excluídas fisicamente; nos estados finais ficam só o estado e as datas.

confirmar_analise() não grava nada financeiro: recebe `gravar(dados,
analise_id)`, o mapeamento da GR-51 para registrar_movimento(), e o executa na
mesma transação que finaliza a análise. Se `gravar` falhar, nada é gravado e a
análise continua PENDENTE.

Correções da conferência (GR-22, F-2; T-02, T-03 e G-03 aprovadas por Pedro
Simon em 27/10/2026): registrar_correcoes() substitui o conjunto inteiro, com
controle otimista por versao_correcoes, e guarda tudo separado de `dados`.
`gravar` continua recebendo só os dados extraídos; dentro dele,
correcoes_da_confirmacao(analise_id) devolve as correções da análise que está
sendo confirmada. Na finalização as correções são apagadas e ficam só os nomes
dos campos corrigidos.
"""

import contextvars
import hashlib
import json
import secrets
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .correcoes import validar_correcoes
from .models import AnalisePendente, StatusAnalise

VALIDADE = timedelta(minutes=30)
VERSAO_DADOS = 1
CHAVE_DA_SESSAO = "analise_dono"
# Chaves do JSON final, na ordem de montar_resultado (versão 1).
CHAVES_DOS_DADOS = (
    "fornecedor", "faturado", "numero_nota", "data_emissao", "itens",
    "quantidade_parcelas", "parcelas", "valor_total", "tipo_despesa", "validacoes",
)
# Folga ampla para uma nota; impede guardar conteúdo arbitrário.
LIMITE_DOS_DADOS = 256 * 1024

MENSAGENS = {
    "dados_invalidos": "Não foi possível guardar a análise da nota.",
    "sessao_sem_codigo": "Sua sessão precisa ser renovada. Saia e entre novamente.",
    "analise_nao_encontrada": "Análise não encontrada. Envie a nota novamente.",
    "analise_expirada": "O prazo para conferir esta análise terminou. Envie a nota novamente.",
    "analise_confirmada": "Esta análise já foi confirmada.",
    "analise_cancelada": "Esta análise foi cancelada. Envie a nota novamente.",
    "correcao_invalida": "Revise os campos corrigidos: há valores inválidos.",
    "correcoes_desatualizadas": (
        "Os dados desta análise foram alterados em outra janela. Recarregue a conferência."
    ),
}
CODIGO_DO_ESTADO_FINAL = {
    StatusAnalise.CONFIRMADA: "analise_confirmada",
    StatusAnalise.CANCELADA: "analise_cancelada",
    StatusAnalise.EXPIRADA: "analise_expirada",
}


# Análise cujo `gravar` está rodando agora (correcoes_da_confirmacao).
_EM_CONFIRMACAO = contextvars.ContextVar("analise_em_confirmacao", default=None)


class AnaliseError(Exception):
    """Falha da análise pendente. `mensagem` é segura para exibir na tela.

    `campos`: nomes dos campos com problema (correcao_invalida); nunca valores.
    """

    def __init__(self, codigo, campos=()):
        self.codigo = codigo
        self.mensagem = MENSAGENS[codigo]
        self.campos = tuple(campos)
        super().__init__(self.mensagem)


def _hash(codigo):
    return hashlib.sha256(codigo.encode()).hexdigest()


def _dono(session):
    """Hash do código da sessão; None se a sessão não tem um."""
    codigo = session.get(CHAVE_DA_SESSAO)
    if not isinstance(codigo, str) or not codigo:
        return None
    return _hash(codigo)


def _copia_dos_dados(resultado):
    """Cópia JSON pura do resultado, conferida na estrutura de primeiro nível."""
    if not isinstance(resultado, dict) or set(resultado) != set(CHAVES_DOS_DADOS):
        raise AnaliseError("dados_invalidos")
    try:
        texto = json.dumps(resultado, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise AnaliseError("dados_invalidos") from None
    if len(texto.encode()) > LIMITE_DOS_DADOS:
        raise AnaliseError("dados_invalidos")
    return json.loads(texto)


def _uuid(analise_id):
    if isinstance(analise_id, UUID):
        return analise_id
    try:
        return UUID(str(analise_id))
    except ValueError:
        raise AnaliseError("analise_nao_encontrada") from None


# Estado final: sem dados nem correções (campos_corrigidos fica, T-03).
_LIMPEZA = {"dados": None, "correcoes": None}


def _finalizar(analise, status, agora):
    analise.status = status
    analise.dados = None
    analise.correcoes = None
    analise.finalizado_em = agora
    analise.save(update_fields=["status", "dados", "correcoes", "finalizado_em"])


def _travar(session, analise_id):
    """Análise PENDENTE da sessão, bloqueada até o fim da transação.

    Devolve (analise, vencida). Exige transação aberta (select_for_update).
    """
    dono = _dono(session)
    analise = None
    if dono is not None:
        analise = (
            AnalisePendente.objects.select_for_update()
            .filter(pk=_uuid(analise_id), dono_hash=dono).first()
        )
    if analise is None:
        raise AnaliseError("analise_nao_encontrada")
    if analise.status != StatusAnalise.PENDENTE:
        raise AnaliseError(CODIGO_DO_ESTADO_FINAL[analise.status])
    return analise


def _executar_se_valida(session, analise_id, acao):
    """Bloqueia a análise e roda `acao(analise, agora)` se ainda estiver no prazo.

    Vencida, a análise é marcada EXPIRADA (gravado) e AnaliseError é levantado
    depois do commit, para que a marcação não seja desfeita. durable=True: a
    chamada dentro de outra transação é recusada (RuntimeError), porque um
    rollback externo desfaria a expiração e o commit não seria desta função.
    """
    with transaction.atomic(durable=True):
        analise = _travar(session, analise_id)
        agora = timezone.now()
        if analise.vencida(agora):
            _finalizar(analise, StatusAnalise.EXPIRADA, agora)
            vencida = True
        else:
            resultado = acao(analise, agora)
            vencida = False
    if vencida:
        raise AnaliseError("analise_expirada")
    return resultado


def garantir_dono(session):
    """Dá à sessão um código novo (chamado no login, usuarios/demo.py).

    O código nasce no login, e não numa requisição longa de processamento: com
    cookie assinado, a resposta regrava a sessão inteira e poderia desfazer um
    logout feito em outra aba nesse meio tempo. Um código novo a cada login
    impede que o código de uma sessão não autenticada seja reaproveitado; não
    protege contra quem planta um cookie já autenticado.
    """
    session[CHAVE_DA_SESSAO] = secrets.token_urlsafe(32)


def criar_analise(session, resultado):
    """Guarda o JSON final e devolve a AnalisePendente criada.

    Não cria cadastros, movimentos nem parcelas. Aproveita para expirar as
    análises vencidas de qualquer sessão: uma análise abandonada não fica com
    os dados da nota no banco à espera do comando de limpeza.
    """
    dono = _dono(session)
    if dono is None:
        raise AnaliseError("sessao_sem_codigo")
    dados = _copia_dos_dados(resultado)
    agora = timezone.now()
    expirar_analises(agora)
    return AnalisePendente.objects.create(
        dono_hash=dono,
        versao_dados=VERSAO_DADOS,
        dados=dados,
        criado_em=agora,
        expira_em=agora + VALIDADE,
    )


def obter_analise(session, analise_id):
    """AnalisePendente PENDENTE e no prazo, só para a sessão dona."""
    return _executar_se_valida(session, analise_id, lambda analise, agora: analise)


def cancelar_analise(session, analise_id):
    """Cancela a análise e apaga os dados. Cancelar de novo não tem efeito."""
    try:
        _executar_se_valida(
            session, analise_id,
            lambda analise, agora: _finalizar(analise, StatusAnalise.CANCELADA, agora),
        )
    except AnaliseError as erro:
        if erro.codigo != "analise_cancelada":
            raise


def _conferir_versao(analise, versao):
    if isinstance(versao, bool) or not isinstance(versao, int):
        raise TypeError("A versão das correções deve ser um inteiro.")
    if versao != analise.versao_correcoes:
        raise AnaliseError("correcoes_desatualizadas")


def registrar_correcoes(session, analise_id, correcoes, versao):
    """Substitui as correções da análise e devolve a AnalisePendente atualizada.

    `correcoes`: dicionário completo {campo: valor} da lista fechada de
    documentos/correcoes.py ({} apaga as correções). `versao`: a
    versao_correcoes que a tela leu; diferente → correcoes_desatualizadas, sem
    gravar (outra janela já mudou). Mesmas regras de dono, prazo, estado e
    transação de obter_analise. `dados` nunca muda.
    """
    if not isinstance(correcoes, dict):
        raise AnaliseError("correcao_invalida")
    normalizadas, invalidos = validar_correcoes(correcoes)
    if invalidos:
        raise AnaliseError("correcao_invalida", campos=invalidos)
    texto = json.dumps(normalizadas, ensure_ascii=False)
    if len(texto.encode()) > LIMITE_DOS_DADOS:
        raise AnaliseError("correcao_invalida")

    def registrar(analise, agora):
        _conferir_versao(analise, versao)
        analise.correcoes = normalizadas or None
        analise.campos_corrigidos = sorted(normalizadas)
        analise.versao_correcoes += 1
        analise.save(update_fields=["correcoes", "campos_corrigidos", "versao_correcoes"])
        return analise

    return _executar_se_valida(session, analise_id, registrar)


def correcoes_da_confirmacao(analise_id):
    """Cópia das correções da análise que está sendo confirmada ({} sem correção).

    Só funciona dentro do `gravar` de confirmar_analise() para essa mesma
    análise (RuntimeError fora dele): a autorização e o bloqueio já foram
    feitos pela confirmação.
    """
    analise = _EM_CONFIRMACAO.get()
    if analise is None or analise.id != _uuid(analise_id):
        raise RuntimeError("correcoes_da_confirmacao() só vale dentro do gravar da confirmação.")
    return json.loads(json.dumps(analise.correcoes or {}))


def confirmar_analise(session, analise_id, gravar, *, versao_correcoes=None):
    """Executa `gravar(dados, analise_id)` e marca a análise CONFIRMADA, na
    mesma transação. Devolve o que `gravar` devolver.

    A linha fica bloqueada durante a gravação: uma segunda confirmação
    concorrente espera e depois recebe "analise_confirmada". Qualquer exceção
    de `gravar` desfaz tudo e a análise continua PENDENTE.

    `versao_correcoes` (opcional): a versão das correções que o usuário
    conferiu; diferente → correcoes_desatualizadas, sem chamar `gravar`.
    """
    def confirmar(analise, agora):
        if versao_correcoes is not None:
            _conferir_versao(analise, versao_correcoes)
        token = _EM_CONFIRMACAO.set(analise)
        try:
            resultado = gravar(analise.dados, analise.id)
        finally:
            _EM_CONFIRMACAO.reset(token)
        _finalizar(analise, StatusAnalise.CONFIRMADA, timezone.now())
        return resultado

    return _executar_se_valida(session, analise_id, confirmar)


def descartar_analises(session):
    """Cancela as análises pendentes da sessão e apaga os dados (para o logout).

    Um cookie antigo reenviado depois do logout encontra só análises
    canceladas, sem dados. Devolve quantas foram canceladas.
    """
    dono = _dono(session)
    if dono is None:
        return 0
    agora = timezone.now()
    return AnalisePendente.objects.filter(
        dono_hash=dono, status=StatusAnalise.PENDENTE
    ).update(status=StatusAnalise.CANCELADA, finalizado_em=agora, **_LIMPEZA)


def expirar_analises(agora=None):
    """Marca EXPIRADA as análises pendentes vencidas e apaga os dados.

    Devolve quantas foram expiradas. Uma confirmação em andamento mantém a
    linha bloqueada; o UPDATE espera por ela e, se ela confirmar, a linha já
    não é PENDENTE e fica como está.
    """
    agora = agora or timezone.now()
    return AnalisePendente.objects.filter(
        status=StatusAnalise.PENDENTE, expira_em__lte=agora
    ).update(status=StatusAnalise.EXPIRADA, finalizado_em=agora, **_LIMPEZA)
