# Gestão Rural — Documento de handoff (estado atual e GR-14 pronta para commit/PR)

> **Para que serve este arquivo:** quem abrir só este documento deve conseguir entender o projeto, o que o professor pediu, o que já foi concluído, como o backend funciona hoje e **como a interface Web (GR-14) foi implementada e validada**.
>
> **Estado atual:** GR-6 a GR-12 **concluídas e mergeadas**. **GR-14 concluída na branch (etapas 1 a 6)**: tela de envio, página de detalhe, botão Processar chamando `processar_documento` (GR-12), JS de proteção visual e **validação manual no navegador com execução real da Gemini (Documento ID 2 → `CONCLUIDO`)**. A GR-14 está **tecnicamente pronta para commit/PR**, aguardando autorização. Depois do merge, a próxima tarefa é a **GR-21** (seção 23).
>
> **Fonte de verdade:** o código da branch `feature/GR-14-interface-web`, criada a partir da `main` em `292ee0c` (merge da GR-12) e que agora contém as mudanças **ainda não commitadas** das etapas 1 a 6 da GR-14 (a etapa 6 só atualizou este relatório). Contratos, rotas e contagens abaixo foram conferidos no código.
>
> **Regras deste documento:**
> - nenhuma chave, segredo ou valor real do `.env` aparece aqui;
> - nenhum dado pessoal real aparece aqui;
> - `999.999.999-99` é um CPF **explicitamente fictício**, do PDF de demonstração.

---

## Sumário

**Parte I — Projeto**
1. [A atividade (o que o professor pediu)](#1-a-atividade-o-que-o-professor-pediu)
2. [Estado das tarefas](#2-estado-das-tarefas)
3. [Estrutura atual do projeto](#3-estrutura-atual-do-projeto)
4. [Projeto × atividade](#4-projeto--atividade)

**Parte II — Backend pronto (GR-6 a GR-12)**
5. [Documento, upload e validação (GR-6/7/8)](#5-documento-upload-e-validação-gr-678)
6. [GeminiClient (GR-9)](#6-geminiclient-gr-9)
7. [AgentExtrator (GR-10)](#7-agentextrator-gr-10)
8. [AgentClassificador (GR-11)](#8-agentclassificador-gr-11)
9. [Orquestração `processar_documento` (GR-12)](#9-orquestração-processar_documento-gr-12)

**Parte III — GR-14: interface Web (concluída na branch)**
10. [Progresso, estado da interface e validação manual](#10-progresso-estado-da-interface-e-validação-manual)
11. [Arquitetura](#11-arquitetura)
12. [Fluxo da GR-14 (implementado)](#12-fluxo-da-gr-14-implementado)
13. [URLs e views](#13-urls-e-views)
14. [Templates, CSS e JS](#14-templates-css-e-js)
15. [Apresentação por status, JSON e erros](#15-apresentação-por-status-json-e-erros)
16. [Arquivos](#16-arquivos)
17. [Testes](#17-testes)
18. [Riscos](#18-riscos)
19. [Decisões](#19-decisões)
20. [Ordem de implementação e próximos passos](#20-ordem-de-implementação-e-próximos-passos)

**Parte IV — Operação**
21. [Guia da Gemini API](#21-guia-da-gemini-api)
22. [Checklist de segurança](#22-checklist-de-segurança)
23. [Depois da GR-14: GR-21](#23-depois-da-gr-14-gr-21)
24. [Estado do Git](#24-estado-do-git)

---

# Parte I — Projeto

## 1. A atividade (o que o professor pediu)

**Requisitos gerais:**

- Processador de **PDF de nota fiscal de contas a pagar**.
- Uso de **Agents** (Gemini recomendado).
- Resposta em **JSON**.
- **Interface Web:** o usuário carrega o PDF, **aciona o processamento por um botão** e vê o **JSON na tela**.

**Campos obrigatórios do JSON:**

| Grupo | Campos |
| --- | --- |
| Fornecedor | Razão Social, Nome Fantasia, CNPJ |
| Faturado | Nome Completo, CPF |
| Nota | Número da Nota Fiscal, Data de Emissão |
| Itens | Descrição dos produtos |
| Parcelas | Quantidade de parcelas, Data de vencimento |
| Financeiro | Valor total |
| Classificação | **TipoDespesa** |

**Observações do enunciado:**

- Não é necessário criar uma entidade Produto.
- Deve existir estrutura para múltiplas parcelas.
- `TipoDespesa` **não** é copiado do PDF: é **interpretado pelo Gemini com base nos produtos**.

**Avaliação:**

| Peso | Critério |
| --- | --- |
| 40% | Uso do Agent conforme a estrutura |
| 30% | Conteúdo do JSON |
| 30% | Assertividade da classificação da despesa |

---

## 2. Estado das tarefas

| Tarefa | Descrição | Situação | Evidência |
| --- | --- | --- | --- |
| GR-6 | Modelar `Documento` | ✅ mergeada | PR #6 |
| GR-7 | Upload de PDF | ✅ mergeada | PR #7 |
| GR-8 | Validação de PDF | ✅ mergeada | PR #8 |
| GR-9 | `GeminiClient` | ✅ mergeada | PR #9 |
| GR-10 | Agent Extrator | ✅ mergeada | PR #10 |
| GR-11 | Agent Classificador | ✅ mergeada | PR #11 |
| GR-12 | Orquestração PDF → Agents → JSON | ✅ mergeada, com teste real ponta a ponta feito | PR #12 (`2f7f742`, merge `292ee0c`) |
| **GR-14** | **Interface Web** | ✅ **concluída na branch (etapas 1–6), validada manualmente com a Gemini real; pronta para commit/PR** | branch `feature/GR-14-interface-web` (sem commit) |
| GR-21 | Validação final | ⏳ **próxima tarefa**, depois do merge da GR-14 | — |

```
GR-6 → GR-7 → GR-8 ─────────────┐
GR-9 → GR-10 → GR-11 → GR-12 ───┴─► GR-14 (interface) ─► GR-21 (validação final)
```

**Testes atuais:** `python manage.py test` → **303 testes — OK** (216 da base + 87 da GR-14). Nenhum chama a API real.

| Área | Testes |
| --- | --- |
| projeto base (documentos, financeiro, usuários, `GeminiClient`) | 55 |
| Extrator | 86 |
| Classificador | 26 |
| Orquestração (`documentos.test_processamento`) | 49 |
| GR-14 etapa 1 (caminho 500 do upload + `_salvar_documento`, em `documentos/test_upload.py`) | 4 |
| GR-14 etapas 2 a 5 (`documentos/test_interface.py`) | 83 |

---

## 3. Estrutura atual do projeto

```
gestao-rural/
├── config/
│   ├── settings.py              load_dotenv(); PostgreSQL; templates/static padrão; messages; GEMINI_*
│   └── urls.py                  "" → redirect /documentos/ (inicio) · admin/ · include("documentos.urls") em documentos/
├── documentos/
│   ├── models.py                Documento (GR-6)
│   ├── urls.py                  "" · upload/ · <int:pk>/ · <int:pk>/processar/ — GR-14
│   ├── views.py                 _salvar_documento · upload_documento (JSON, GR-7) · documento_inicio · documento_detalhe + apresentação · documento_processar (GR-14)
│   ├── templates/documentos/    base.html · inicio.html · detalhe.html — GR-14
│   ├── static/documentos/       documentos.css · documentos.js — GR-14
│   ├── forms.py                 DocumentoUploadForm → validar_pdf (GR-8)
│   ├── validators.py            validar_pdf (GR-8)
│   ├── processamento.py         processar_documento (GR-12)
│   ├── admin.py                 DocumentoAdmin (status editável)
│   ├── tests.py, test_upload.py, test_processamento.py, test_interface.py
│   └── migrations/0001_initial.py
├── agents/
│   ├── gemini_client.py         GR-9
│   ├── extrator/                GR-10
│   └── classificador/           GR-11
├── financeiro/, usuarios/       models de apoio (fora do fluxo)
├── uploads/teste-gr10/          PDF fictício — IGNORADO pelo Git
├── media/                       PDFs enviados — IGNORADO pelo Git
└── analisetemporaria.md         este documento
```

Templates e static existem **só** no app `documentos` (GR-14); `config/settings.py` não precisou mudar.

---

## 4. Projeto × atividade

| Requisito | Situação | Onde |
| --- | --- | --- |
| Receber, armazenar e validar PDF | ✅ | GR-6/7/8 (endpoint JSON) |
| Agent de extração (todos os campos da nota) | ✅ | GR-10 |
| Múltiplas parcelas + `quantidade_parcelas` explícita | ✅ | GR-10 + GR-12 |
| **TipoDespesa** interpretado pelo Gemini | ✅ | GR-11 |
| Extração + classificação encadeadas; JSON final persistido; estados; erros seguros | ✅ | GR-12 |
| **Tela para carregar o PDF** | ✅ (branch, validado no navegador) | **GR-14** (`/documentos/`) |
| **Botão para acionar o processamento** | ✅ (branch, validado com a Gemini real) | **GR-14** (`POST /documentos/<id>/processar/` → `processar_documento`) |
| **JSON na tela** | ✅ (branch, validado no navegador) | **GR-14** |
| Validação final ponta a ponta no navegador | ⏳ | GR-21 |

**Todos os requisitos da atividade estão implementados e foram validados no navegador** na branch da GR-14: upload do PDF, botão de processamento, Agents de extração e classificação com a Gemini real, e JSON final na tela (seção 10.3). Faltam o **commit/PR/merge da GR-14** e a **GR-21** (validação final da atividade).

---

# Parte II — Backend pronto (GR-6 a GR-12)

## 5. Documento, upload e validação (GR-6/7/8)

### 5.1 `Documento` (`documentos/models.py`)

| Campo | Tipo | Observação |
| --- | --- | --- |
| `arquivo` | `FileField(upload_to="documentos/")` | PDF em `MEDIA_ROOT/documentos/`; **não deve ser exposto por URL** |
| `nome_original` | `CharField(255)` | nome sanitizado pela GR-8 |
| `enviado_em` | `DateTimeField(auto_now_add)` | |
| `status` | `PENDENTE` · `PROCESSANDO` · `CONCLUIDO` · `ERRO` | `get_status_display()` → "Pendente", "Processando", "Concluído", "Erro" |
| `titular` | FK `Titular`, `null=True` | fora do escopo |
| `resultado_estruturado` | `JSONField` | JSON final (GR-12); `{}` fora de `CONCLUIDO` |
| `metadados` | `JSONField` | `processamento` e, em `ERRO`, `erro` (GR-12) |

O model não tem `Meta.ordering`: a lista da interface precisa ordenar explicitamente (`-enviado_em`).

### 5.2 Upload JSON (GR-7) — `documentos/views.py::upload_documento`

- `POST /documentos/upload/`, `name="documento_upload"`, declarado em **`documentos/urls.py`** (incluído por `config/urls.py` em `documentos/`) desde a etapa 1 da GR-14. URL e nome não mudaram.
- `@staff_member_required`: anônimo ou não-staff é redirecionado para `/admin/login/`. `@require_POST`: GET recebe 405.
- Usa `DocumentoUploadForm(request.POST, request.FILES)`. Se for inválido → `400 {"erro": "<1ª mensagem do campo arquivo>"}`.
- Salva pelo helper **`_salvar_documento(arquivo)`** (etapa 1 da GR-14), que cria `Documento(arquivo=..., nome_original=arquivo.name)` com status `PENDENTE`. Se o save falhar depois que o arquivo foi gravado, o helper remove o arquivo e relança. A view converte `DatabaseError`/`OSError` em `500 {"erro": "Não foi possível salvar o documento."}`.
- Sucesso → `201 {"id", "nome_original", "status": "PENDENTE"}`.
- Coberto por `documentos/test_upload.py`: os 8 testes originais da GR-7 (inalterados, usam `reverse("documento_upload")`) + 4 testes de regressão do caminho 500 e do helper (etapa 1 da GR-14).

### 5.3 Validação (GR-8)

O form **real** chama-se **`DocumentoUploadForm`** (não existe `DocumentoForm`). Tem um único campo `arquivo` (`forms.FileField`), e `clean_arquivo` chama `validar_pdf`:

| Validação | Mensagem ao usuário |
| --- | --- |
| sem arquivo | "Selecione um arquivo PDF." |
| extensão ≠ `.pdf` | "Selecione um arquivo PDF." |
| vazio | "O arquivo PDF está vazio." |
| > `MAX_PDF_UPLOAD_SIZE_MB` (10) | "O arquivo excede o limite de 10 MB." |
| `content_type` ≠ `application/pdf` | "O tipo do arquivo enviado não é PDF." |
| sem cabeçalho `%PDF-` | "O arquivo enviado não é um PDF válido." |

Também sanitiza o nome (`get_valid_filename`). **As mensagens já são adequadas para a tela.**

---

## 6. GeminiClient (GR-9)

`agents/gemini_client.py`, o único ponto que fala com o SDK `google-genai` 2.24.0.

- `gerar_json(conteudo, *, instrucao_sistema, schema_resposta, temperatura)` → `dict`.
- **Configuração:** `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SEGUNDOS` (60, por tentativa) e `GEMINI_MAX_TENTATIVAS` (3, no total), todos via `settings`.
- **Retry:** fica a cargo do SDK (408/429/500/502/503/504, timeout, conexão).
- **Exceções**, todas herdando de `GeminiError`: `GeminiConfiguracaoError`, `GeminiTimeoutError`, `GeminiAPIError(status_code)` e `GeminiRespostaInvalidaError`.
- **A interface nunca usa o `GeminiClient`.**

---

## 7. AgentExtrator (GR-10)

`AgentExtrator(cliente=None).extrair_documento(documento) -> NotaFiscalExtraida`. Lê o PDF pelo storage e **não** altera o `Documento`.

**`NotaFiscalExtraida`:**

- `fornecedor{razao_social, nome_fantasia, cnpj}`, `faturado{nome, cpf}`;
- `numero_nota`, `data_emissao` (`date`);
- `itens[]{descricao, quantidade, valor_unitario, valor_total}`;
- `parcelas[]{numero, data_vencimento, valor}`, `valor_total` (`Decimal` > 0);
- `validacoes`, calculado localmente.

`model_dump(mode="json")` produz dinheiro como string (`"1500.00"`) e datas ISO.

**Política de CPF/CNPJ:**

- **Dado extraído:** o Gemini copia o número do documento.
- **Validade matemática:** a aplicação normaliza, **preserva** e valida o DV, sinalizando em `validacoes.{fornecedor_cnpj,faturado_cpf} = {"status": "valido"|"invalido"|"ausente", "motivo": null|"digitos_verificadores_invalidos"}`.
- **Existência real:** **não é verificada**; DV válido não prova que a pessoa ou empresa existe.
- DV inválido **não descarta a nota**. Exemplo fictício: `999.999.999-99` → `"99999999999"` e `invalido`.
- CNPJ alfanumérico é suportado.

**Exceções:**

| Exceção | `codigo` |
| --- | --- |
| `DocumentoIlegivelError` | `documento_ilegivel` (sem arquivo, removido, vazio, sem `%PDF-`; o Gemini não é chamado) |
| `ExtracaoIndisponivelError` | `servico_indisponivel` (config, timeout, 429, 503, rede, 4xx) |
| `ExtracaoInvalidaError` | `resposta_invalida` (fora do schema, não é nota, sem itens, sem total) |

---

## 8. AgentClassificador (GR-11)

`AgentClassificador(cliente=None).classificar(nota: NotaFiscalExtraida) -> ClassificacaoDespesa{tipo_despesa, justificativa}`.

- Envia ao Gemini só o fornecedor (razão social e nome fantasia), os itens (descrição, quantidade, total) e o valor total. **Não envia CPF, CNPJ, faturado, datas nem parcelas.**
- **`TipoDespesa`, 2 categorias no MVP:**
  - `MANUTENCAO_E_OPERACAO`: máquinas, veículos, diesel, lubrificantes, peças;
  - `INFRAESTRUTURA_E_UTILIDADES`: hidráulica, elétrica, construção.

**Exceções:**

| Exceção | `codigo` |
| --- | --- |
| `ClassificacaoIndisponivelError` | `servico_indisponivel` |
| `ClassificacaoInvalidaError` | `classificacao_invalida` |
| `ClassificacaoInconclusivaError` | `classificacao_inconclusiva` (itens fora das 2 categorias) |

---

## 9. Orquestração `processar_documento` (GR-12)

`documentos/processamento.py`. **É a única função que a interface precisa chamar para processar.**

### 9.1 API

```python
from documentos.processamento import processar_documento, DocumentoEmProcessamentoError

processar_documento(documento_id, *, extrator=None, classificador=None) -> Documento
```

| Estado ao chamar | Resultado |
| --- | --- |
| `PENDENTE` ou `ERRO` | processa → retorna o `Documento` em `CONCLUIDO` ou `ERRO` (falhas **não são relançadas**) |
| `CONCLUIDO` | retorna o `Documento` sem chamar os Agents (**sem gasto de cota**) |
| `PROCESSANDO` | lança `DocumentoEmProcessamentoError` (`codigo="documento_em_processamento"`, mensagem "O documento já está sendo processado.") |
| inexistente | lança `Documento.DoesNotExist` |
| falha ao gravar o próprio `ERRO` (ex.: banco fora) | a exceção sobe (caso excepcional) |

### 9.2 Fluxo

```
_reservar  (transaction.atomic + select_for_update; transação curta que TERMINA antes dos Agents)
  → PROCESSANDO
  → AgentExtrator.extrair_documento()  → AgentClassificador.classificar(nota)
  → _montar_resultado()  → _registrar_sucesso() → CONCLUIDO
  falha: ExtratorError / ClassificadorError / Exception inesperada → _registrar_erro() → ERRO
```

- **Concorrência:** uma segunda chamada simultânea espera o lock, encontra `PROCESSANDO` e recebe `DocumentoEmProcessamentoError` sem chamar Agents. Isso foi testado com duas threads e conexões reais ao PostgreSQL.
- **Duração:** síncrona; de segundos até cerca de 6 min no pior caso (2 chamadas × 3 tentativas × 60 s).

### 9.3 JSON final (`resultado_estruturado`, só em `CONCLUIDO`)

```json
{
  "fornecedor": {"razao_social": "...", "nome_fantasia": "...", "cnpj": "11222333000181"},
  "faturado": {"nome": "...", "cpf": "99999999999"},
  "numero_nota": "000123",
  "data_emissao": "2026-09-20",
  "itens": [{"descricao": "...", "quantidade": "2", "valor_unitario": "500.00", "valor_total": "1000.00"}],
  "quantidade_parcelas": 1,
  "parcelas": [{"numero": 1, "data_vencimento": "2026-10-20", "valor": "1500.00"}],
  "valor_total": "1500.00",
  "tipo_despesa": "MANUTENCAO_E_OPERACAO",
  "validacoes": {
    "fornecedor_cnpj": {"status": "valido", "motivo": null},
    "faturado_cpf": {"status": "invalido", "motivo": "digitos_verificadores_invalidos"}
  }
}
```

(Valores fictícios.) Não contém `documento_e_nota_fiscal` nem `justificativa`.

⚠️ O PostgreSQL (`jsonb`) **não preserva a ordem das chaves** ao ler de volta. A interface deve reordenar para exibir (seção 15.3).

### 9.4 Metadados

**`CONCLUIDO`:**

```json
{"processamento": {
   "versao_resultado": 1, "iniciado_em": "<ISO>", "finalizado_em": "<ISO>",
   "extracao": {"versao_schema": 1, "modelo": "<modelo>"},
   "classificacao": {"versao_schema": 1, "modelo": "<modelo>", "justificativa": "<texto>"}}}
```

**`ERRO`** (invariante: todo `ERRO` passa por `_registrar_erro`):

```json
{"processamento": {"versao_resultado": 1, "iniciado_em": "<ISO>", "finalizado_em": "<ISO>"},
 "erro": {"etapa": "extracao|classificacao|processamento", "codigo": "<codigo>", "mensagem": "<mensagem segura>"}}
```

- Em `ERRO`, `resultado_estruturado = {}`, e **nunca** há `extracao`, `classificacao` ou `justificativa`, nem mesmo se o save final de sucesso falhar.
- **Nunca persistidos:** traceback, `__cause__`, status HTTP, resposta bruta do Gemini, API Key.
- `metadados["erro"]["mensagem"]` **já é segura para exibir na tela.**

### 9.5 Mapa de erros (o que a tela pode mostrar)

| `etapa` / `codigo` | Mensagem gravada | Sugestão para o usuário (GR-14) |
| --- | --- | --- |
| `extracao` / `documento_ilegivel` | "Não foi possível ler o arquivo PDF do documento." | envie o PDF novamente |
| `extracao` / `servico_indisponivel` | "Serviço de extração indisponível no momento." | tente novamente mais tarde |
| `extracao` / `resposta_invalida` | "Não foi possível extrair dados válidos da nota fiscal." ou "O documento enviado não foi reconhecido como nota fiscal." | confira se o PDF é uma nota fiscal |
| `classificacao` / `servico_indisponivel` | "Serviço de classificação indisponível no momento." | tente novamente mais tarde |
| `classificacao` / `classificacao_invalida` | "A classificação retornada não é válida." | tente novamente |
| `classificacao` / `classificacao_inconclusiva` | "A despesa não se encaixa nas categorias disponíveis no MVP." | limitação atual (2 categorias) |
| `processamento` / `erro_interno` | "Erro inesperado ao processar o documento." | tente novamente; se persistir, avise a equipe |

### 9.6 Teste manual real da GR-12 (concluído)

Teste ponta a ponta com a **Gemini API real** e o PDF fictício `uploads/teste-gr10/danfe (ciclano - pecas).pdf`.

- **1ª tentativa:** falhou **antes dos Agents**, porque a tabela `documentos_documento` não existia no banco local (a migration `documentos.0001_initial` estava pendente). Foi resolvida com `python manage.py migrate`, e depois não havia mais migrations pendentes.
- **2ª tentativa:** sucesso.
  - `Documento` criado no PostgreSQL e `processar_documento()` executado, terminando em **`CONCLUIDO`**;
  - `quantidade_parcelas = 1` e `tipo_despesa = MANUTENCAO_E_OPERACAO`;
  - CNPJ `valido`; CPF fictício preservado e `invalido`;
  - metadados do Extrator e do Classificador gravados, com a justificativa e sem `erro`.
- **Verificação no banco:**

  ```
  ID: 1 | STATUS: CONCLUIDO | TEM RESULTADO: True | TIPO DESPESA: MANUTENCAO_E_OPERACAO | QUANTIDADE PARCELAS: 1 | TEM ERRO: False
  ```

  O documento ID 1 fica no banco local e é útil para conferir visualmente a página de detalhe na GR-14 **sem gastar cota**.

---

# Parte III — GR-14: interface Web (concluída na branch)

## 10. Progresso, estado da interface e validação manual

### 10.1 Etapas

| Etapa | Conteúdo | Situação |
| --- | --- | --- |
| **1** | `documentos/urls.py`; upload JSON movido (mesma URL e nome); helper `_salvar_documento`; testes do caminho 500 | ✅ concluída |
| **2** | raiz `/`; `documento_inicio` (tela de envio + upload HTML + recentes); `base.html`, `inicio.html`, `documentos.css` | ✅ concluída |
| **3** | página de detalhe, apresentação por status, resumo, avisos, justificativa, JSON ordenado, erro seguro; upload → detalhe; links na lista | ✅ concluída |
| **4** | botão **Processar / Tentar novamente funcional**: `documento_processar` → `processar_documento(pk)` (GR-12) | ✅ concluída |
| **5** | `documentos.js`: proteção **visual** contra clique duplo + texto "Enviando..."/"Processando..." nos botões | ✅ concluída |
| **6** | validação manual no navegador (com **uma** execução real da Gemini) + auditoria Git final + relatório | ✅ concluída (seção 10.3) |

### 10.2 Como está a interface hoje

| Item | Situação real |
| --- | --- |
| Telas | `/documentos/` (envio + recentes com link) e `/documentos/<id>/` (detalhe). Também o Django Admin |
| Raiz `/` | 302 → `/documentos/`; anônimo → `/admin/login/?next=/documentos/` |
| Upload pela tela | `DocumentoUploadForm` → `_salvar_documento` → redirect para `/documentos/<id>/` |
| Upload JSON (GR-7) | inalterado (`POST /documentos/upload/`) |
| **Processamento pela tela** | ✅ `PENDENTE` → botão **Processar**; `ERRO` → **Tentar novamente**. Ambos são `<form method="post">` com CSRF para `/documentos/<id>/processar/` |
| Detalhe | `PROCESSANDO` com refresh de 5 s; `CONCLUIDO` com resumo, avisos, justificativa e JSON; `ERRO` com mensagem segura, sugestão e nova tentativa |
| Atividade do professor | ✅ **fluxo completo validado no navegador:** carregar o PDF → botão → JSON na tela (seção 10.3) |
| JavaScript | `documentos.js` (carregado com `defer` pelo `base.html`) desabilita o botão e troca o texto nos 3 formulários marcados com `data-submit-lock`; **só melhoria visual** (seção 14.1) |
| Templates / static | `base.html`, `inicio.html`, `detalhe.html`, `documentos.css`; settings **não alterados** |
| Acesso | `@staff_member_required` em todas as páginas |

### 10.3 Validação manual no navegador (etapa 6) — concluída

Feita com o **`runserver` local**, a **Gemini API real** e o PDF **fictício** `uploads/teste-gr10/danfe (ciclano - pecas).pdf`, que é ignorado pelo Git.

| Passo | Resultado real |
| --- | --- |
| `python manage.py migrate` | "No migrations to apply." |
| `python manage.py runserver` | iniciou normalmente; system check sem problemas |
| `/documentos/` | carregou; `documentos.css` e `documentos.js` com **HTTP 200**; documento anterior (ID 1) listado como `CONCLUIDO` |
| Único 404 observado | `/favicon.ico`: **irrelevante** para a atividade (o navegador pede o ícone automaticamente); **não exige correção** |
| Upload pelo navegador do PDF fictício | **Documento ID 2** criado; redirect para `/documentos/2/`; status inicial `PENDENTE`; botão "Processar" exibido |
| "Processar" pela interface | `documento_processar` → `processar_documento` → `AgentExtrator` → `AgentClassificador`, **com a Gemini real** → `CONCLUIDO`; mensagem **"Processamento concluído."** |

**Resultado exibido na página do Documento ID 2** (documento de demonstração fictício):

| Campo do resumo | Valor exibido |
| --- | --- |
| Tipo de despesa | Manutenção e operação |
| Valor total | R$ 3.086,75 |
| Quantidade de parcelas | 1 |
| Fornecedor | IGUACU MAQUINAS AGRICOLAS LTDA |
| Número da nota | 000.084.682 |
| Data de emissão | 19/09/2025 |

- **Validação local:** o CPF fictício do faturado foi sinalizado como "com dígitos verificadores inválidos", **sem impedir o processamento** (política da seção 7).
- **Justificativa da classificação:** exibida corretamente.
- **JSON final:** exibido formatado, com os campos da atividade (fornecedor, faturado, número, data, itens, `quantidade_parcelas`, parcelas, valor total, `tipo_despesa`, `validacoes`).
- **Nenhum dado interno da Gemini exposto na tela:** nem modelo, nem resposta bruta, nem status HTTP, nem chave.

**Fluxo exigido pela atividade, validado ponta a ponta:**

```
upload PDF → Documento PENDENTE → botão Processar → GR-12 → AgentExtrator → AgentClassificador
          → JSON final → CONCLUIDO → resultado exibido no navegador
```

Os documentos ID 1 e ID 2 e seus arquivos em `media/`, ignorado pelo Git, existem só no **banco e disco locais**.

---

## 11. Arquitetura

**Django templates + HTML + 1 CSS + 1 JS mínimo.** Sem frontend separado, framework, CDN, build, Node/npm ou dependências novas.

1. ✅ **Upload por formulário HTML** (`DocumentoUploadForm`, validação da GR-8 intacta) + PRG para o detalhe.
2. ✅ **`_salvar_documento`** compartilhado pelo endpoint JSON e pela tela.
3. ✅ **Apresentação só lê** `status`, `resultado_estruturado` e `metadados` (contrato da GR-12).
4. ✅ **Processamento em POST separado**, disparado por botão. **A única entrada é `processar_documento(pk)`.** `views.py` importa apenas `processar_documento` e `DocumentoEmProcessamentoError` de `documentos.processamento`, e não menciona `agents`, `AgentExtrator`, `AgentClassificador`, `GeminiClient` nem `genai` (há teste).
5. ✅ **Processamento síncrono** na requisição do botão (sem threads ou filas). `PROCESSANDO` se atualiza sozinho com `meta refresh` (sem JS). ✅ O JS da etapa 5 dá só **proteção visual** contra clique duplo. A **proteção real contra concorrência** continua na GR-12 (`transaction.atomic()` + `select_for_update()` → `DocumentoEmProcessamentoError`).
6. ✅ **Acesso** `@staff_member_required` + **CSRF** em todos os POSTs.
7. ✅ **Sem simulação**; ✅ **sem alterar** models, migrations, forms, validators, `processamento.py`, `agents/**` e settings.

```
Navegador                                    Django (documentos/views.py)                          Backend
─────────                                    ────────────────────────────                          ───────
GET  /                           ─► RedirectView → /documentos/
GET  /documentos/                ─► documento_inicio (form + 10 recentes com link)
POST /documentos/  (PDF)         ─► documento_inicio ─► DocumentoUploadForm ─► validar_pdf       (GR-8)
                                         └ válido → _salvar_documento → redirect /documentos/<id>/
GET  /documentos/<id>/           ─► documento_detalhe → helpers de apresentação → detalhe.html
POST /documentos/<id>/processar/ ─► documento_processar ─► processar_documento(pk)                (GR-12)
                                         │                    └─► AgentExtrator (GR-10) → AgentClassificador (GR-11)
                                         └ messages + redirect /documentos/<id>/
POST /documentos/upload/         ─► upload_documento (JSON)                                       (GR-7)
```

---

## 12. Fluxo da GR-14 (implementado)

```
1. Usuário abre /  → /documentos/  (login do admin se necessário)
2. Tela inicial: formulário "Enviar nota fiscal" + "Documentos recentes" (nome → detalhe)
3. "Enviar PDF"
      ├─ inválido → mesma tela, mensagem do form no campo; nenhum Documento
      ├─ falha ao salvar → mesma tela, "Não foi possível salvar o documento."
      └─ válido → Documento PENDENTE → /documentos/<id>/ + "Documento “<nome>” enviado."
4. Página do documento (PENDENTE): "Pronto para processar." + botão "Processar" (form POST + CSRF)
5. "Processar" → POST /documentos/<id>/processar/ → processar_documento(pk)   (segundos a minutos; síncrono)
      ├─ CONCLUIDO           → "Processamento concluído."                           (success)
      ├─ ERRO                → "O processamento falhou. Veja os detalhes abaixo."   (error)
      ├─ já em processamento → "O documento já está sendo processado."              (info)
      ├─ inexistente         → 404
      └─ falha excepcional   → "Não foi possível processar o documento agora. Tente novamente mais tarde." (error)
      → sempre redirect para /documentos/<id>/
6. CONCLUIDO: resumo + avisos + justificativa + JSON final   (sem botão; não reprocessa)
   ERRO:      mensagem segura + sugestão + "Tentar novamente" (form POST + CSRF)
   PROCESSANDO (outra aba): "Processando..." + refresh de 5 s (sem botão)
```

---

## 13. URLs e views

### 13.1 URLs (todas implementadas)

| Método | URL | Nome | View |
| --- | --- | --- | --- |
| GET | `/` | `inicio` | `RedirectView(pattern_name="documento_inicio")` (em `config/urls.py`) |
| GET, POST | `/documentos/` | `documento_inicio` | `documento_inicio` |
| POST | `/documentos/upload/` | `documento_upload` | `upload_documento` (JSON, GR-7) |
| GET | `/documentos/<int:pk>/` | `documento_detalhe` | `documento_detalhe` |
| POST | `/documentos/<int:pk>/processar/` | `documento_processar` | `documento_processar` |

**Sem `app_name`** (nomes globais).

### 13.2 Views e helpers (`documentos/views.py`)

| Nome | Tipo | Comportamento |
| --- | --- | --- |
| `_salvar_documento(arquivo)` | helper | cria o `Documento` (`PENDENTE`); se o save falhar depois de gravar o arquivo, remove-o e relança |
| `upload_documento` | view (`staff`, `POST`) | JSON da GR-7: 201 · 400 · 500 |
| `documento_inicio` | view (`staff`, `GET/POST`) | form + 10 recentes; POST válido → `_salvar_documento` → `messages.success` → redirect `documento_detalhe`; `DatabaseError`/`OSError` → erro geral seguro |
| `documento_detalhe` | view (`staff`, `GET`) | `get_object_or_404`; `CONCLUIDO` → `resumo`, `avisos`, `justificativa`, `json_resultado`; `ERRO` → `erro` (`mensagem`, `sugestao`). Só leitura |
| **`documento_processar`** | view (`staff`, `POST`) | chama **somente** `processar_documento(pk)` e traduz o resultado em mensagem + redirect (seção 13.3) |
| `_dicionario`, `_json_ordenado`, `_rotulo_tipo_despesa`, `_formatar_moeda`, `_formatar_data`, `_resumo`, `_avisos_validacao`, `_justificativa`, `_erro_para_exibir` | helpers | apresentação (seção 15) |

Constantes: `LIMITE_DOCUMENTOS_RECENTES`, `MENSAGEM_FALHA_AO_SALVAR`, `MENSAGEM_PROCESSAMENTO_CONCLUIDO`, `MENSAGEM_PROCESSAMENTO_FALHOU`, `MENSAGEM_FALHA_INESPERADA`, `CHAVES_RESULTADO`, `ROTULOS_TIPO_DESPESA`, `AVISOS_VALIDACAO`, `MENSAGEM_ERRO_PADRAO`, `SUGESTAO_ERRO_PADRAO`, `SUGESTOES_ERRO`. Há um `logger` do módulo.

### 13.3 `documento_processar` (implementada)

```python
@staff_member_required
@require_POST
def documento_processar(request, pk):
    try:
        documento = processar_documento(pk)
    except Documento.DoesNotExist:
        raise Http404("Documento não encontrado.")
    except DocumentoEmProcessamentoError as exc:
        messages.info(request, str(exc))                       # "O documento já está sendo processado."
    except Exception:
        # Só falhas excepcionais escapam do serviço (ex.: banco indisponível).
        logger.exception("Falha inesperada ao processar o documento %s pela interface.", pk)
        messages.error(request, MENSAGEM_FALHA_INESPERADA)
    else:
        if documento.status == Documento.Status.CONCLUIDO:
            messages.success(request, MENSAGEM_PROCESSAMENTO_CONCLUIDO)
        elif documento.status == Documento.Status.ERRO:
            messages.error(request, MENSAGEM_PROCESSAMENTO_FALHOU)
    return redirect("documento_detalhe", pk=pk)
```

- **Erros normais de Extrator e Classificador não chegam como exceção:** a GR-12 já os grava como `Documento` em `ERRO`, e a view só lê o status.
- **`CONCLUIDO` é idempotente:** o serviço devolve o documento sem chamar os Agents (sem gasto de cota), e a view mostra "Processamento concluído.".
- O serviço recebe **apenas o `pk`**. Nenhum parâmetro do request (ex.: `api_key`, `modelo`) é repassado; há teste.

---

## 14. Templates, CSS e JS

| Arquivo | Etapa | Conteúdo real |
| --- | --- | --- |
| `templates/documentos/base.html` | 2 (+3, +5) | `lang="pt-BR"`, viewport, CSS via `{% static %}`, **`<script src="{% static 'documentos/documentos.js' %}" defer>`** (etapa 5), `{% block head_extra %}`, topo com "Enviar nota", `messages`, `{% block conteudo %}` |
| `templates/documentos/inicio.html` | 2 (+3, +5) | formulário de upload (multipart, CSRF, `accept`, `required`, **`data-submit-lock data-submit-texto="Enviando..."`**), erros do form, limite de MB, tabela de recentes com link para o detalhe |
| `templates/documentos/detalhe.html` | 3 (+4, +5) | voltar; nome, selo, data; `PENDENTE`: form POST "Processar"; `PROCESSANDO`: mensagem + meta refresh; `CONCLUIDO`: resumo, avisos, justificativa, JSON; `ERRO`: mensagem, sugestão e form POST "Tentar novamente". Os 2 forms de processamento têm **`data-submit-lock data-submit-texto="Processando..."`** (etapa 5) |
| `static/documentos/documentos.css` | 2 (+3) | layout, mensagens, formulário, tabela, selos, detalhe, resumo, avisos, erro, bloco JSON. Etapa 4 sem mudanças de CSS |
| `static/documentos/documentos.js` | **5** | proteção visual contra clique duplo (seção 14.1) |

Nenhum template usa `|safe` ou `autoescape off`, nem JS inline (há testes).

### 14.1 `documentos.js` — como funciona

- **Onde age:** só em `form[data-submit-lock]`, ou seja, nos 3 formulários marcados: **upload** (`inicio.html`), **Processar** e **Tentar novamente** (`detalhe.html`). Não se aplica automaticamente a outros forms.
- **No 1º submit:** marca o form (`data-enviando="true"`), guarda o texto original do botão, troca o texto via **`textContent`** para o valor de `data-submit-texto` ("Enviar PDF" → "Enviando..."; "Processar"/"Tentar novamente" → "Processando..."), desabilita o botão (`disabled` + `aria-busy`). **Não cancela o envio:** o POST HTML normal segue, com CSRF, e o navegador espera a resposta do processamento síncrono.
- **Em um 2º submit** enquanto o 1º está em curso (ex.: Enter repetido): `preventDefault()`, e só nesse ramo.
- **Voltar pelo histórico** (`pageshow` com `persisted`): restaura o botão e o texto original, para a página não ficar travada.
- **Não usa:** `fetch`, AJAX/`XMLHttpRequest`, `setInterval`, polling, WebSocket, `innerHTML`, `eval` nem bibliotecas. Não recebe nem conhece chave, modelo, metadados ou PDF. `PROCESSANDO` continua com `meta refresh` de 5 s, **sem** JS.
- **Sem JavaScript**, tudo funciona igual (upload, Processar, Tentar novamente, CSRF). O JS é **só melhoria visual**.
- **A proteção real contra processamento concorrente continua na GR-12** (lock no banco): mesmo com JS desativado, ou com duas abas, a segunda execução recebe "O documento já está sendo processado.".
- Validação local: `node --check documentos.js` OK. O Node **não** é dependência do projeto; foi só uma verificação de sintaxe na máquina.

---

## 15. Apresentação por status, JSON e erros

### 15.1 Por status

| Status | O que aparece | Botão |
| --- | --- | --- |
| `PENDENTE` | "Pronto para processar." + "O processamento pode levar alguns minutos." | **Processar**: `<form method="post" action="/documentos/<id>/processar/">` + CSRF |
| `PROCESSANDO` | "Processando... a página atualiza automaticamente." + `<meta http-equiv="refresh" content="5">` **só nesse status** | nenhum |
| `CONCLUIDO` | resumo + avisos de validação + justificativa + JSON final | nenhum (não reprocessa pela interface) |
| `ERRO` | "O processamento não foi concluído." + `metadados.erro.mensagem` + sugestão pelo `codigo` | **Tentar novamente**: mesmo form POST + CSRF |

### 15.2 `CONCLUIDO`

- **Resumo:** tipo de despesa (rótulo amigável), valor total (`R$ 1.500,00`), quantidade de parcelas (inclusive `0`), fornecedor, número e data da nota (`20/09/2026`); ausentes → "—".
- **Rótulos:** `MANUTENCAO_E_OPERACAO` → "Manutenção e operação"; `INFRAESTRUTURA_E_UTILIDADES` → "Infraestrutura e utilidades"; valor desconhecido aparece como veio, escapado.
- **Avisos:** "CNPJ do fornecedor com dígitos verificadores inválidos." / "CPF do faturado com dígitos verificadores inválidos.", seguidos de "Isso não impediu o processamento. A verificação confere apenas o formato e os dígitos verificadores, não a existência do documento."
- **Justificativa:** só se existir em `metadados.processamento.classificacao.justificativa`.
- **JSON:** `json.dumps(ordenado, ensure_ascii=False, indent=2)` na ordem de `CHAVES_RESULTADO` (chaves desconhecidas no fim), em `<pre>` com escape automático.
- **Nunca aparecem:** modelo Gemini, versões de schema, datas de processamento ou outras chaves de `metadados`.

### 15.3 `ERRO` — sugestões por `codigo`

| `codigo` | Sugestão |
| --- | --- |
| `documento_ilegivel` | "Envie o arquivo PDF novamente." |
| `servico_indisponivel` | "Tente novamente mais tarde." |
| `resposta_invalida` | "Confira se o arquivo enviado é uma nota fiscal válida." |
| `classificacao_invalida` | "Tente novamente." |
| `classificacao_inconclusiva` | "Os itens da nota não se encaixaram nas categorias de despesa disponíveis no MVP (Manutenção e operação; Infraestrutura e utilidades)." |
| `erro_interno` e código desconhecido | "Tente novamente. Se o problema persistir, avise a equipe." |

- Sem `mensagem` → "Não foi possível processar o documento."
- Nunca aparecem `etapa`, `codigo`, traceback, `__cause__`, status HTTP, resposta da Gemini, API Key ou modelo.

### 15.4 Mensagens flash de `documento_processar`

| Situação | Tag | Texto |
| --- | --- | --- |
| `CONCLUIDO` | success | "Processamento concluído." |
| `ERRO` | error | "O processamento falhou. Veja os detalhes abaixo." |
| `DocumentoEmProcessamentoError` | info | "O documento já está sendo processado." |
| falha excepcional (fora do serviço) | error | "Não foi possível processar o documento agora. Tente novamente mais tarde." (detalhe **só** no log via `logger.exception`) |

### 15.5 Robustez

`resultado_estruturado`/`metadados` que não sejam objetos, ou chaves ausentes, não quebram a página.

---

## 16. Arquivos

### 16.1 Criados na GR-14

| Arquivo | Etapa |
| --- | --- |
| `documentos/urls.py` (`""`, `upload/`, `<int:pk>/`, `<int:pk>/processar/`) | 1–4 |
| `documentos/templates/documentos/base.html` | 2 (+3, +5) |
| `documentos/templates/documentos/inicio.html` | 2 (+3, +5) |
| `documentos/templates/documentos/detalhe.html` | 3 (+4, +5) |
| `documentos/static/documentos/documentos.css` | 2 (+3) |
| `documentos/static/documentos/documentos.js` | 5 |
| `documentos/test_interface.py` (83 testes) | 2–5 |

### 16.2 Modificados na GR-14

| Arquivo | Mudança |
| --- | --- |
| `config/urls.py` | `include("documentos.urls")` (1) + raiz `inicio` (2) |
| `documentos/views.py` | `_salvar_documento` (1); `documento_inicio` (2); `documento_detalhe` + apresentação, e upload redirecionando ao detalhe (3); **`documento_processar`, import de `processar_documento`/`DocumentoEmProcessamentoError`, `logger` e mensagens de processamento (4)** |
| `documentos/test_upload.py` | +4 testes (1); 8 originais inalterados |
| `analisetemporaria.md` | este registro |

### 16.3 Arquivos do commit da GR-14 (lista exata)

```
analisetemporaria.md
config/urls.py
documentos/views.py
documentos/urls.py
documentos/test_upload.py
documentos/test_interface.py
documentos/templates/documentos/base.html
documentos/templates/documentos/inicio.html
documentos/templates/documentos/detalhe.html
documentos/static/documentos/documentos.css
documentos/static/documentos/documentos.js
```

A etapa 6 não criou nem alterou código; só este relatório. **Não** entram `.env`, `uploads/` nem `media/` (ignorados pelo `.gitignore`).

### 16.4 Não alterados (e não precisam mudar)

`documentos/processamento.py`, `forms.py`, `validators.py`, `models.py`, `migrations/*`, `admin.py`, `tests.py`, `test_processamento.py`, `agents/**`, `config/settings.py`, `requirements.txt`, `.env.example`, `financeiro/*` e `usuarios/*`. Conferido com `git diff --stat`, que sai vazio para esses caminhos. **Na etapa 5, `views.py`, `urls.py` e `config/urls.py` também não mudaram** (contratos de views e URLs preservados).

---

## 17. Testes

### 17.1 Estado atual

| Comando | Resultado |
| --- | --- |
| `python manage.py test documentos.test_interface` | **83 — OK** |
| `python manage.py test documentos.test_processamento` | **49 — OK** (GR-12, inalterado) |
| `python manage.py test documentos.test_upload` | **12 — OK** |
| `python manage.py test documentos` | **147 — OK** |
| `python manage.py test` | **303 — OK** |
| `python manage.py check` | OK |
| `git diff --check` | OK |

### 17.2 `documentos/test_interface.py` (83 testes)

Todos usam `InterfaceTestMixin`: `MEDIA_ROOT` temporário, staff logado e `genai.Client` patchado para falhar. **Nenhum teste chama a API real da Gemini.**

| Classe | Testes | Cobre |
| --- | --- | --- |
| `AcessoTests` | 6 | raiz; staff 200; anônimo e não-staff → login; 405 |
| `TelaInicialTests` | 8 | formulário; limite; lista vazia; máx. 10 em ordem; status; escape; nada interno; link para o detalhe |
| `UploadHtmlTests` | 7 | upload válido → detalhe; mensagem na página do documento; `_salvar_documento`; inválidos; limite; sem validação duplicada; **`views.py` só processa via `processar_documento`** (não menciona `agents`, `AgentExtrator`, `AgentClassificador`, `GeminiClient`, `genai`) |
| `UploadHtmlFalhaAoSalvarTests` | 2 | falha no banco e no storage → erro seguro, sem arquivo órfão |
| `RegressaoUploadJsonTests` | 2 | endpoint JSON da GR-7 |
| `DetalheAcessoTests` | 7 | acesso, 404, 405, nome/data/voltar, escape, sem `/media/` |
| `DetalhePendenteTests` | 1 | "Pronto para processar." + **form POST com CSRF, `action` correto, botão não desabilitado e marcado com `data-submit-lock`**; abrir a página não chama o serviço |
| `DetalheProcessandoTests` | 2 | mensagem + refresh de 5 s, sem botão; refresh ausente nos outros status |
| `DetalheConcluidoTests` | 13 | resumo, rótulos, justificativa, avisos, JSON ordenado e escapado, nada interno, sem botão, robustez |
| `DetalheErroTests` | 5 | mensagem + sugestão + **form POST "Tentar novamente" com CSRF**; 6 códigos; desconhecido; escape; nada interno |
| `SegurancaTemplatesTests` | 1 | sem `|safe` e sem `autoescape off` |
| **`ProcessarRotaEAcessoTests`** | 5 | `reverse` → `/documentos/<pk>/processar/`; GET/PUT/DELETE/PATCH → 405 sem chamar o serviço; anônimo e não-staff → login sem chamar o serviço; **CSRF obrigatório** (403 sem token, com `enforce_csrf_checks`); o token do formulário da página é aceito |
| **`ProcessarEstadosDaPaginaTests`** | 1 | `PROCESSANDO` e `CONCLUIDO` sem botão, form ou link de processamento |
| **`ProcessarServicoMockadoTests`** | 7 | `processar_documento` chamado **1×** com o `pk`; parâmetros do request (`api_key`, `modelo`…) não são repassados; `CONCLUIDO` → "Processamento concluído."; `ERRO` → "O processamento falhou. Veja os detalhes abaixo."; `DocumentoEmProcessamentoError` → mensagem info; `DoesNotExist` → 404; exceção inesperada → mensagem genérica, `logger.exception` com traceback no log e nada interno na página |
| **`ProcessarIntegracaoTests`** | 4 | **`processar_documento` real** com `AgentExtrator`/`AgentClassificador` falsos, patchados em `documentos.processamento`, e `GEMINI_API_KEY=None`: **(A)** sucesso → `CONCLUIDO`, `tipo_despesa`, `quantidade_parcelas = 1`, `valor_total` persistidos, redirect para o detalhe, página com rótulo, valor, aviso de CPF, justificativa e JSON, sem modelo; **(B)** falha do Extrator → `ERRO`, `{}`, Classificador não chamado, mensagem segura + sugestão + "Tentar novamente"; **(C)** falha do Classificador → `ERRO`, `{}`, sem dados da extração nos metadados nem na página; `CONCLUIDO` não reprocessa |
| **`JavaScriptTests`** | 12 | `documentos.js` existe e é achado pelo `staticfiles`; `base.html` carrega `<script src="/static/documentos/documentos.js" defer>`; form de upload com `data-submit-lock` + "Enviando...", `method="post"` e CSRF; forms de Processar/Tentar novamente marcados, com "Processando..."; `PROCESSANDO`/`CONCLUIDO` sem form marcado; `PROCESSANDO` mantém o `meta refresh`; o JS só age em `form[data-submit-lock]`, usa `textContent` e `disabled`; `preventDefault` só no 2º envio (não cancela o 1º); o JS não tem `fetch`, `XMLHttpRequest`, `WebSocket`, `setInterval`, `innerHTML`/`outerHTML`/`insertAdjacentHTML`, `eval`, `new Function` nem `document.write`; o JS não menciona Gemini, chave, modelo, metadados nem PDF; templates sem `fetch(`, `XMLHttpRequest` nem `<script>` inline; o fluxo upload → processar funciona como POST HTML puro, sem executar JS |

Sem navegador automatizado no projeto (nada de Selenium/Playwright/Node/npm), o comportamento no navegador foi conferido na **validação manual da etapa 6** (seção 10.3): CSS e JS carregados (HTTP 200), upload, processamento real e exibição do resultado.

---

## 18. Riscos

| # | Risco | Mitigação |
| --- | --- | --- |
| R1 | **Requisição longa:** o POST de Processar espera o serviço síncrono (até cerca de 6 min) | aceitável com `runserver`; o botão mostra "Processando..." e fica desabilitado (JS); outra aba mostra `PROCESSANDO` com refresh. Em produção com timeout de worker → execução em segundo plano (tarefa futura) |
| R2 | Documento preso em `PROCESSANDO` (processo interrompido) | mudar para `ERRO` no Django Admin; depois o botão "Tentar novamente" funciona |
| R3 | **Duplo clique / duas abas** | proteção **real** na GR-12 (lock + `DocumentoEmProcessamentoError` → mensagem info), que vale mesmo sem JS; ✅ proteção **visual** no `documentos.js` (botão desabilitado + "Processando...") |
| R4 | **Cota da Gemini:** cada POST em `PENDENTE`/`ERRO` faz 2 chamadas | só por botão explícito; `CONCLUIDO` não reprocessa (testado) |
| R5 | XSS | escape automático, sem `|safe`; testado em nome, JSON, tipo desconhecido, mensagem de erro |
| R6 | Exposição do PDF | sem link para arquivo/`MEDIA` (testado) |
| R7 | `DEBUG=False` → sem CSS no `runserver` | `DJANGO_DEBUG=True` em desenvolvimento |
| R8 | Acesso só para staff | `python manage.py createsuperuser` |
| R9 | Refatoração do upload JSON | ✅ mitigado |
| R10 | Ordem das chaves do JSON | ✅ mitigado |
| R11 | `classificacao_inconclusiva` frequente (2 categorias) | sugestão explica a limitação do MVP |
| R12 | Banco local sem migrations | `python manage.py migrate` (seção 21.3) |
| R13 | Mensagem de arquivo vazio vem do Django ("O arquivo submetido está vázio.") | comportamento existente; `forms.py` não alterado |
| R14 | CSRF em POST de processamento | ✅ testado: sem token → 403 e o serviço não é chamado |
| R15 | Botão travado ao voltar pelo histórico (cache do navegador) | ✅ `pageshow` restaura botão e texto |
| R16 | JS não testado em navegador automatizado | testes estáticos do arquivo e da marcação + ✅ validação manual no navegador (etapa 6); a página funciona sem JS |
| R17 | `/favicon.ico` retorna 404 no `runserver` | **irrelevante**: pedido automático do navegador, sem impacto na atividade; não exige correção |

---

## 19. Decisões

| # | Decisão | Situação |
| --- | --- | --- |
| D1 | Upload por formulário HTML + PRG; endpoint JSON mantido | ✅ |
| D2 | `_salvar_documento` compartilhado | ✅ |
| D3 | Processamento **síncrono**, em POST separado, por botão | ✅ etapa 4 |
| D4 | `@staff_member_required` + CSRF | ✅ |
| D5 | Botão "Copiar JSON" | **descartado** nesta tarefa: não é pedido pela atividade; o JSON já pode ser selecionado e copiado no `<pre>`; `navigator.clipboard` exige contexto seguro (funciona em `localhost`, não em HTTP pela rede); manter o JS mínimo. Pode ser adicionado depois sem mudar o backend |
| D6 | Raiz `/` → `/documentos/` | ✅ |
| D7 | 10 documentos recentes | ✅ |
| D8 | Resumo + avisos acima do JSON | ✅ |
| D9 | Upload redireciona para o detalhe | ✅ |
| D10 | Botões de processamento | ✅ **forms POST reais** em `PENDENTE` ("Processar") e `ERRO` ("Tentar novamente"); nenhum botão em `PROCESSANDO`/`CONCLUIDO` |
| D11 | Apresentação em helpers de `views.py` | ✅ |
| D13 | JavaScript | ✅ **opt-in** por `data-submit-lock` (não pega todo `<form>`); texto temporário em `data-submit-texto`; carregado com `defer` no `base.html`; `PROCESSANDO` continua com `meta refresh` |
| D12 | Tratamento de exceções na view | `DoesNotExist` → 404; `DocumentoEmProcessamentoError` → info; `Exception` → `logger.exception` + mensagem genérica; **sem reinterpretar** erros de Extrator/Classificador (já são `ERRO` no `Documento`) |

---

## 20. Ordem de implementação e próximos passos

1. ✅ **Etapa 1:** rotas do app + `_salvar_documento` + testes do caminho 500.
2. ✅ **Etapa 2:** raiz, `documento_inicio`, `base.html`, `inicio.html`, `documentos.css`.
3. ✅ **Etapa 3:** `documento_detalhe`, `detalhe.html`, apresentação por status, redirect do upload, links.
4. ✅ **Etapa 4:** `documento_processar` + rota; botões viram forms POST com CSRF; testes de rota, acesso, CSRF, serviço mockado e integração real sem Gemini.
5. ✅ **Etapa 5:** `documentos.js` (proteção visual contra clique duplo), 3 forms marcados; "Copiar JSON" descartado (D5).
6. ✅ **Etapa 6:** validação manual no navegador com **uma** execução real da Gemini (Documento ID 2 → `CONCLUIDO`, seção 10.3); auditoria final da branch (arquivos protegidos intocados; `.env`, `uploads/` e `media/` ignorados; nenhuma chave em arquivos versionáveis); suíte completa, `check` e `git diff --check` OK.

**Próximos passos (somente com autorização):**

1. `git add` dos arquivos da seção 16.3 → `git diff --cached` (conferir que `.env`, `uploads/` e `media/` não entram).
2. Commit com a mensagem sugerida: `feat(documentos): implementar interface web GR-14`.
3. Push da branch `feature/GR-14-interface-web` e PR para a `main`.
4. Depois do merge: **GR-21 — validação final** (seção 23).

---

# Parte IV — Operação

## 21. Guia da Gemini API

### 21.1 Conferir a configuração sem expor a chave

```bash
python manage.py shell -c 'from django.conf import settings; print("API Key carregada:", bool(settings.GEMINI_API_KEY)); print("Modelo:", settings.GEMINI_MODEL)'
```

- Esperado: `API Key carregada: True` e `Modelo: <modelo configurado>`. **Nunca** use `print(settings.GEMINI_API_KEY)`.
- `.env`: `GEMINI_API_KEY=`, `GEMINI_MODEL=`, `GEMINI_TIMEOUT_SEGUNDOS=60`, `GEMINI_MAX_TENTATIVAS=3`.
- O modelo vem **só** de `GEMINI_MODEL` (`.env` → `settings` → `GeminiClient.modelo` → `/v1beta/models/<modelo>:generateContent`). Os dois Agents usam o mesmo.
- Cada `manage.py shell` relê o `.env`. **O `runserver` precisa ser reiniciado** depois de alterar o `.env`.
- ⚠️ Uma **variável exportada no terminal vence o `.env`** (`load_dotenv()` não sobrescreve). Confira com `echo $GEMINI_MODEL` e remova com `unset GEMINI_MODEL`.

### 21.2 Retry e timeout

- **Retry:** 3 tentativas no total por chamada, feitas pelo SDK (408/429/500/502/503/504, timeout, conexão). Não crie retry manual. Não resolve cota diária esgotada.
- **Timeout:** 60 s por tentativa. Pior caso por documento (2 chamadas) ≈ 6 min.

### 21.3 Diagnóstico por sintoma

| Sintoma | Significado | Ação | Bug do projeto? |
| --- | --- | --- | --- |
| `GeminiAPIError 503` UNAVAILABLE ("high demand") | modelo sobrecarregado | aguardar; tentar depois; outro modelo só para diagnóstico | ❌ externo |
| `GeminiAPIError 429` RESOURCE_EXHAUSTED ("quota exceeded", `free_tier_requests`) | cota do **projeto Google** | AI Studio → projeto certo → **Uso** e **Limite de taxa**; aguardar a janela; **não repetir em loop** | ❌ externo |
| `GeminiTimeoutError` | lento, indisponível ou rede | conferir serviço, conexão e PDF | ❌ normalmente externo |
| `GeminiAPIError None` | falha de rede | conferir conexão | ❌ |
| `GeminiAPIError 400/401/403` | chave inválida ou sem permissão | conferir chave e projeto | ❌ configuração |
| `GeminiAPIError 404` | modelo inexistente ou com nome errado | conferir `GEMINI_MODEL` | ❌ configuração |
| `GeminiConfiguracaoError` | chave ou modelo ausentes | preencher o `.env` | ❌ configuração |
| `resposta_invalida` / `classificacao_invalida` | a API respondeu, mas o conteúdo não passou na validação | ver no log os caminhos dos campos | ⚠️ documento ou modelo |
| `classificacao_inconclusiva` | itens fora das 2 categorias | esperado no MVP | ❌ |
| `validacoes.*.status = "invalido"` | CPF/CNPJ com DV inválido; nota aceita | nenhuma | ❌ |
| `relation "documentos_documento" does not exist` | banco local sem migrations | `python manage.py showmigrations` → `python manage.py migrate` | ❌ ambiente |
| Aviso "Both GOOGLE_API_KEY and GEMINI_API_KEY are set" | há `GOOGLE_API_KEY` no ambiente | inofensivo | ❌ |
| Aviso "Direct use of automatic function calling (AFC)…" | aviso padrão do SDK | nenhuma | ❌ |

- No `Documento`, erros de serviço aparecem como `metadados["erro"]["codigo"] == "servico_indisponivel"`. O status HTTP exato (429/503) fica **só no log** dos Agents (`... indisponível (GeminiAPIError, status=429)`).
- Na GR-14, a tela mostra a mensagem segura. Para diagnosticar, olhe o **terminal do `runserver`**.

### 21.4 Modelos já testados

Resultado do momento de cada teste; nada é permanente.

| Modelo | Observado |
| --- | --- |
| `gemini-3.8-flash` | 503 e depois 429 por cota; usável em outro momento |
| `gemini-3.7-flash` | 503 |
| `gemini-3.5-flash-lite` | processou o PDF com structured output |

### 21.5 Teste manual do processamento pelo shell (API real; uma vez só)

```bash
python manage.py shell -c '
import json
from django.core.files import File
from documentos.models import Documento
from documentos.processamento import processar_documento

with open("uploads/teste-gr10/danfe (ciclano - pecas).pdf", "rb") as f:
    doc = Documento.objects.create(arquivo=File(f, name="danfe-teste.pdf"), nome_original="danfe-teste.pdf")
doc = processar_documento(doc.pk)
print("id:", doc.pk, "status:", doc.status)
print(json.dumps(doc.resultado_estruturado, ensure_ascii=False, indent=2))
print("erro:", json.dumps(doc.metadados.get("erro"), ensure_ascii=False))
'
```

Para ver os avisos dos Agents, acrescente `import logging; logging.basicConfig(level=logging.WARNING)` no início.

### 21.6 Se a Gemini parar de funcionar

1. Não altere código.
2. Confira a chave e o modelo (21.1).
3. Leia `metadados["erro"]` (na tela ou no admin) e o log do terminal.
4. 429 → cota; 503 → aguardar; timeout → serviço, rede e PDF.
5. CPF/CNPJ inválido ou classificação inconclusiva **não** são falha da API.
6. Rode `python manage.py test`, que não chama a API real.
7. Só altere código se testes ou auditoria indicarem defeito interno.

---

## 22. Checklist de segurança

Situação na auditoria final da GR-14:

- [x] `.env` nunca vai para o Git (`git check-ignore -v .env` → `.gitignore:12`; não rastreado).
- [x] A API Key nunca aparece em commit, PR, chat, log, **tela** ou documentação. Se vazar, revogue no AI Studio. *(Confirmado: o valor real e padrões de chave Google estão ausentes de todos os arquivos versionáveis; a tela não mostra chave.)*
- [x] `uploads/` e `media/` continuam ignorados; notas fiscais reais nunca são versionadas (`.gitignore:20` e `:19`; não rastreados).
- [x] A interface não expõe PDFs por URL, nem traceback, `__cause__`, status HTTP ou modelo em uso (testes + validação manual).
- [x] Formulários com `{% csrf_token %}`; nada de `|safe` em conteúdo vindo do banco (testes de CSRF e de templates).
- [x] Testes automatizados nunca chamam a API real; documentos de teste são fictícios.
- [x] Antes do commit: `git status` e `git diff` (executados na auditoria final).
- [ ] Antes do commit: `git diff --cached`. **Pendente:** só pode ser executado depois do `git add`.

---

## 23. Depois da GR-14: GR-21

| Tarefa | Entrega |
| --- | --- |
| **GR-21 — Validação final** (próxima tarefa, depois do merge da GR-14) | a partir da `main` já com a GR-14: repetir o fluxo no navegador com PDF fictício (login → enviar PDF → processar → JSON), conferir **cada campo exigido pela atividade** (seção 1), incluindo `tipo_despesa` e `quantidade_parcelas`; conferir mensagens de erro (PDF inválido, `ERRO` com “Tentar novamente”); rodar a suíte completa. A etapa 6 da GR-14 já antecipou boa parte disso (seção 10.3) |
| Melhorias futuras (fora do escopo atual) | processamento em segundo plano (R1); destravar `PROCESSANDO` automaticamente; ampliar `TipoDespesa` (R11); vincular `Titular` e gerar `LancamentoFinanceiro`/`Parcela` |

```
Navegador → upload (GR-7/8) → Documento → botão Processar (GR-14) → processar_documento (GR-12)
          → Extrator (GR-10) → Classificador (GR-11) → JSON final → tela (GR-14) → validação (GR-21)
```

---

## 24. Estado do Git

| Item | Estado |
| --- | --- |
| Branch | `feature/GR-14-interface-web` |
| Base | `main` em `292ee0c` (merge da GR-12, PR #12) |
| GR-14 | **concluída (etapas 1–6) e pronta para commit/PR**; aguardando autorização |
| Alterações atuais (sem commit) | `M analisetemporaria.md` · `M config/urls.py` · `M documentos/test_upload.py` · `M documentos/views.py` · `?? documentos/static/` · `?? documentos/templates/` · `?? documentos/test_interface.py` · `?? documentos/urls.py` (11 arquivos, seção 16.3) |
| Arquivos protegidos | **intocados**: `documentos/processamento.py`, `models.py`, `forms.py`, `validators.py`, `migrations/`, `agents/`, `config/settings.py`, `requirements.txt` |
| Auditoria de segredos | `.env` (`.gitignore:12`), `uploads/` (`.gitignore:20`) e `media/` (`.gitignore:19`) ignorados e não rastreados; valor real da `GEMINI_API_KEY` e padrões de chave Google **ausentes** de todos os arquivos versionáveis |
| `git add` / commit / push / PR | **não realizados** |
| `.env` / `uploads/` / `media/` | ignorados e não rastreados |
| Banco local | migrations aplicadas ("No migrations to apply."); documentos de teste ID 1 e ID 2 em `CONCLUIDO` |
