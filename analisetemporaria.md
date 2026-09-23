# GR-9 — [AGENTS] Configurar cliente compartilhado do Gemini

> Registro completo da implementação da GR-9: o que foi feito, onde cada código fica, como o fluxo funciona e o código final.
> Substitui a análise prévia da GR-9 (as decisões dela foram aprovadas e aplicadas; ver seção 3).
> **Última atualização:** após integrar a `main` remota com a GR-8 (merge PR #8, `4b4a5f6`) e validar o cliente contra a API real do Gemini.
> Nenhum valor real de chave, modelo ou outro segredo aparece neste relatório.

---

## 1. Situação atual

| Item                           | Estado                                                                                                                                     |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Branch                         | `feature/GR-9-gemini-client`                                                                                                               |
| Base atual                     | `4b4a5f6` — _Merge pull request #8 from PedroSimon1/feature/GR-8-validacao-pdf_ (GR-8 já integrada; branch atualizada com a `main` remota) |
| Commit / push / PR da GR-9     | **Não realizados** (aguardando revisão)                                                                                                    |
| Stash de segurança             | `stash@{0}: On feature/GR-9-gemini-client: WIP GR-9 antes de atualizar com GR-8` (**mantido**, não apagar)                                 |
| Dependências novas             | Nenhuma (`google-genai==2.24.0` já estava no `requirements.txt`)                                                                           |
| Migrations                     | Nenhuma (nenhum model alterado)                                                                                                            |
| `python manage.py check`       | OK                                                                                                                                         |
| `python manage.py test agents` | **27 testes — OK** (não usa banco)                                                                                                         |
| `python manage.py test`        | **55 testes — OK** (28 do projeto, incluindo GR-8, + 27 da GR-9)                                                                           |
| `git diff --check`             | OK                                                                                                                                         |
| Teste manual com API real      | **OK** — `gerar_conteudo` e `gerar_json` (ver seção 7.2)                                                                                   |

### Atualização da branch com a GR-8

1. As alterações da GR-9 (ainda sem commit) foram guardadas em stash:
   `stash@{0}: WIP GR-9 antes de atualizar com GR-8`.
2. A branch `feature/GR-9-gemini-client` foi atualizada com a `main` remota, que já continha o merge da GR-8
   (`6158c2b feat(documentos): validar arquivos PDF GR-8` → `4b4a5f6 Merge pull request #8`).
3. O stash foi reaplicado. Houve conflito **somente** em:
   - `.env.example`
   - `config/settings.py`
4. Os dois conflitos foram resolvidos **preservando GR-8 + GR-9** (nenhuma configuração de nenhuma das tarefas foi perdida).
5. `agents/gemini_client.py` e `agents/test_gemini_client.py` não tiveram conflito e estão idênticos à versão guardada no stash.
6. O stash **continua existindo** como cópia de segurança até a GR-9 ser commitada.

O que a GR-8 trouxe para os arquivos compartilhados:

- `.env.example`: `MAX_PDF_UPLOAD_SIZE_MB=10`
- `config/settings.py`: `MAX_PDF_UPLOAD_SIZE_MB` e `MAX_PDF_UPLOAD_SIZE`

### Arquivos da GR-9

| Arquivo                        | Tipo                                       | Onde pertence / papel                                                                                                                                                             |
| ------------------------------ | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agents/gemini_client.py`      | **novo**                                   | Camada compartilhada do pacote `agents`. Única parte do projeto que conversa com o SDK `google-genai`. Será usada pelo Agent Extrator (GR-10) e pelo Agent Classificador (GR-11). |
| `agents/test_gemini_client.py` | **novo**                                   | Testes unitários do cliente (segue o padrão `documentos/test_upload.py`). Descoberto automaticamente pelo `manage.py test`.                                                       |
| `config/settings.py`           | alterado (+8 linhas sobre a base com GR-8) | Fonte única de configuração: bloco "Gemini" logo após o bloco da GR-8, lendo as 4 variáveis `GEMINI_*` do ambiente (já carregado pelo `load_dotenv()`).                           |
| `.env.example`                 | alterado                                   | Documenta as variáveis `GEMINI_*`, depois de `MAX_PDF_UPLOAD_SIZE_MB` (GR-8).                                                                                                     |
| `.gitignore`                   | alterado (decisão manual do Pedro Simon)   | Remoção da regra que ignorava `analisetemporaria.md` — ver abaixo.                                                                                                                |

### Arquivos NÃO alterados pela GR-9

`requirements.txt`, `agents/extrator/agent.py`, `agents/classificador/agent.py`, `agents/__init__.py`, models, migrations, `documentos/`, `financeiro/`, `usuarios/`.

### `.gitignore` e versionamento deste relatório

A remoção das linhas abaixo do `.gitignore` foi uma **decisão manual do Pedro Simon**, porque ele quer que
`analisetemporaria.md` seja **versionado no GitHub**:

```
# Análises temporárias
analisetemporaria.md
```

Não há mais decisão pendente sobre isso. A regra `.env` continua no `.gitignore`.

### `.env` real (local)

- Contém `GEMINI_API_KEY` e `GEMINI_MODEL` preenchidos (necessários para o teste manual da seção 7.2).
- Continua **ignorado pelo Git** (`git check-ignore -v .env` → `.gitignore:12:.env`) e não está rastreado (`git ls-files .env` vazio).
- **Nunca deve ser versionado.**
- Seus valores reais **não** aparecem neste relatório nem devem aparecer em nenhum arquivo versionado, log ou mensagem.

---

## 2. Estrutura de pastas resultante

```
gestao-rural/
├── .env.example                  ← GR-8: MAX_PDF_UPLOAD_SIZE_MB | GR-9: GEMINI_* (4 variáveis)
├── config/
│   └── settings.py               ← GR-8: MAX_PDF_UPLOAD_SIZE_MB/_SIZE | GR-9: bloco "Gemini" (4 settings)
└── agents/
    ├── __init__.py               (vazio, inalterado)
    ├── gemini_client.py          ← NOVO: exceções + GeminiClient
    ├── test_gemini_client.py     ← NOVO: 27 testes
    ├── extrator/
    │   ├── __init__.py           (vazio, inalterado)
    │   └── agent.py              (vazio — GR-10 usará GeminiClient)
    └── classificador/
        ├── __init__.py           (vazio, inalterado)
        └── agent.py              (vazio — GR-11 usará GeminiClient)
```

Direção das dependências (em um sentido só):

```
agents/extrator/agent.py ─┐
                          ├──► agents/gemini_client.py ──► google-genai (SDK) ──► API Gemini
agents/classificador/agent.py ┘            │
                                           └──► django.conf.settings ◄── config/settings.py ◄── .env / ambiente
```

O cliente não conhece `documentos`, `financeiro`, prompts nem schemas de negócio — isso fica nos agents (GR-10/GR-11).

---

## 3. Decisões aplicadas

1. Cliente em `agents/gemini_client.py`; testes em `agents/test_gemini_client.py`.
2. Configuração lida de `django.conf.settings`, com parâmetros explícitos no construtor sobrescrevendo settings (facilita testes/injeção).
3. Variáveis: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SEGUNDOS` (padrão **60**), `GEMINI_MAX_TENTATIVAS` (padrão **3**).
4. `GEMINI_API_KEY` e `GEMINI_MODEL` **não** geram erro na importação do settings; a validação acontece ao criar `GeminiClient`.
5. Retry **nativo** do SDK (`types.HttpRetryOptions`), sem loop manual. O SDK repete 408/429/5xx, timeout e falha de conexão.
6. Timeout via `types.HttpOptions(timeout=...)`, que é em **milissegundos** → `segundos * 1000`.
7. `api_key` sempre passada explicitamente e `vertexai=False` → o SDK não usa `GOOGLE_API_KEY` nem troca de backend por variável de ambiente.
8. Hierarquia de exceções própria: `GeminiError` → `GeminiConfiguracaoError`, `GeminiTimeoutError`, `GeminiAPIError`, `GeminiRespostaInvalidaError`.
9. Encadeamento com `raise ... from exc` (a causa original fica em `__cause__` para depuração).
10. API **síncrona** apenas (`client.models.generate_content`).
11. Cliente do SDK criado **sob demanda** (ao instanciar `GeminiClient`), nunca na importação do módulo.
12. Chave nunca exposta: não é guardada em atributo, não entra em `__repr__`, mensagens, logs; `@sensitive_variables` esconde as variáveis locais na página de erro do Django com `DEBUG=True`; no SDK ela vai no header `x-goog-api-key`.
13. Testes com `SimpleTestCase` + `unittest.mock`, sem chamadas reais ao Gemini.

---

## 4. Fluxo criado

### 4.1 Configuração (na inicialização do Django)

```
.env ──load_dotenv()──► os.environ ──os.getenv()──► config/settings.py
                                                     GEMINI_API_KEY          (None se ausente)
                                                     GEMINI_MODEL            (None se ausente)
                                                     GEMINI_TIMEOUT_SEGUNDOS ("60" se ausente/vazio)
                                                     GEMINI_MAX_TENTATIVAS   ("3"  se ausente/vazio)
```

Nenhuma validação aqui → `migrate`, `runserver`, `test` funcionam sem chave.

### 4.2 Criação do cliente — `GeminiClient(...)`

```
GeminiClient(api_key=?, modelo=?, timeout_segundos=?, max_tentativas=?)
 │
 ├─ 1. chave  = parâmetro explícito  OU settings.GEMINI_API_KEY → strip()
 │        None / "" / "   "  ──► GeminiConfiguracaoError("GEMINI_API_KEY não configurada.")
 │
 ├─ 2. modelo = parâmetro explícito  OU settings.GEMINI_MODEL → strip()
 │        None / ""          ──► GeminiConfiguracaoError("GEMINI_MODEL não configurado.")
 │
 ├─ 3. timeout_segundos = parâmetro OU settings OU 60   → int > 0
 │        "abc" / 0 / -1     ──► GeminiConfiguracaoError
 │
 ├─ 4. max_tentativas   = parâmetro OU settings OU 3    → int > 0
 │        "abc" / 0          ──► GeminiConfiguracaoError
 │
 └─ 5. self._client = genai.Client(
            api_key=chave,               # explícito: sem fallback p/ GOOGLE_API_KEY
            vertexai=False,              # explícito: sem troca de backend por env
            http_options=HttpOptions(
                timeout=timeout_segundos * 1000,                    # ms
                retry_options=HttpRetryOptions(attempts=max_tentativas)))
```

Se qualquer validação falhar, o SDK **não** é criado.

### 4.3 Chamada — `gerar_conteudo(...)`

```
gerar_conteudo(conteudo, instrucao_sistema=, schema_resposta=, tipo_resposta=, temperatura=)
 │   conteudo: str (texto)  OU  lista de partes (ex.: texto + Part.from_bytes(pdf))
 │
 ├─ monta types.GenerateContentConfig(system_instruction, response_mime_type,
 │                                    response_schema, temperature)
 │
 ├─ self._client.models.generate_content(model=self.modelo, contents=conteudo, config=config)
 │     (o SDK faz as novas tentativas internamente, até max_tentativas)
 │
 ├─ tradução de exceções (ordem importa: TimeoutException é subclasse de HTTPError):
 │     httpx.TimeoutException   ──► GeminiTimeoutError                     + log WARNING
 │     google.genai.errors.APIError (ClientError 4xx / ServerError 5xx)
 │                              ──► GeminiAPIError(status_code=exc.code)   + log WARNING
 │     httpx.HTTPError (rede)   ──► GeminiAPIError(status_code=None)       + log WARNING
 │
 ├─ texto = resposta.text
 │     erro ao ler / None / "" / só espaços ──► GeminiRespostaInvalidaError
 │
 └─ return texto (str)
```

Mensagens e logs contêm só texto fixo, modelo e código HTTP — nunca a mensagem crua da API, headers ou a chave.

### 4.4 Chamada JSON — `gerar_json(...)`

```
gerar_json(conteudo, instrucao_sistema=, schema_resposta=, temperatura=)
 ├─ gerar_conteudo(..., tipo_resposta="application/json", schema_resposta=...)
 ├─ json.loads(texto)
 │     JSONDecodeError ──► GeminiRespostaInvalidaError
 └─ return dict / list (estrutura Python)
```

### 4.5 Como os agents vão usar (GR-10 / GR-11 — ilustrativo, ainda NÃO implementado)

```python
from google.genai import types
from agents.gemini_client import GeminiClient, GeminiError

# GR-10 — Extrator (PDF → JSON)
cliente = GeminiClient()
try:
    dados = cliente.gerar_json(
        ["Extraia os dados deste documento.",
         types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")],
        schema_resposta=SchemaExtracao,       # pydantic/dict definido na GR-10
    )
except GeminiError:
    ...  # Documento.Status.ERRO, mensagem genérica em metadados

# GR-11 — Classificador (texto → JSON)
classificacao = cliente.gerar_json(
    texto_extraido,
    instrucao_sistema="Classifique o lançamento...",
    schema_resposta=SchemaClassificacao,
    temperatura=0.1,
)
```

Os agents devem capturar apenas `GeminiError` (nunca exceções do SDK/httpx) e podem receber um `GeminiClient` falso nos testes (`mock.Mock(spec=GeminiClient)`).

### 4.6 Hierarquia de exceções

```
Exception
└── GeminiError                      ← agents capturam esta
    ├── GeminiConfiguracaoError      chave/modelo ausente, timeout/tentativas inválidos
    ├── GeminiTimeoutError           httpx.TimeoutException
    ├── GeminiAPIError               APIError do SDK (status_code) ou falha de rede (status_code=None)
    └── GeminiRespostaInvalidaError  resposta vazia/sem texto ou JSON inválido
```

---

## 5. Código completo

### 5.1 `config/settings.py` — final do arquivo (GR-8 + GR-9)

Estado final após resolver o conflito: o bloco da GR-8 fica primeiro e o bloco "Gemini" da GR-9 logo depois.

```python
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# Limite máximo para upload de PDFs

MAX_PDF_UPLOAD_SIZE_MB = int(os.getenv("MAX_PDF_UPLOAD_SIZE_MB", "10"))   # GR-8
MAX_PDF_UPLOAD_SIZE = MAX_PDF_UPLOAD_SIZE_MB * 1024 * 1024                # GR-8

# Gemini
# A validação acontece somente quando agents.gemini_client.GeminiClient é criado.

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")                              # GR-9
GEMINI_MODEL = os.getenv("GEMINI_MODEL")                                  # GR-9
GEMINI_TIMEOUT_SEGUNDOS = os.getenv("GEMINI_TIMEOUT_SEGUNDOS") or "60"    # GR-9
GEMINI_MAX_TENTATIVAS = os.getenv("GEMINI_MAX_TENTATIVAS") or "3"         # GR-9
```

(Os comentários `# GR-8` / `# GR-9` acima são só anotação deste relatório; não existem no arquivo.)

Diff da GR-9 sobre a base atual (`4b4a5f6`, que já tem a GR-8):

```diff
@@ -145,3 +145,11 @@ MEDIA_URL = "/media/"
 MAX_PDF_UPLOAD_SIZE_MB = int(os.getenv("MAX_PDF_UPLOAD_SIZE_MB", "10"))
 MAX_PDF_UPLOAD_SIZE = MAX_PDF_UPLOAD_SIZE_MB * 1024 * 1024
+
+# Gemini
+# A validação acontece somente quando agents.gemini_client.GeminiClient é criado.
+
+GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
+GEMINI_MODEL = os.getenv("GEMINI_MODEL")
+GEMINI_TIMEOUT_SEGUNDOS = os.getenv("GEMINI_TIMEOUT_SEGUNDOS") or "60"
+GEMINI_MAX_TENTATIVAS = os.getenv("GEMINI_MAX_TENTATIVAS") or "3"
```

### 5.2 `.env.example` — arquivo completo (GR-8 + GR-9)

```dotenv
DJANGO_SECRET_KEY=
DJANGO_DEBUG=True

DB_NAME=gestao_rural
DB_USER=gestao_rural_user
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

MAX_PDF_UPLOAD_SIZE_MB=10

GEMINI_API_KEY=
GEMINI_MODEL=
GEMINI_TIMEOUT_SEGUNDOS=60
GEMINI_MAX_TENTATIVAS=3
```

| Variável                  | Tarefa | Valor no exemplo                                                                                                         |
| ------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------ |
| `MAX_PDF_UPLOAD_SIZE_MB`  | GR-8   | `10`                                                                                                                     |
| `GEMINI_API_KEY`          | GR-9   | vazio (segredo; preencher só no `.env` local)                                                                            |
| `GEMINI_MODEL`            | GR-9   | vazio (cada ambiente informa um modelo disponível na conta; sem ele, `GeminiClient()` levanta `GeminiConfiguracaoError`) |
| `GEMINI_TIMEOUT_SEGUNDOS` | GR-9   | `60`                                                                                                                     |
| `GEMINI_MAX_TENTATIVAS`   | GR-9   | `3`                                                                                                                      |

Diff da GR-9 sobre a base atual (na base, `GEMINI_API_KEY=` ficava antes de `MAX_PDF_UPLOAD_SIZE_MB`; foi movida para junto das demais `GEMINI_*`):

```diff
@@ -7,6 +7,9 @@ DB_PASSWORD=
 DB_HOST=localhost
 DB_PORT=5432
-GEMINI_API_KEY=
-
 MAX_PDF_UPLOAD_SIZE_MB=10
+
+GEMINI_API_KEY=
+GEMINI_MODEL=
+GEMINI_TIMEOUT_SEGUNDOS=60
+GEMINI_MAX_TENTATIVAS=3
```

### 5.3 `agents/gemini_client.py` — arquivo completo (novo)

```python
import json
import logging

import httpx
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

TIMEOUT_PADRAO_SEGUNDOS = 60
MAX_TENTATIVAS_PADRAO = 3


class GeminiError(Exception):
    """Erro base do cliente Gemini. Os agents devem capturar somente esta."""


class GeminiConfiguracaoError(GeminiError):
    pass


class GeminiTimeoutError(GeminiError):
    pass


class GeminiAPIError(GeminiError):
    def __init__(self, mensagem, status_code=None):
        super().__init__(mensagem)
        self.status_code = status_code


class GeminiRespostaInvalidaError(GeminiError):
    pass


def _texto_ou_none(valor):
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def _inteiro_positivo(valor, padrao, nome):
    if valor is None or valor == "":
        return padrao
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise GeminiConfiguracaoError(
            f"{nome} deve ser um número inteiro."
        ) from exc
    if numero < 1:
        raise GeminiConfiguracaoError(f"{nome} deve ser maior que zero.")
    return numero


class GeminiClient:
    """Cliente compartilhado do Gemini usado pelos agents.

    A configuração vem de django.conf.settings, mas pode ser sobrescrita
    por parâmetros explícitos. O SDK é criado somente quando esta classe
    é instanciada.
    """

    @sensitive_variables("api_key", "chave")
    def __init__(
        self,
        *,
        api_key=None,
        modelo=None,
        timeout_segundos=None,
        max_tentativas=None,
    ):
        chave = _texto_ou_none(
            api_key if api_key is not None
            else getattr(settings, "GEMINI_API_KEY", None)
        )
        if chave is None:
            raise GeminiConfiguracaoError("GEMINI_API_KEY não configurada.")

        self.modelo = _texto_ou_none(
            modelo if modelo is not None
            else getattr(settings, "GEMINI_MODEL", None)
        )
        if self.modelo is None:
            raise GeminiConfiguracaoError("GEMINI_MODEL não configurado.")

        self.timeout_segundos = _inteiro_positivo(
            timeout_segundos if timeout_segundos is not None
            else getattr(settings, "GEMINI_TIMEOUT_SEGUNDOS", None),
            TIMEOUT_PADRAO_SEGUNDOS,
            "GEMINI_TIMEOUT_SEGUNDOS",
        )
        self.max_tentativas = _inteiro_positivo(
            max_tentativas if max_tentativas is not None
            else getattr(settings, "GEMINI_MAX_TENTATIVAS", None),
            MAX_TENTATIVAS_PADRAO,
            "GEMINI_MAX_TENTATIVAS",
        )

        # api_key e vertexai explícitos impedem que o SDK use GOOGLE_API_KEY
        # ou troque de backend a partir de variáveis de ambiente.
        self._client = genai.Client(
            api_key=chave,
            vertexai=False,
            http_options=types.HttpOptions(
                timeout=self.timeout_segundos * 1000,
                retry_options=types.HttpRetryOptions(
                    attempts=self.max_tentativas,
                ),
            ),
        )

    def __repr__(self):
        return (
            f"GeminiClient(modelo={self.modelo!r}, "
            f"timeout_segundos={self.timeout_segundos}, "
            f"max_tentativas={self.max_tentativas})"
        )

    def gerar_conteudo(
        self,
        conteudo,
        *,
        instrucao_sistema=None,
        schema_resposta=None,
        tipo_resposta=None,
        temperatura=None,
    ):
        """Envia o conteúdo ao Gemini e retorna o texto da resposta.

        `conteudo` pode ser texto ou uma lista de partes do SDK
        (ex.: types.Part.from_bytes(data=..., mime_type="application/pdf")).
        """
        config = types.GenerateContentConfig(
            system_instruction=instrucao_sistema,
            response_mime_type=tipo_resposta,
            response_schema=schema_resposta,
            temperature=temperatura,
        )

        try:
            resposta = self._client.models.generate_content(
                model=self.modelo,
                contents=conteudo,
                config=config,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Timeout na chamada ao Gemini (modelo=%s).", self.modelo)
            raise GeminiTimeoutError(
                "Tempo limite excedido na chamada ao Gemini."
            ) from exc
        except errors.APIError as exc:
            logger.warning(
                "Erro da API do Gemini (modelo=%s, status=%s).",
                self.modelo,
                exc.code,
            )
            raise GeminiAPIError(
                f"Erro da API do Gemini (status {exc.code}).",
                status_code=exc.code,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede na chamada ao Gemini (modelo=%s).", self.modelo)
            raise GeminiAPIError(
                "Falha de comunicação com o Gemini."
            ) from exc

        try:
            texto = resposta.text
        except (AttributeError, ValueError) as exc:
            raise GeminiRespostaInvalidaError(
                "Resposta do Gemini sem conteúdo de texto."
            ) from exc

        if not texto or not texto.strip():
            raise GeminiRespostaInvalidaError("Resposta do Gemini vazia.")

        return texto

    def gerar_json(
        self,
        conteudo,
        *,
        instrucao_sistema=None,
        schema_resposta=None,
        temperatura=None,
    ):
        """Solicita saída JSON ao Gemini e retorna a estrutura Python."""
        texto = self.gerar_conteudo(
            conteudo,
            instrucao_sistema=instrucao_sistema,
            schema_resposta=schema_resposta,
            tipo_resposta="application/json",
            temperatura=temperatura,
        )

        try:
            return json.loads(texto)
        except json.JSONDecodeError as exc:
            raise GeminiRespostaInvalidaError(
                "Resposta do Gemini não é um JSON válido."
            ) from exc
```

### 5.4 `agents/test_gemini_client.py` — arquivo completo (novo)

```python
import os
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings
from google.genai import errors

from .gemini_client import (
    GeminiAPIError,
    GeminiClient,
    GeminiConfiguracaoError,
    GeminiError,
    GeminiRespostaInvalidaError,
    GeminiTimeoutError,
)

CHAVE_TESTE = "chave-secreta-teste-gr9"

CONFIGURACAO_PADRAO = {
    "GEMINI_API_KEY": CHAVE_TESTE,
    "GEMINI_MODEL": "modelo-teste",
    "GEMINI_TIMEOUT_SEGUNDOS": "60",
    "GEMINI_MAX_TENTATIVAS": "3",
}


def erro_api(classe, codigo, status):
    return classe(
        codigo,
        {
            "error": {
                "code": codigo,
                "message": f"Falha usando a chave {CHAVE_TESTE}",
                "status": status,
            }
        },
    )


@override_settings(**CONFIGURACAO_PADRAO)
class GeminiClientTestBase(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch("agents.gemini_client.genai.Client")
        self.sdk_client_classe = patcher.start()
        self.addCleanup(patcher.stop)
        self.sdk_client = self.sdk_client_classe.return_value
        self.generate_content = self.sdk_client.models.generate_content

    def argumentos_do_sdk(self):
        return self.sdk_client_classe.call_args.kwargs

    def definir_resposta(self, texto):
        self.generate_content.return_value = mock.Mock(text=texto)


class GeminiClientConfiguracaoTests(GeminiClientTestBase):
    @override_settings(GEMINI_API_KEY=None)
    def test_chave_ausente_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

        self.sdk_client_classe.assert_not_called()

    @override_settings(GEMINI_API_KEY="")
    def test_chave_vazia_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    @override_settings(GEMINI_API_KEY="   ")
    def test_chave_so_com_espacos_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    @override_settings(GEMINI_MODEL=None)
    def test_modelo_ausente_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    def test_chave_valida_e_passada_explicitamente_ao_sdk(self):
        cliente = GeminiClient()

        argumentos = self.argumentos_do_sdk()
        self.assertEqual(argumentos["api_key"], CHAVE_TESTE)
        self.assertIs(argumentos["vertexai"], False)
        self.assertEqual(cliente.modelo, "modelo-teste")

    @override_settings(GEMINI_API_KEY=None)
    def test_google_api_key_nao_substitui_gemini_api_key_ausente(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "outra-chave"}):
            with self.assertRaises(GeminiConfiguracaoError):
                GeminiClient()

        self.sdk_client_classe.assert_not_called()

    def test_google_api_key_nao_substitui_gemini_api_key_configurada(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "outra-chave"}):
            GeminiClient()

        self.assertEqual(self.argumentos_do_sdk()["api_key"], CHAVE_TESTE)

    def test_parametros_explicitos_sobrescrevem_settings(self):
        cliente = GeminiClient(
            api_key="chave-explicita",
            modelo="modelo-explicito",
            timeout_segundos=10,
            max_tentativas=5,
        )

        argumentos = self.argumentos_do_sdk()
        self.assertEqual(argumentos["api_key"], "chave-explicita")
        self.assertEqual(cliente.modelo, "modelo-explicito")
        self.assertEqual(argumentos["http_options"].timeout, 10_000)
        self.assertEqual(
            argumentos["http_options"].retry_options.attempts, 5
        )

    def test_timeout_e_configurado_em_milissegundos(self):
        cliente = GeminiClient()

        self.assertEqual(cliente.timeout_segundos, 60)
        self.assertEqual(self.argumentos_do_sdk()["http_options"].timeout, 60_000)

    @override_settings(GEMINI_TIMEOUT_SEGUNDOS=None, GEMINI_MAX_TENTATIVAS=None)
    def test_timeout_e_tentativas_usam_padrao_quando_ausentes(self):
        cliente = GeminiClient()

        self.assertEqual(cliente.timeout_segundos, 60)
        self.assertEqual(cliente.max_tentativas, 3)

    @override_settings(GEMINI_TIMEOUT_SEGUNDOS="abc")
    def test_timeout_invalido_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    def test_tentativas_usam_retry_nativo_do_sdk(self):
        cliente = GeminiClient()

        retry = self.argumentos_do_sdk()["http_options"].retry_options
        self.assertEqual(cliente.max_tentativas, 3)
        self.assertEqual(retry.attempts, 3)

    @override_settings(GEMINI_MAX_TENTATIVAS="0")
    def test_tentativas_menor_que_um_gera_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError):
            GeminiClient()

    def test_repr_nao_expoe_chave(self):
        cliente = GeminiClient()

        self.assertNotIn(CHAVE_TESTE, repr(cliente))
        self.assertNotIn(CHAVE_TESTE, str(cliente))


class GeminiClientChamadaTests(GeminiClientTestBase):
    def test_chamada_com_sucesso_retorna_texto(self):
        self.definir_resposta("resposta do modelo")

        texto = GeminiClient().gerar_conteudo(
            "Classifique este lançamento",
            instrucao_sistema="Você é um classificador.",
            temperatura=0.1,
        )

        self.assertEqual(texto, "resposta do modelo")
        argumentos = self.generate_content.call_args.kwargs
        self.assertEqual(argumentos["model"], "modelo-teste")
        self.assertEqual(argumentos["contents"], "Classifique este lançamento")
        self.assertEqual(argumentos["config"].temperature, 0.1)
        self.assertIsNone(argumentos["config"].response_mime_type)

    def test_aceita_conteudo_multimodal(self):
        self.definir_resposta("ok")
        conteudo = ["Extraia os dados", mock.sentinel.parte_pdf]

        GeminiClient().gerar_conteudo(conteudo)

        self.assertEqual(
            self.generate_content.call_args.kwargs["contents"], conteudo
        )

    def test_json_valido_e_convertido(self):
        self.definir_resposta('{"categoria": "insumos", "valor": 10.5}')
        schema = {
            "type": "OBJECT",
            "properties": {"categoria": {"type": "STRING"}},
        }

        resultado = GeminiClient().gerar_json(
            "Classifique", schema_resposta=schema
        )

        self.assertEqual(resultado, {"categoria": "insumos", "valor": 10.5})
        config = self.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertIsNotNone(config.response_schema)

    def test_json_invalido_gera_resposta_invalida(self):
        self.definir_resposta("isto não é json")

        with self.assertRaises(GeminiRespostaInvalidaError):
            GeminiClient().gerar_json("Classifique")

    def test_resposta_vazia_gera_resposta_invalida(self):
        for texto in (None, "", "   "):
            with self.subTest(texto=texto):
                self.definir_resposta(texto)

                with self.assertRaises(GeminiRespostaInvalidaError):
                    GeminiClient().gerar_conteudo("Olá")


class GeminiClientFalhasTests(GeminiClientTestBase):
    def test_timeout_gera_gemini_timeout_error(self):
        self.generate_content.side_effect = httpx.ReadTimeout("timeout")

        with self.assertLogs("agents.gemini_client", "WARNING"):
            with self.assertRaises(GeminiTimeoutError) as contexto:
                GeminiClient().gerar_conteudo("Olá")

        self.assertIsInstance(contexto.exception.__cause__, httpx.ReadTimeout)

    def test_erro_de_rede_gera_gemini_api_error(self):
        self.generate_content.side_effect = httpx.ConnectError("sem rede")

        with self.assertLogs("agents.gemini_client", "WARNING"):
            with self.assertRaises(GeminiAPIError) as contexto:
                GeminiClient().gerar_conteudo("Olá")

        self.assertIsNone(contexto.exception.status_code)

    def test_erro_da_api_gera_gemini_api_error_com_status(self):
        casos = (
            (errors.ClientError, 403, "PERMISSION_DENIED"),
            (errors.ClientError, 429, "RESOURCE_EXHAUSTED"),
            (errors.ServerError, 503, "UNAVAILABLE"),
        )
        for classe, codigo, status in casos:
            with self.subTest(codigo=codigo):
                erro = erro_api(classe, codigo, status)
                self.generate_content.side_effect = erro

                with self.assertLogs("agents.gemini_client", "WARNING"):
                    with self.assertRaises(GeminiAPIError) as contexto:
                        GeminiClient().gerar_conteudo("Olá")

                self.assertEqual(contexto.exception.status_code, codigo)
                self.assertIs(contexto.exception.__cause__, erro)

    def test_todas_as_excecoes_herdam_gemini_error(self):
        for classe in (
            GeminiConfiguracaoError,
            GeminiTimeoutError,
            GeminiAPIError,
            GeminiRespostaInvalidaError,
        ):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(issubclass(classe, GeminiError))

    def test_chave_nao_aparece_em_excecoes_nem_logs(self):
        falhas = (
            httpx.ReadTimeout(f"timeout {CHAVE_TESTE}"),
            httpx.ConnectError(f"sem rede {CHAVE_TESTE}"),
            erro_api(errors.ClientError, 401, "UNAUTHENTICATED"),
            erro_api(errors.ServerError, 500, "INTERNAL"),
        )
        for falha in falhas:
            with self.subTest(falha=type(falha).__name__):
                self.generate_content.side_effect = falha

                with self.assertLogs("agents.gemini_client") as logs:
                    with self.assertRaises(GeminiError) as contexto:
                        GeminiClient().gerar_conteudo("Olá")

                self.assertNotIn(CHAVE_TESTE, str(contexto.exception))
                self.assertNotIn(CHAVE_TESTE, repr(contexto.exception))
                self.assertNotIn(CHAVE_TESTE, "\n".join(logs.output))

    def test_chave_nao_aparece_em_erros_de_resposta(self):
        self.generate_content.side_effect = None
        for texto in (None, "json inválido"):
            with self.subTest(texto=texto):
                self.definir_resposta(texto)

                with self.assertRaises(GeminiRespostaInvalidaError) as contexto:
                    GeminiClient().gerar_json("Olá")

                self.assertNotIn(CHAVE_TESTE, str(contexto.exception))

    @override_settings(GEMINI_MODEL=None)
    def test_chave_nao_aparece_em_erro_de_configuracao(self):
        with self.assertRaises(GeminiConfiguracaoError) as contexto:
            GeminiClient()

        self.assertNotIn(CHAVE_TESTE, str(contexto.exception))


@override_settings(**CONFIGURACAO_PADRAO)
class GeminiClientSdkRealTests(SimpleTestCase):
    """Usa o genai.Client real, sem chamadas de rede."""

    def test_sdk_real_usa_gemini_api_key_mesmo_com_google_api_key(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "outra-chave"}):
            cliente = GeminiClient()

        self.assertEqual(cliente._client._api_client.api_key, CHAVE_TESTE)
        self.assertNotIn(CHAVE_TESTE, repr(cliente))
```

---

## 6. Testes criados (27) e o que cobrem

Todos usam `SimpleTestCase` (sem banco) e `genai.Client` substituído por `mock.patch("agents.gemini_client.genai.Client")`,
exceto `GeminiClientSdkRealTests`, que instancia o `genai.Client` real **sem fazer chamadas de rede**.
`CHAVE_TESTE = "chave-secreta-teste-gr9"` é colocada de propósito nas mensagens de erro simuladas da API para provar que ela não vaza.

### `GeminiClientConfiguracaoTests` (14)

| Teste                                                          | Requisito                                           |
| -------------------------------------------------------------- | --------------------------------------------------- |
| `test_chave_ausente_gera_erro_de_configuracao`                 | chave ausente (e SDK não é criado)                  |
| `test_chave_vazia_gera_erro_de_configuracao`                   | chave vazia                                         |
| `test_chave_so_com_espacos_gera_erro_de_configuracao`          | chave só com espaços                                |
| `test_modelo_ausente_gera_erro_de_configuracao`                | modelo obrigatório                                  |
| `test_chave_valida_e_passada_explicitamente_ao_sdk`            | chave válida, `api_key` explícito, `vertexai=False` |
| `test_google_api_key_nao_substitui_gemini_api_key_ausente`     | `GOOGLE_API_KEY` não substitui chave ausente        |
| `test_google_api_key_nao_substitui_gemini_api_key_configurada` | `GOOGLE_API_KEY` não substitui chave configurada    |
| `test_parametros_explicitos_sobrescrevem_settings`             | parâmetros explícitos > settings                    |
| `test_timeout_e_configurado_em_milissegundos`                  | timeout 60 s → 60000 ms                             |
| `test_timeout_e_tentativas_usam_padrao_quando_ausentes`        | padrões 60 / 3                                      |
| `test_timeout_invalido_gera_erro_de_configuracao`              | timeout inválido                                    |
| `test_tentativas_usam_retry_nativo_do_sdk`                     | `HttpRetryOptions(attempts=3)`                      |
| `test_tentativas_menor_que_um_gera_erro_de_configuracao`       | tentativas inválidas                                |
| `test_repr_nao_expoe_chave`                                    | chave fora de `repr`/`str` do cliente               |

### `GeminiClientChamadaTests` (5)

| Teste                                        | Requisito                                                  |
| -------------------------------------------- | ---------------------------------------------------------- |
| `test_chamada_com_sucesso_retorna_texto`     | sucesso; modelo, conteúdo e temperatura repassados         |
| `test_aceita_conteudo_multimodal`            | lista de partes (texto + PDF) repassada ao SDK             |
| `test_json_valido_e_convertido`              | JSON válido → dict; `application/json` + `response_schema` |
| `test_json_invalido_gera_resposta_invalida`  | JSON inválido                                              |
| `test_resposta_vazia_gera_resposta_invalida` | `None`, `""`, `"   "`                                      |

### `GeminiClientFalhasTests` (7)

| Teste                                               | Requisito                                    |
| --------------------------------------------------- | -------------------------------------------- |
| `test_timeout_gera_gemini_timeout_error`            | timeout (`__cause__` preservado)             |
| `test_erro_de_rede_gera_gemini_api_error`           | erro HTTP/rede                               |
| `test_erro_da_api_gera_gemini_api_error_com_status` | 403, 429, 503 com `status_code`              |
| `test_todas_as_excecoes_herdam_gemini_error`        | hierarquia                                   |
| `test_chave_nao_aparece_em_excecoes_nem_logs`       | chave fora de `str(exc)`, `repr(exc)` e logs |
| `test_chave_nao_aparece_em_erros_de_resposta`       | chave fora dos erros de resposta             |
| `test_chave_nao_aparece_em_erro_de_configuracao`    | chave fora do erro de configuração           |

### `GeminiClientSdkRealTests` (1)

| Teste                                                       | Requisito                                                                              |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `test_sdk_real_usa_gemini_api_key_mesmo_com_google_api_key` | no SDK real, a chave usada é a `GEMINI_API_KEY` mesmo com `GOOGLE_API_KEY` no ambiente |

---

## 7. Execução e resultados

### 7.1 Testes automatizados (após integrar a GR-8)

```
$ python manage.py check
System check identified no issues (0 silenced).        → OK

$ python manage.py test agents
Ran 27 tests ... OK                                     → 27 testes, OK

$ python manage.py test
Ran 55 tests ... OK                                     → 55 testes, OK

$ git diff --check
(sem saída)                                             → OK
```

Antes da integração com a GR-8 a suíte completa tinha 51 testes; a GR-8 acrescentou testes em `documentos`, e o total agora é 55.

### 7.2 Testes manuais com a API real do Gemini

Feitos fora da suíte automatizada (a suíte **nunca** chama a API real), usando o `.env` local com `GEMINI_API_KEY` e `GEMINI_MODEL` preenchidos.

**a) `gerar_conteudo(...)`**

```python
from agents.gemini_client import GeminiClient
GeminiClient().gerar_conteudo(...)
# resposta real: ok
```

**b) `gerar_json(...)`**

```python
GeminiClient().gerar_json(...)
# resposta real: {'status': 'ok'}
```

Isso confirmou:

- `GEMINI_API_KEY` válida;
- `GEMINI_MODEL` acessível com essa chave;
- autenticação funcionando (chave enviada explicitamente pelo cliente);
- `GeminiClient` conseguindo chamar a API real;
- retorno de texto funcionando (`gerar_conteudo` → `str`);
- retorno JSON funcionando (`gerar_json` → `dict` Python).

### 7.3 Warning `Both GOOGLE_API_KEY and GEMINI_API_KEY are set...`

Esse aviso aparece durante a execução dos testes automatizados. Ele é emitido pelo SDK `google-genai` no teste
`GeminiClientSdkRealTests.test_sdk_real_usa_gemini_api_key_mesmo_com_google_api_key`, que:

1. injeta **temporariamente** `GOOGLE_API_KEY="outra-chave"` com `mock.patch.dict(os.environ, ...)`;
2. cria um `GeminiClient` com o `genai.Client` real (sem rede);
3. verifica que a chave usada continua sendo a configurada explicitamente (`GEMINI_API_KEY`).

Como o `.env` local define `GEMINI_API_KEY` e o teste injeta `GOOGLE_API_KEY`, o SDK vê as duas no ambiente
e avisa. É **esperado** e prova justamente o comportamento desejado (sem fallback para `GOOGLE_API_KEY`).
O `mock.patch.dict` restaura o ambiente ao fim do teste. Foi confirmado no terminal que `GOOGLE_API_KEY`
**não está definida permanentemente** no ambiente do Pedro.

### 7.4 Ajustes feitos durante a implementação

- `_inteiro_positivo` passou de `from None` para `from exc`, seguindo a regra de encadeamento.
- Adicionado `@sensitive_variables("api_key", "chave")` no construtor (proteção extra com `DEBUG=True`).
- Testes de timeout/rede/API passaram a usar `assertLogs(..., "WARNING")` para que os avisos esperados não poluam a saída dos testes.
- O teste de "chave fora do erro de configuração" usa `GEMINI_MODEL=None` com a chave presente (assim a chave existe e é possível provar que ela não aparece na mensagem).

---

## 8. `git status` / diff resumido (sem commit)

```
M  .env.example            GR-8 preservada + variáveis GEMINI_* (conflito resolvido)
M  .gitignore              remoção da regra de analisetemporaria.md (decisão do Pedro Simon)
M  config/settings.py      GR-8 preservada + bloco "Gemini" (conflito resolvido)
?? agents/gemini_client.py
?? agents/test_gemini_client.py
?? analisetemporaria.md    será versionado por decisão do Pedro Simon
```

- Base: `4b4a5f6` (merge da GR-8). Os arquivos modificados aparecem no índice como resultado da reaplicação do stash e da resolução dos conflitos.
- Não há conflito pendente.
- Stash `stash@{0}: WIP GR-9 antes de atualizar com GR-8` mantido.
- `.env` ignorado e fora do índice.

---

## 9. Pendências e próximos passos

1. **Revisão** do código e deste relatório.
2. Commit da GR-9 (somente com autorização). Mensagem sugerida: `feat(agents): configurar cliente compartilhado do Gemini GR-9`,
   com `agents/gemini_client.py`, `agents/test_gemini_client.py`, `config/settings.py`, `.env.example`,
   `.gitignore` e `analisetemporaria.md`. **Nunca incluir `.env`.**
3. Push e Pull Request para `main` (somente com autorização).
4. Apagar o `stash@{0}` **somente depois** que a GR-9 estiver commitada e revisada (decisão do Pedro).
5. GR-10 / GR-11: implementar os agents consumindo `GeminiClient` e capturando somente `GeminiError`.
