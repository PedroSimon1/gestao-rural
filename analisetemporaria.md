# Gestão Rural — Documento de handoff (estado atual e GR-12 implementada)

> **Para que serve este arquivo:** quem abrir só este documento deve conseguir entender o projeto, o que o professor pediu, o que já foi concluído, como os Agents e a orquestração funcionam hoje e o que falta para terminar a atividade.
>
> **Estado atual:** GR-12 com **implementação e teste manual real concluídos** na branch `feature/GR-12-orquestracao`, aguardando validação final no Git, commit, push, PR e merge.
>
> **Fonte de verdade:** o código da branch. Contratos, números de linha e contagem de testes abaixo foram conferidos no código atual.
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

**Parte II — Componentes já mergeados**
5. [Documento, upload e validação (GR-6/7/8)](#5-documento-upload-e-validação-gr-678)
6. [GeminiClient (GR-9)](#6-geminiclient-gr-9)
7. [AgentExtrator (GR-10)](#7-agentextrator-gr-10)
8. [AgentClassificador (GR-11)](#8-agentclassificador-gr-11)
9. [Compatibilidade GR-10 → GR-11](#9-compatibilidade-gr-10--gr-11)

**Parte III — GR-12: orquestração implementada**
10. [Visão geral e API](#10-visão-geral-e-api)
11. [Fluxo real de `processar_documento`](#11-fluxo-real-de-processar_documento)
12. [Reserva transacional e concorrência](#12-reserva-transacional-e-concorrência)
13. [JSON final (`resultado_estruturado`)](#13-json-final-resultado_estruturado)
14. [Metadados](#14-metadados)
15. [Máquina de estados](#15-máquina-de-estados)
16. [Tratamento de erros](#16-tratamento-de-erros)
17. [Persistência](#17-persistência)
18. [Decisões tomadas (D1–D9)](#18-decisões-tomadas-d1d9)
19. [Testes da GR-12](#19-testes-da-gr-12)
20. [Contrato para a GR-14](#20-contrato-para-a-gr-14)
21. [Riscos](#21-riscos)

**Parte IV — Operação e próximos passos**
22. [Guia da Gemini API](#22-guia-da-gemini-api)
23. [Checklist de segurança](#23-checklist-de-segurança)
24. [Teste manual real e o que falta](#24-teste-manual-real-e-o-que-falta)
25. [Estado do Git](#25-estado-do-git)

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
| Parcelas | **Quantidade de parcelas**, Data de vencimento |
| Financeiro | Valor total |
| Classificação | **TipoDespesa** |

**Observações do enunciado:**

- Não é necessário criar uma entidade Produto.
- Deve existir estrutura para **múltiplas parcelas**.
- `TipoDespesa` **não** é copiado do PDF: é **interpretado pelo Gemini com base nos produtos**.

**Avaliação:**

| Peso | Critério |
| --- | --- |
| 40% | Uso do Agent conforme a estrutura |
| 30% | Conteúdo do JSON |
| 30% | Assertividade da classificação da despesa |

**Fluxo exigido:**

```
PDF → Agents (extração + classificação) → JSON → interface Web
```

---

## 2. Estado das tarefas

| Tarefa | Descrição | Situação | Evidência |
| --- | --- | --- | --- |
| GR-6 | Modelar `Documento` | ✅ mergeada | PR #6 |
| GR-7 | Upload de PDF | ✅ mergeada | PR #7 |
| GR-8 | Validação de PDF | ✅ mergeada | PR #8 |
| GR-9 | `GeminiClient` compartilhado | ✅ mergeada | PR #9 |
| GR-10 | Agent Extrator | ✅ mergeada | PR #10 (`c8ec436`) |
| GR-11 | Agent Classificador | ✅ mergeada | PR #11 (`1aa95b2`, merge `e25d47d`) |
| **GR-12** | **Orquestração PDF → Agents → JSON** | 🟡 **implementação e teste real concluídos na branch; aguardando validação Git, commit, push, PR e merge** | `documentos/processamento.py`, `documentos/test_processamento.py`; teste real (seção 24.1) |
| GR-14 | Interface Web | ⏳ pendente; depois da GR-12 | — |
| GR-21 | Validação final | ⏳ pendente | — |

```
GR-6 → GR-7 → GR-8 ──────────────┐
GR-9 → GR-10 → GR-11 ────────────┼─► GR-12 (orquestração) ─► GR-14 (interface) ─► GR-21 (validação final)
```

**Testes atuais** (nenhum chama a API real):

| Comando | Resultado |
| --- | --- |
| `python manage.py test documentos.test_processamento` | **49 testes — OK** |
| `python manage.py test documentos` | **60 testes — OK** |
| `python manage.py test` | **216 testes — OK** |
| `python manage.py check` | OK |
| `git diff --check` | OK |

Composição da suíte: 55 do projeto base + 86 do Extrator + 26 do Classificador + 49 da GR-12.

---

## 3. Estrutura atual do projeto

```
gestao-rural/
├── config/
│   ├── settings.py              load_dotenv(); PostgreSQL; MAX_PDF_UPLOAD_SIZE_MB; GEMINI_*
│   └── urls.py                  admin/ e documentos/upload/
├── documentos/                  GR-6/7/8 + GR-12
│   ├── models.py                Documento
│   ├── views.py                 upload_documento (POST, JSON)
│   ├── forms.py                 DocumentoUploadForm → validar_pdf
│   ├── validators.py            validar_pdf
│   ├── processamento.py         GR-12 — processar_documento (NOVO)
│   ├── test_processamento.py    GR-12 — 49 testes (NOVO)
│   ├── tests.py, test_upload.py
│   ├── admin.py                 DocumentoAdmin (status editável)
│   └── migrations/0001_initial.py
├── agents/                      pacote Python (não está em INSTALLED_APPS; sem models)
│   ├── gemini_client.py         GR-9 — único ponto de contato com o SDK google-genai
│   ├── test_gemini_client.py
│   ├── extrator/                GR-10 — agent.py, schemas.py, test_agent.py, test_schemas.py
│   └── classificador/           GR-11 — agent.py, schemas.py, test_agent.py, test_schemas.py
├── financeiro/                  LancamentoFinanceiro, Parcela, Amortizacao (não usados pelo fluxo)
├── usuarios/                    Usuario, Titular(nome, cpf)
├── uploads/teste-gr10/          PDF fictício de demonstração — IGNORADO pelo Git
├── .env                         segredos locais — IGNORADO pelo Git
├── .env.example                 modelo sem valores reais
└── analisetemporaria.md         este documento
```

- Não há templates, static nem telas próprias: só o Django Admin (`/admin/`) e o endpoint JSON de upload (GR-14).
- Hoje o processamento é chamado **por código** (`processar_documento`); ainda não há botão nem endpoint HTTP.

---

## 4. Projeto × atividade

| Requisito | Situação | Implementação | Tarefa | O que falta |
| --- | --- | --- | --- | --- |
| Receber, armazenar e validar PDF | ✅ | `POST /documentos/upload/`, `Documento`, `validar_pdf` | GR-6/7/8 | tela (GR-14) |
| Cliente Gemini | ✅ | `GeminiClient` | GR-9 | — |
| Agent de extração | ✅ | `AgentExtrator` | GR-10 | — |
| Fornecedor, faturado, nº nota, data, itens, parcelas, vencimentos, valor total | ✅ | `NotaFiscalExtraida` | GR-10 | — |
| Múltiplas parcelas | ✅ | lista `parcelas` | GR-10 | — |
| Validação local de CPF/CNPJ | ✅ (extra) | `validacoes` | GR-10 | — |
| Agent de classificação / **TipoDespesa** | ✅ | `AgentClassificador` | GR-11 | — |
| Extração + classificação encadeadas | ✅ (branch) | `processar_documento` | **GR-12** | merge |
| **Quantidade de parcelas explícita** | ✅ (branch) | `quantidade_parcelas = len(parcelas)` | **GR-12** | merge |
| **JSON final completo e persistido** | ✅ (branch) | `Documento.resultado_estruturado` | **GR-12** | merge |
| Estados do processamento | ✅ (branch) | `PENDENTE → PROCESSANDO → CONCLUIDO/ERRO` | **GR-12** | merge |
| Erros integrados e seguros | ✅ (branch) | `metadados["erro"]` | **GR-12** | merge |
| Botão de processamento / JSON na tela | ⏳ | — | GR-14 | interface |
| Validação final ponta a ponta | ⏳ | — | GR-21 | — |

**O que a GR-12 trouxe:** os dois Agents, antes isolados, agora formam o caminho `Documento → Extrator → Classificador → JSON final → Documento`, com estado e erro gravados no banco. Falta só a camada Web (GR-14): um botão que chame `processar_documento` e uma tela que leia o `Documento`.

---

# Parte II — Componentes já mergeados

## 5. Documento, upload e validação (GR-6/7/8)

### 5.1 `Documento` (`documentos/models.py`)

| Campo | Tipo | Valor após upload | Quem altera |
| --- | --- | --- | --- |
| `arquivo` | `FileField(upload_to="documentos/")` | PDF em `MEDIA_ROOT/documentos/` | ninguém (somente leitura) |
| `nome_original` | `CharField(255)` | nome sanitizado | — |
| `enviado_em` | `DateTimeField(auto_now_add)` | data do upload | — |
| `status` | `PENDENTE`, `PROCESSANDO`, `CONCLUIDO`, `ERRO` | `PENDENTE` | **GR-12** |
| `titular` | FK `Titular`, `null=True` | `None` | fora do escopo atual |
| `resultado_estruturado` | `JSONField(default=dict)` | `{}` | **GR-12** |
| `metadados` | `JSONField(default=dict)` | `{}` | **GR-12** |

- Os `JSONField` usam o encoder padrão, que **não aceita `Decimal`/`date`**. Por isso a GR-12 usa `model_dump(mode="json")`.
- O `DocumentoAdmin` permite editar `status`, o que serve para destravar um documento manualmente (seção 21, R1).

### 5.2 Upload (GR-7) e validação (GR-8)

- `POST /documentos/upload/` (`name="documento_upload"`), com `@staff_member_required` e `@require_POST`.
- Respostas JSON: `201 {id, nome_original, status}`, `400 {"erro": "<mensagem>"}` e `500 {"erro": "Não foi possível salvar o documento."}`.
- `validar_pdf` confere:
  - extensão `.pdf`;
  - arquivo não vazio;
  - tamanho até 10 MB (`MAX_PDF_UPLOAD_SIZE_MB`);
  - `content_type` igual a `application/pdf`;
  - cabeçalho `%PDF-`;
  - e sanitiza o nome.
- Mesmo assim, o Extrator confere de novo (arquivo ausente, vazio ou sem `%PDF-`), cobrindo documentos criados por outros caminhos ou arquivos removidos do disco.

---

## 6. GeminiClient (GR-9)

`agents/gemini_client.py`, o único ponto do projeto que fala com o SDK `google-genai` 2.24.0.

```python
GeminiClient(*, api_key=None, modelo=None, timeout_segundos=None, max_tentativas=None)
    .modelo
    .gerar_conteudo(conteudo, *, instrucao_sistema=None, schema_resposta=None,
                    tipo_resposta=None, temperatura=None) -> str
    .gerar_json(conteudo, *, instrucao_sistema=None, schema_resposta=None,
                temperatura=None) -> dict | list
```

- **Configuração:** vem de `settings`: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SEGUNDOS` (60, **por tentativa**) e `GEMINI_MAX_TENTATIVAS` (3, **no total**).
- **Retry:** fica a cargo do SDK, que repete os HTTP 408, 429, 500, 502, 503 e 504, além de timeout e falha de conexão.
- **Exceções**, todas herdando de `GeminiError`:
  - `GeminiConfiguracaoError`;
  - `GeminiTimeoutError`;
  - `GeminiAPIError(status_code)` (com status, ou `None` para erro de rede);
  - `GeminiRespostaInvalidaError`.
- As mensagens nunca contêm a chave.
- **A GR-12 não usa o `GeminiClient` diretamente:** cada Agent cria o seu de forma preguiçosa.

---

## 7. AgentExtrator (GR-10)

`agents/extrator/agent.py` + `agents/extrator/schemas.py`.

### 7.1 API

```python
AgentExtrator(cliente=None)                   # GeminiClient criado na 1ª extração se None
  .modelo -> str | None                       # None antes da 1ª extração
  .extrair(pdf_bytes: bytes) -> NotaFiscalExtraida
  .extrair_documento(documento) -> NotaFiscalExtraida   # lê documento.arquivo pelo storage; NÃO altera o Documento
```

### 7.2 `NotaFiscalExtraida` (Pydantic v2)

| Campo | Tipo | Obrigatório | Normalização / validação |
| --- | --- | --- | --- |
| `documento_e_nota_fiscal` | `bool` | sim | o agent rejeita `False` |
| `fornecedor.razao_social` / `nome_fantasia` | `str \| None` | não | espaços colapsados; `""` → `None` |
| `fornecedor.cnpj` | `str \| None` | não | 14 caracteres `[0-9A-Z]{12}\d{2}`, maiúsculas; DV não bloqueia |
| `faturado.nome` | `str \| None` | não | espaços colapsados |
| `faturado.cpf` | `str \| None` | não | 11 dígitos; DV não bloqueia |
| `numero_nota` | `str \| None` | não | como impresso |
| `data_emissao` | `date \| None` | não | só `AAAA-MM-DD` |
| `itens[]` | `list[Item]` | sim (agent exige ≥ 1) | ordem preservada |
| `itens[].descricao` | `str` | sim | não vazia |
| `itens[].quantidade` | `Decimal \| None` | não | ≥ 0, sem quantizar |
| `itens[].valor_unitario` / `valor_total` | `Decimal \| None` | não | ≥ 0, 2 casas |
| `parcelas[]` | `list[ParcelaExtraida]` | sim (pode ser `[]`) | ordem preservada; sem número → 1..n; parcial ou repetida → erro |
| `parcelas[].data_vencimento` | `date \| None` | não | `AAAA-MM-DD` |
| `parcelas[].valor` | `Decimal` | sim | > 0, 2 casas |
| `valor_total` | `Decimal` | sim | > 0, 2 casas, < 10.000.000.000 |
| `validacoes` | `@computed_field` | calculado | **não** vem do Gemini; aparece no `model_dump` |

`VERSAO_SCHEMA = 1`. `model_dump(mode="json")` produz dinheiro como string (`"1500.00"`), datas ISO e inclui `validacoes`.

### 7.3 Exceções

Base `ExtratorError` (`codigo = "erro_extracao"`), que não herda de `GeminiError`.

| Exceção | `codigo` | Causa |
| --- | --- | --- |
| `DocumentoIlegivelError` | `documento_ilegivel` | sem arquivo, arquivo removido ou inacessível, vazio, sem `%PDF-`. **O Gemini não é chamado** |
| `ExtracaoIndisponivelError` | `servico_indisponivel` | configuração, timeout, `GeminiAPIError` (429, 503, rede, 400/401/403/404) |
| `ExtracaoInvalidaError` | `resposta_invalida` | resposta fora do schema, estrutura de CPF/CNPJ impossível, não é nota fiscal, sem itens, sem total |

### 7.4 Política de CPF/CNPJ

1. **Dado extraído:** o Gemini **copia** o número do documento.
2. **Validade matemática:** a aplicação normaliza, **preserva** e valida os DVs (`cpf_dv_valido`, `cnpj_dv_valido`), sinalizando o resultado em `validacoes`.
3. **Existência real:** **não é verificada**. DV válido não prova que a pessoa ou empresa existe.

- DV inválido **não descarta a nota** e o número não vira `null`. Exemplo fictício: `999.999.999-99` → `"99999999999"`, com `faturado_cpf = {"status": "invalido", "motivo": "digitos_verificadores_invalidos"}`.
- Sequências repetidas são tratadas como inválidas.
- O CNPJ alfanumérico (IN RFB 2.229/2024) é suportado.
- Estrutura impossível continua rejeitada.
- **Na GR-12:** `validacoes` é preservado no JSON final, e `status == "invalido"` **não** é erro de processamento.

### 7.5 Teste real com PDF (GR-10)

- Arquivo `uploads/teste-gr10/danfe (ciclano - pecas).pdf`, fictício e **ignorado pelo Git**.
- O Gemini leu o PDF, extraiu todos os campos (vários itens, parcela, total) e o structured output passou no schema.
- O CNPJ saiu `valido` e o CPF fictício saiu `invalido`, com a nota aceita. É a evidência de que a aplicação não confia cegamente no Gemini.

---

## 8. AgentClassificador (GR-11)

`agents/classificador/agent.py` + `agents/classificador/schemas.py`.

### 8.1 API e entrada

```python
AgentClassificador(cliente=None)
  .modelo -> str | None
  .classificar(nota: NotaFiscalExtraida) -> ClassificacaoDespesa
```

- Recebe **diretamente** um `NotaFiscalExtraida`. Qualquer outro tipo, não-nota ou nota sem itens → `ClassificacaoInvalidaError`.
- **Dados enviados ao Gemini**, somente:
  - `fornecedor.razao_social` e `nome_fantasia`;
  - `itens[].descricao`, `quantidade` e `valor_total`;
  - `valor_total`.
  - **CPF, CNPJ, faturado, datas e parcelas não são enviados.**
- A chamada usa `gerar_json(..., schema_resposta=ClassificacaoDespesa, temperatura=0)`.

### 8.2 `ClassificacaoDespesa`

| Campo | Tipo | Regra |
| --- | --- | --- |
| `tipo_despesa` | `TipoDespesa \| None` (Enum `str`) | o agent **nunca retorna `None`**: vira `ClassificacaoInconclusivaError` |
| `justificativa` | `str` | 1 a 500 caracteres |

**Categorias do MVP (`TipoDespesa`):**

- `MANUTENCAO_E_OPERACAO`: máquinas, equipamentos, veículos (diesel, lubrificante, peças);
- `INFRAESTRUTURA_E_UTILIDADES`: infraestrutura e utilidades (materiais hidráulicos, elétricos, de construção).

Não existe campo de confiança. `VERSAO_SCHEMA = 1`.

### 8.3 Exceções

Base `ClassificadorError` (`codigo = "erro_classificacao"`), que não herda de `ExtratorError` nem de `GeminiError`.

| Exceção | `codigo` | Causa |
| --- | --- | --- |
| `ClassificacaoIndisponivelError` | `servico_indisponivel` | configuração, timeout, `GeminiAPIError` |
| `ClassificacaoInvalidaError` | `classificacao_invalida` | entrada inválida, `GeminiRespostaInvalidaError`, `ValidationError` |
| `ClassificacaoInconclusivaError` | `classificacao_inconclusiva` | `tipo_despesa = null` (itens fora das 2 categorias) |

---

## 9. Compatibilidade GR-10 → GR-11

- **Diretamente compatíveis.** `classificador.classificar(extrator.extrair_documento(doc))` funciona sem adaptação.
- **Reuso do `GeminiClient`:** os dois o reutilizam corretamente (criação preguiçosa, só `gerar_json`, schema Pydantic, `temperatura=0`, capturam só `GeminiError`).
- **Nenhum problema de contrato exigiu alterar `agents/`.** As observações foram resolvidas na GR-12:

| # | Observação | Como a GR-12 trata |
| --- | --- | --- |
| C1 | hierarquias de exceção separadas | captura `ExtratorError` e `ClassificadorError` separadamente |
| C2 | `servico_indisponivel` existe nas duas | grava também `etapa` (`extracao` / `classificacao`) |
| C3 | inconclusivo vira exceção | `ERRO` com `classificacao_inconclusiva` (D3) |
| C4 | só 2 categorias no MVP | risco R5 (fora do escopo da GR-12) |
| C5 | a `description` de `tipo_despesa` some na conversão do SDK | instrução está no prompt de sistema; sem impacto |
| C6 | 2 chamadas ao Gemini por documento | cota e tempo dobram (R2/R3) |

---

# Parte III — GR-12: orquestração implementada

## 10. Visão geral e API

**Arquivos criados:**

| Arquivo | Linhas | Conteúdo |
| --- | --- | --- |
| `documentos/processamento.py` | 214 | serviço de orquestração |
| `documentos/test_processamento.py` | 930 | 49 testes |

**Nenhum outro arquivo de código foi alterado:** `agents/**`, models, migrations, views, forms, validators, `config/**` e `requirements.txt` estão intactos, e não houve migration.

**API pública:**

```python
from documentos.processamento import processar_documento, DocumentoEmProcessamentoError

processar_documento(documento_id, *, extrator=None, classificador=None) -> Documento
```

| Parâmetro | Uso |
| --- | --- |
| `documento_id` | pk do `Documento`. O serviço sempre relê o estado atual do banco |
| `extrator` | opcional; se `None`, cria `AgentExtrator()` (só quando o documento é reservado) |
| `classificador` | opcional; se `None`, cria `AgentClassificador()` |

| Resultado | Quando |
| --- | --- |
| retorna o `Documento` em `CONCLUIDO` | sucesso, ou documento que já estava `CONCLUIDO` |
| retorna o `Documento` em `ERRO` | qualquer falha de extração, classificação ou inesperada (**não é relançada**) |
| lança `DocumentoEmProcessamentoError` | documento já em `PROCESSANDO` |
| lança `Documento.DoesNotExist` | pk inexistente |
| lança a exceção original | só se a **gravação do próprio `ERRO`** falhar (ex.: banco fora) |

**Onde fica cada parte (`documentos/processamento.py`):**

| Linha | Nome | Papel |
| --- | --- | --- |
| 21 | `VERSAO_RESULTADO = 1` | versão do JSON final |
| 23 | `MENSAGEM_ERRO_INTERNO` | "Erro inesperado ao processar o documento." |
| 26 | `ProcessamentoError` | base (`codigo="erro_processamento"`) |
| 36 | `DocumentoEmProcessamentoError` | `codigo="documento_em_processamento"`, "O documento já está sendo processado." |
| 41 | `_reservar(documento_id)` | transação curta com lock → `PROCESSANDO` |
| 76 | `_montar_resultado(nota, classificacao)` | função pura → JSON final |
| 100 | `_erro_seguro(documento, etapa, exc)` | monta `{etapa, codigo, mensagem}` + `logger.warning` |
| 112 | `_registrar_sucesso(...)` | grava `CONCLUIDO` |
| 127 | `_registrar_erro(documento, erro)` | grava `ERRO` (**único caminho para `ERRO`**) |
| 144 | `_executar(...)` | cria os Agents se necessário e roda Extrator → Classificador → sucesso |
| 184 | `processar_documento(...)` | função pública; captura erro inesperado no limite |

Responsabilidades que **não** estão no serviço: SDK e `GeminiClient` (ficam nos Agents); prompts e schemas (Agents); regras de CPF/CNPJ (Extrator); validação de upload (GR-8); HTTP, templates e `JsonResponse` (GR-14); `LancamentoFinanceiro`, `Parcela` e `Titular` (fora do escopo).

---

## 11. Fluxo real de `processar_documento`

```
processar_documento(documento_id, *, extrator=None, classificador=None)
 │
 ├─ 1. _reservar(documento_id)                         ← transação curta (seção 12)
 │       PENDENTE ou ERRO → PROCESSANDO → segue
 │       CONCLUIDO        → return documento           (Agents não são criados nem chamados)
 │       PROCESSANDO      → raise DocumentoEmProcessamentoError   (nada é alterado)
 │       inexistente      → raise Documento.DoesNotExist
 │     ── a transação terminou; daqui em diante nenhuma transação fica aberta ──
 │
 ├─ 2. try: erro = _executar(documento, extrator, classificador)
 │       ├─ cria AgentExtrator() / AgentClassificador() se não foram injetados
 │       ├─ nota = extrator.extrair_documento(documento)
 │       │     ExtratorError      → return _erro_seguro("extracao", exc)
 │       ├─ classificacao = classificador.classificar(nota)     ← o MESMO objeto NotaFiscalExtraida
 │       │     ClassificadorError → return _erro_seguro("classificacao", exc)
 │       ├─ resultado = _montar_resultado(nota, classificacao)
 │       └─ _registrar_sucesso(documento, resultado, {extracao, classificacao})   → CONCLUIDO; return None
 │    except Exception:                                ← limite do serviço
 │       logger.exception(...)
 │       erro = {"etapa": "processamento", "codigo": "erro_interno", "mensagem": MENSAGEM_ERRO_INTERNO}
 │       (inclui falha no save final de sucesso)
 │
 ├─ 3. if erro: _registrar_erro(documento, erro)       → ERRO   (se esta gravação falhar, a exceção sobe)
 │
 └─ 4. return documento
```

---

## 12. Reserva transacional e concorrência

### 12.1 Implementação (`_reservar`)

```python
with transaction.atomic():
    documento = Documento.objects.select_for_update().get(pk=documento_id)   # lock da linha
    if documento.status == PROCESSANDO: raise DocumentoEmProcessamentoError()
    if documento.status == CONCLUIDO:   return documento, False
    metadados = dict(documento.metadados)
    metadados.pop("erro", None)                                               # limpa erro anterior
    metadados["processamento"] = {"versao_resultado": 1,
                                  "iniciado_em": timezone.now().isoformat()}  # recriado do zero
    documento.metadados = metadados
    documento.status = PROCESSANDO
    documento.save(update_fields=["status", "metadados"])
# ← a transação TERMINA aqui, antes de qualquer chamada aos Agents/Gemini
return documento, True
```

- A transação cobre **somente**:
  - leitura com lock;
  - verificação do estado;
  - limpeza do erro anterior;
  - criação de `processamento` com `iniciado_em`;
  - status `PROCESSANDO`;
  - `save`.
- **Nenhuma transação fica aberta durante os Agents**, que podem levar minutos: isso prenderia conexão e lock. Há um teste que verifica exatamente isso.
- O bloco `processamento` é **recriado** a cada tentativa. Outras chaves de `metadados`, se existirem, são preservadas.

### 12.2 Concorrência

Se duas execuções começam ao mesmo tempo:

1. a primeira obtém o lock e reserva (`PROCESSANDO`);
2. a segunda **fica bloqueada** no `select_for_update` até a primeira confirmar;
3. depois encontra `PROCESSANDO`, lança `DocumentoEmProcessamentoError` e **não altera nada nem chama Agents**.

**Teste real** (`ReservaConcorrenteTests`, `TransactionTestCase`): duas threads com **conexões separadas ao PostgreSQL**. A primeira segura o lock; a segunda comprovadamente continua bloqueada após 0,5 s; ao liberar, a segunda recebe `DocumentoEmProcessamentoError` e os metadados continuam intactos. Numa verificação de mutação (com `select_for_update` desativado), o teste **falhou**, confirmando que detecta a ausência do lock.

---

## 13. JSON final (`resultado_estruturado`)

Contrato implementado (`_montar_resultado`), montado a partir de `nota.model_dump(mode="json")` e `classificacao.model_dump(mode="json")`. Valores genéricos/fictícios:

```json
{
  "fornecedor": {"razao_social": "...", "nome_fantasia": "...", "cnpj": "11222333000181"},
  "faturado": {"nome": "...", "cpf": "99999999999"},
  "numero_nota": "000123",
  "data_emissao": "2026-09-20",
  "itens": [
    {"descricao": "...", "quantidade": "2", "valor_unitario": "500.00", "valor_total": "1000.00"}
  ],
  "quantidade_parcelas": 2,
  "parcelas": [
    {"numero": 1, "data_vencimento": "2026-10-20", "valor": "750.00"},
    {"numero": 2, "data_vencimento": "2026-11-20", "valor": "750.00"}
  ],
  "valor_total": "1500.00",
  "tipo_despesa": "MANUTENCAO_E_OPERACAO",
  "validacoes": {
    "fornecedor_cnpj": {"status": "valido", "motivo": null},
    "faturado_cpf": {"status": "invalido", "motivo": "digitos_verificadores_invalidos"}
  }
}
```

| Chave | Regra |
| --- | --- |
| `quantidade_parcelas` | `int`, **explícito**, `= len(parcelas)` (0 para nota à vista) |
| `tipo_despesa` | **string** do Enum (`MANUTENCAO_E_OPERACAO` ou `INFRAESTRUTURA_E_UTILIDADES`) |
| `validacoes` | preservado da extração |
| dinheiro / datas | strings `"1500.00"` / ISO, serializáveis pelo `JSONField` |
| **Não contém** | `documento_e_nota_fiscal` (é sempre `true` quando se chega aqui) e `justificativa` (vai para os metadados) |

O `jsonb` do PostgreSQL **não garante a ordem das chaves** ao ler de volta. Se a ordem importar na tela, a GR-14 reordena.

---

## 14. Metadados

### 14.1 Sucesso (`CONCLUIDO`)

```json
{
  "processamento": {
    "versao_resultado": 1,
    "iniciado_em": "<ISO, gravado na reserva e preservado>",
    "finalizado_em": "<ISO>",
    "extracao": {"versao_schema": 1, "modelo": "<extrator.modelo>"},
    "classificacao": {
      "versao_schema": 1,
      "modelo": "<classificador.modelo>",
      "justificativa": "<justificativa da classificação>"
    }
  }
}
```

- `modelo` é lido de `agent.modelo` **depois** das chamadas (cliente preguiçoso).
- Não existe `erro`, e os metadados **não duplicam dados da nota**.

### 14.2 Erro (`ERRO`)

**Invariante:** **todo** caminho que termina em `ERRO` passa por `_registrar_erro`, que **reconstrói** `processamento` do zero.

```json
{
  "processamento": {
    "versao_resultado": 1,
    "iniciado_em": "<ISO da reserva>",
    "finalizado_em": "<ISO>"
  },
  "erro": {"etapa": "<extracao|classificacao|processamento>", "codigo": "<codigo>", "mensagem": "<mensagem segura>"}
}
```

- `resultado_estruturado = {}`.
- `processamento` contém **somente** `versao_resultado`, `iniciado_em` e `finalizado_em`. **Nunca** `extracao`, `classificacao` ou `justificativa`.
- `erro` contém **somente** `etapa`, `codigo` e `mensagem`.
- A regra vale **inclusive** quando Extrator e Classificador terminaram, mas o **save final de sucesso falhou**. Nesse caso os dados das etapas já estavam em memória, e `_registrar_erro` os descarta (coberto por teste).

---

## 15. Máquina de estados

Sem status novos:

```
            _reservar (lock)                  sucesso
PENDENTE ───────────────────► PROCESSANDO ─────────────► CONCLUIDO   (final; não reprocessa)
                                   │
                                   │ ExtratorError / ClassificadorError / erro inesperado
                                   ▼
                                  ERRO ──── nova chamada ────► PROCESSANDO
```

| Estado ao chamar | Comportamento | Status final |
| --- | --- | --- |
| `PENDENTE` | processa | `CONCLUIDO` ou `ERRO` |
| `ERRO` | nova tentativa: limpa `erro` e recria `processamento` | `CONCLUIDO` ou `ERRO` |
| `PROCESSANDO` | `DocumentoEmProcessamentoError`; nada é alterado; Agents não chamados | `PROCESSANDO` |
| `CONCLUIDO` | devolve o documento; Agents não criados nem chamados; **sem gasto de cota** | `CONCLUIDO` |
| inexistente | `Documento.DoesNotExist` | — |

| Situação durante o fluxo | Status final | `erro` |
| --- | --- | --- |
| sem arquivo / arquivo removido / vazio / sem `%PDF-` | `ERRO` | `extracao` / `documento_ilegivel` |
| Gemini indisponível (429, 503, timeout, rede, config) na extração | `ERRO` | `extracao` / `servico_indisponivel` |
| resposta inválida / não é nota / sem itens / sem total | `ERRO` | `extracao` / `resposta_invalida` |
| Gemini indisponível na classificação | `ERRO` | `classificacao` / `servico_indisponivel` |
| classificação fora do schema | `ERRO` | `classificacao` / `classificacao_invalida` |
| itens fora das 2 categorias | `ERRO` | `classificacao` / `classificacao_inconclusiva` |
| CPF/CNPJ com DV inválido | **`CONCLUIDO`** | — (sinalizado em `validacoes`) |
| erro inesperado (bug, banco, falha no save de sucesso…) | `ERRO` | `processamento` / `erro_interno` |

---

## 16. Tratamento de erros

| Origem | Capturado como | `etapa` | `codigo` | `mensagem` (segura; pode ir para a tela) | Log |
| --- | --- | --- | --- | --- | --- |
| Extrator | `ExtratorError` | `extracao` | `documento_ilegivel` / `servico_indisponivel` / `resposta_invalida` | `str(exc)`, a mensagem fixa do Agent | `warning`, **sem traceback** |
| Classificador | `ClassificadorError` | `classificacao` | `servico_indisponivel` / `classificacao_invalida` / `classificacao_inconclusiva` | `str(exc)` | `warning`, **sem traceback** |
| Qualquer outra `Exception` | `except Exception` no limite de `processar_documento` | `processamento` | `erro_interno` | "Erro inesperado ao processar o documento." | **`logger.exception`** (traceback **só no log do servidor**) |
| Documento em processamento | não grava | — | `documento_em_processamento` | "O documento já está sendo processado." | — |

- O aviso para erro esperado é `"Processamento do documento <pk> falhou (<etapa>/<codigo>)."`. Não leva `exc_info`, porque o `__cause__` pode ser uma `ValidationError` com dados da nota.
- **Nunca persistir:** `__cause__`, traceback, status HTTP, resposta bruta do Gemini, API Key.

---

## 17. Persistência

| Momento | Campos gravados | Como |
| --- | --- | --- |
| Reserva | `status=PROCESSANDO`, `metadados` (sem `erro`, `processamento` recriado) | dentro da transação curta: `save(update_fields=["status", "metadados"])` |
| Sucesso | `status=CONCLUIDO`, `resultado_estruturado`=JSON final, `metadados` | **um** `save(update_fields=["status", "resultado_estruturado", "metadados"])`, só depois de Extrator + Classificador + JSON montado |
| Erro | `status=ERRO`, `resultado_estruturado={}`, `metadados` seguros | **um** `save(update_fields=[...])` via `_registrar_erro` |

- **Nenhum resultado parcial é persistido:** se a classificação falhar, a extração é descartada.
- `update_fields` evita sobrescrever campos que não pertencem ao serviço (`arquivo`, `nome_original`, `titular`, `enviado_em`). Há teste alterando `nome_original` durante o fluxo.
- Cada gravação final é um único `UPDATE`, atômico por si só; não há transação durante os Agents.

---

## 18. Decisões tomadas (D1–D9)

| # | Decisão | Implementação |
| --- | --- | --- |
| D1 | Serviço central, sem lógica em view | `documentos/processamento.py`, `processar_documento(documento_id, *, extrator=None, classificador=None)` |
| D2 | `justificativa` fora do JSON final | em `metadados.processamento.classificacao.justificativa` (só no sucesso) |
| D3 | Classificação inconclusiva | `ERRO` com `classificacao_inconclusiva` (TipoDespesa é obrigatório na atividade) |
| D4 | Erro inesperado | capturado só no limite do serviço; `ERRO`/`erro_interno`; `logger.exception`; **não relançado** (exceto se a gravação do erro falhar) |
| **D5** | Reserva | **`transaction.atomic()` + `select_for_update()`**, transação curta que termina antes dos Agents |
| D6 | Status HTTP | não gravado em `metadados` (fica só no log dos Agents) |
| D7 | Reprocessar `CONCLUIDO` / destravar `PROCESSANDO` | não implementado; destravar pelo admin |
| D8 | Persistência parcial | não existe; falha na classificação descarta a extração |
| D9 | Chaves do JSON final | as da seção 13, sem `documento_e_nota_fiscal`, com `quantidade_parcelas` e `validacoes` |

---

## 19. Testes da GR-12

`documentos/test_processamento.py`, **49 testes**. Proteção contra a API real em todos os testes de processamento:

- Agents falsos (`mock.Mock(spec=AgentExtrator/AgentClassificador)`) ou Agents reais em caminhos que não chegam à rede;
- `agents.gemini_client.genai.Client` patchado para falhar se for criado;
- `GEMINI_API_KEY=None`.

| Classe | Testes | Cobre |
| --- | --- | --- |
| `ExcecoesTests` | 2 | hierarquia, códigos e mensagem; `VERSAO_RESULTADO` |
| `MontarResultadoTests` | 10 | chaves exatas e ordem; sem `documento_e_nota_fiscal` e sem justificativa; conteúdo preservado; **`quantidade_parcelas` 0, 1 e 3**; numeração automática mantida; `tipo_despesa` string nas 2 categorias; **`validacoes` preservado**; dinheiro e datas serializáveis; função pura |
| `ReservaTests` | 7 | reserva de `PENDENTE` e de `ERRO` (erro antigo removido, `processamento` recriado, outras chaves preservadas); `PROCESSANDO` recusado; `CONCLUIDO` não reservado; inexistente; `update_fields`; nenhuma transação aberta após o retorno; `iniciado_em` ISO com fuso |
| `ReservaConcorrenteTests` | 1 | **concorrência real** com 2 threads e conexões separadas (seção 12.2) |
| `ProcessamentoSucessoTests` | 12 | fluxo completo; Extrator e Classificador chamados **1×**; Classificador recebe **o mesmo** `NotaFiscalExtraida`; resultado persistido; CPF/CNPJ e `validacoes` preservados; metadados (versões, modelos, justificativa, `iniciado_em ≤ finalizado_em`, sem erro); metadados sem dados da nota; `iniciado_em` preservado; `PROCESSANDO` durante os Agents; **nenhuma transação aberta durante os Agents**; `update_fields`; Agents padrão criados quando não injetados |
| `ProcessamentoErroExtracaoTests` | 1 (4 subtestes) | cada `ExtratorError` → `ERRO`/`extracao`/código correto; Classificador não chamado |
| `ProcessamentoErroClassificacaoTests` | 2 | cada `ClassificadorError` → `ERRO`/`classificacao`/código correto; falha na classificação **não persiste a extração** |
| `ProcessamentoErroSeguroTests` | 1 | `__cause__` com marcador, CPF e "503" **não** vai para metadados nem log; aviso sem `exc_info` |
| `ProcessamentoErroInesperadoTests` | 6 | erro inesperado no Extrator e no Classificador → `processamento`/`erro_interno`; `logger.exception` só nesse caso; falha em `_registrar_sucesso` → `erro_interno`; **falha no save final real de sucesso** → `ERRO` sem `extracao`/`classificacao`/justificativa, com `iniciado_em` preservado e `finalizado_em`; falha ao gravar o erro → exceção sobe |
| `ProcessamentoEstadosTests` | 4 | `CONCLUIDO` não cria nem chama Agents; `PROCESSANDO` não chama Agents; `ERRO` reprocessa; inexistente |
| `ProcessamentoComAgentsReaisTests` | 3 | Agents reais sem rede: sem arquivo e arquivo removido → `documento_ilegivel`; PDF válido sem chave → `GeminiClient` real falha na configuração → `extracao`/`servico_indisponivel`; **SDK nunca criado** |

- **Invariante de metadados mínimos em qualquer `ERRO`:** o helper `assert_erro`, usado por todos os testes de erro, exige que `processamento` tenha exatamente `{versao_resultado, iniciado_em, finalizado_em}` e que `erro` tenha exatamente `{etapa, codigo, mensagem}`.
- **Verificações de mutação** (feitas em memória, sem alterar arquivos). Cada uma fez o teste correspondente falhar, como devia:
  - sem `select_for_update`;
  - Agents dentro de `transaction.atomic()`;
  - traceback no aviso de erro esperado;
  - `_registrar_erro` antigo, que mesclava `processamento`.

**Continuam passando sem alteração:** `documentos/tests.py`, `documentos/test_upload.py`, `agents/test_gemini_client.py`, `agents/extrator/*` e `agents/classificador/*`.

---

## 20. Contrato para a GR-14

A GR-14 **não** chama Agents nem o Gemini, e não monta JSON. Ela só usa:

| Necessidade da tela | O que usar |
| --- | --- |
| Botão "Processar" (POST) | `processar_documento(pk)` → `Documento` atualizado |
| Clique duplo / outra aba | `DocumentoEmProcessamentoError` → "já está sendo processado" (HTTP 409, se for JSON) |
| Documento inexistente | `Documento.DoesNotExist` → 404 |
| Estado | `documento.status` / `get_status_display()` |
| JSON final | `documento.resultado_estruturado` (só em `CONCLUIDO`) |
| Justificativa | `documento.metadados["processamento"]["classificacao"]["justificativa"]` (só em `CONCLUIDO`) |
| Erro | `documento.metadados["erro"]["mensagem"]` (+ `etapa` e `codigo`) |

**Decisões que afetam a interface:**

- O serviço é **síncrono** e pode levar de segundos a cerca de 6 min no pior caso (2 chamadas × 3 tentativas × 60 s). A GR-14 decide entre chamar na requisição (simples, bom para demonstração) ou em segundo plano com consulta de status; o serviço funciona nos dois casos, porque o estado fica no banco.
- `CONCLUIDO` é final: o botão pode virar "ver resultado".
- `ERRO` permite nova tentativa: o botão continua disponível. O `codigo` ajuda a orientar (ex.: `servico_indisponivel` → tentar depois; `documento_ilegivel` → reenviar o PDF).
- Upload já existe: `POST /documentos/upload/` (GR-7/8). A GR-14 deve reaproveitá-lo.
- Não expor o PDF por URL pública nem detalhes internos de erro.

---

## 21. Riscos

| # | Risco | Mitigação |
| --- | --- | --- |
| R1 | Documento preso em `PROCESSANDO` se o processo morrer durante a chamada (Ctrl+C, reinício, OOM) | mudar o status para `ERRO` no Django Admin; destravar automaticamente por tempo **não** foi implementado (D7) |
| R2 | **Cota:** 2 chamadas ao Gemini por documento, cada uma com até 3 tentativas | `CONCLUIDO` não reprocessa; `PROCESSANDO` é recusado; testes sem API real; teste manual uma vez só |
| R3 | **Tempo:** até cerca de 6 min no pior caso, numa chamada síncrona | decisão da GR-14 |
| R4 | Falha na classificação descarta uma extração bem-sucedida, e a nova tentativa extrai de novo (mais cota) | aceito pela simplicidade (D8) |
| R5 | **Só 2 categorias no MVP:** notas de outros tipos → `classificacao_inconclusiva` → `ERRO`. Afeta o critério de 30% | fora do escopo da GR-12; a equipe decide se amplia `TipoDespesa` na GR-11 |
| R6 | `__cause__` pode conter dados da nota | aviso de erro esperado sem `exc_info`; nada disso vai para `metadados` |
| R7 | `jsonb` não preserva a ordem das chaves | tela reordena se necessário |
| R8 | `analisetemporaria.md` é versionado e reescrito a cada tarefa | atualizar no fim de cada tarefa; combinar com quem estiver em outra branch |

---

# Parte IV — Operação e próximos passos

## 22. Guia da Gemini API

### 22.1 Conferir a configuração sem expor a chave

```bash
python manage.py shell -c 'from django.conf import settings; print("API Key carregada:", bool(settings.GEMINI_API_KEY)); print("Modelo:", settings.GEMINI_MODEL)'
```

- Esperado: `API Key carregada: True` e `Modelo: <modelo configurado>`. **Nunca** use `print(settings.GEMINI_API_KEY)`.
- `.env`: `GEMINI_API_KEY=`, `GEMINI_MODEL=`, `GEMINI_TIMEOUT_SEGUNDOS=60`, `GEMINI_MAX_TENTATIVAS=3`.
- O modelo vem **só** do `GEMINI_MODEL` (`.env` → `settings` → `GeminiClient.modelo` → `/v1beta/models/<modelo>:generateContent`); não é preciso escolher no AI Studio. Os **dois Agents usam o mesmo modelo**.
- Cada `manage.py shell` relê o `.env`; servidores persistentes precisam ser reiniciados.
- ⚠️ Uma **variável exportada no terminal vence o `.env`** (`load_dotenv()` não sobrescreve). Confira com `echo $GEMINI_MODEL` e remova com `unset GEMINI_MODEL`.

### 22.2 Retry e timeout

- **Retry:** 3 tentativas **no total** por chamada, feitas pelo SDK (408/429/500/502/503/504, timeout, conexão), com espera exponencial. Não crie loops de retry manuais: eles multiplicam chamadas e cota. O retry não resolve cota diária esgotada.
- **Timeout:** 60 s **por tentativa**. Pior caso por chamada ≈ 3 min; por documento (2 chamadas) ≈ 6 min. Só aumente com justificativa.

### 22.3 Diagnóstico por sintoma

| Sintoma | Significado | Ação | Bug do projeto? |
| --- | --- | --- | --- |
| `GeminiAPIError 503` UNAVAILABLE ("high demand") | modelo sobrecarregado | aguardar; tentar depois; outro modelo só para diagnóstico | ❌ externo |
| `GeminiAPIError 429` RESOURCE_EXHAUSTED ("quota exceeded", `free_tier_requests`) | cota ou limite do **projeto Google** | AI Studio → projeto correto → **Uso** e **Limite de taxa**; ver qual modelo; aguardar a janela; **não repetir em loop** | ❌ externo |
| `GeminiTimeoutError` | lento, indisponível ou rede | conferir serviço, conexão e PDF | ❌ normalmente externo |
| `GeminiAPIError None` | falha de rede | conferir conexão | ❌ |
| `GeminiAPIError 400/401/403` | chave inválida ou sem permissão | conferir chave e projeto | ❌ configuração |
| `GeminiAPIError 404` | modelo inexistente ou com nome errado | conferir `GEMINI_MODEL` | ❌ configuração |
| `GeminiConfiguracaoError` | chave ou modelo ausentes | preencher o `.env` | ❌ configuração |
| `resposta_invalida` / `classificacao_invalida` | a API respondeu, mas o conteúdo não passou na validação | ver no log os caminhos dos campos | ⚠️ geralmente o documento ou o modelo |
| `classificacao_inconclusiva` | itens fora das 2 categorias | esperado (R5) | ❌ limitação do MVP |
| `validacoes.*.status = "invalido"` | CPF/CNPJ com DV inválido; nota aceita | nenhuma | ❌ |
| Aviso "Both GOOGLE_API_KEY and GEMINI_API_KEY are set" | há `GOOGLE_API_KEY` no ambiente | inofensivo: o cliente passa `GEMINI_API_KEY` explicitamente | ❌ |
| Aviso "Direct use of automatic function calling (AFC)…" | aviso padrão do SDK | nenhuma | ❌ |
| `relation "documentos_documento" does not exist` (antes de chegar aos Agents) | banco local sem as migrations aplicadas | `python manage.py showmigrations` → `python manage.py migrate` (seção 24.1) | ❌ ambiente local |

No `Documento`, erros de serviço aparecem como `metadados["erro"] = {"etapa": "...", "codigo": "servico_indisponivel", ...}`. O status HTTP exato (429/503) fica no **log** dos Agents (`... indisponível (GeminiAPIError, status=429)`).

### 22.4 Modelos já testados

Resultado do momento de cada teste; nada é permanente.

| Modelo | Observado |
| --- | --- |
| `gemini-3.8-flash` | 503 e depois 429 por cota; usável em outro momento |
| `gemini-3.7-flash` | 503 |
| `gemini-3.5-flash-lite` | processou o PDF com structured output |

### 22.5 Se a Gemini parar de funcionar

1. Não altere código.
2. Confira a chave e o modelo (22.1).
3. Rode o teste manual (seção 24.1) e leia `metadados["erro"]` e o log.
4. 429 → cota; 503 → aguardar; timeout → serviço, rede e PDF.
5. CPF/CNPJ inválido ou classificação inconclusiva **não** são falha da API.
6. Rode `python manage.py test`, que não chama a API real.
7. Só altere código se testes ou auditoria indicarem defeito interno.

---

## 23. Checklist de segurança

- [ ] `.env` nunca vai para o Git (`git check-ignore -v .env`).
- [ ] A API Key nunca aparece em commit, PR, issue, chat, log ou documentação. Se vazar, revogue no AI Studio e gere outra.
- [ ] `uploads/` e `media/` continuam ignorados; notas fiscais reais nunca são versionadas.
- [ ] Testes usam documentos fictícios; testes automatizados nunca chamam a API real.
- [ ] `metadados` nunca recebe traceback, `__cause__`, status HTTP, resposta bruta ou chave.
- [ ] Antes do commit: `git status`, `git diff`, `git diff --cached`; em dúvida, `git check-ignore -v <arquivo>`.

---

## 24. Teste manual real e o que falta

### 24.1 Teste manual real da GR-12 (concluído)

**Teste manual real ponta a ponta da GR-12 usando a Gemini API**, com o PDF fictício `uploads/teste-gr10/danfe (ciclano - pecas).pdf`. O PDF é ignorado pelo Git.

**Primeira tentativa: falha de ambiente, antes dos Agents**

- O teste falhou **antes de chegar aos Agents**, ao criar o `Documento`, porque a tabela `documentos_documento` **não existia no banco PostgreSQL local**.
- A migration `documentos.0001_initial` existia no repositório, mas estava **pendente** no banco local.
- **Solução:** `python manage.py migrate`. Depois disso não havia mais migrations pendentes (`migrate --check` OK; `showmigrations documentos` → `[X] 0001_initial`).
- Não era defeito do código da GR-12, e nenhuma migration nova foi criada. Os testes automatizados não pegaram o problema porque criam um banco de teste próprio, já com as migrations aplicadas.

**Segunda tentativa: sucesso**

| Etapa | Resultado |
| --- | --- |
| `Documento` criado no PostgreSQL com o PDF fictício | ✅ |
| `processar_documento()` executado (reserva → `AgentExtrator` → `AgentClassificador` → JSON → gravação) | ✅ |
| Status final | **`CONCLUIDO`** |
| `resultado_estruturado` persistido | ✅ |
| `quantidade_parcelas` | **1** |
| `tipo_despesa` | **`MANUTENCAO_E_OPERACAO`** (nota de peças, coerente com a categoria) |
| CNPJ do fornecedor | extraído, normalizado, **`validacoes.fornecedor_cnpj.status = "valido"`** |
| CPF fictício do faturado (`999.999.999-99`) | **preservado** como `"99999999999"` e sinalizado: `validacoes.faturado_cpf = {"status": "invalido", "motivo": "digitos_verificadores_invalidos"}`; a nota foi aceita |
| `metadados.processamento.extracao` / `.classificacao` | persistidos (versão do schema e modelo) |
| Justificativa da classificação | persistida em `metadados.processamento.classificacao.justificativa` |
| `metadados["erro"]` | **ausente** |

**Verificação posterior no banco** (consulta ao `Documento` salvo):

```
ID: 1
STATUS: CONCLUIDO
TEM RESULTADO: True
TIPO DESPESA: MANUTENCAO_E_OPERACAO
QUANTIDADE PARCELAS: 1
TEM ERRO: False
```

- Isso confirma, com a API real, o caminho completo `PDF → Extrator → Classificador → JSON final → Documento`, a política de CPF/CNPJ e o contrato de metadados de sucesso (seções 13 e 14.1).
- Os valores extraídos da nota **não** são reproduzidos aqui, exceto o CPF explicitamente fictício.
- O documento de teste (ID 1) e o arquivo correspondente em `media/`, ignorado pelo Git, estão no **ambiente local**. Podem ser apagados pelo admin quando não forem mais necessários.

**Comando usado** (para repetir, **uma vez só**, por causa da cota):

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

- **Antes do teste**, em banco local novo: `python manage.py migrate`.
- Para ver os avisos dos Agents: acrescente `import logging; logging.basicConfig(level=logging.WARNING)` no início.
- Se terminar em `ERRO`: consulte `metadados["erro"]` e a seção 22.

### Para encerrar a GR-12

1. Validação final no Git: `git status`, `git diff`, e depois do `add`, `git diff --cached`. Conferir que **não** entram `.env`, `uploads/`, `media/` nem a chave.
2. **Commit, push, PR e merge** (somente com autorização). Mensagem sugerida: `feat(documentos): orquestrar extração e classificação GR-12`, com `documentos/processamento.py`, `documentos/test_processamento.py` e `analisetemporaria.md`.

### 24.2 Depois da GR-12

| Tarefa | Entrega |
| --- | --- |
| **GR-14 — Interface Web** | tela de upload (reaproveitando `POST /documentos/upload/`); botão "Processar" chamando `processar_documento`; status, JSON final, justificativa e erro seguro (seção 20) |
| **GR-21 — Validação final** | fluxo completo no navegador com PDF fictício; conferência com os campos da atividade (seção 1) |

```
PDF → upload + validação (GR-7/8) → processar_documento (GR-12)
    → AgentExtrator (GR-10) → AgentClassificador (GR-11) → JSON final no Documento
    → interface Web (GR-14) → validação final (GR-21)
```

---

## 25. Estado do Git

| Item | Estado |
| --- | --- |
| Branch | `feature/GR-12-orquestracao` |
| Base | `main` em `e25d47d` (merge da GR-11, PR #11) |
| GR-12 | implementação e teste manual real concluídos; aguardando validação Git, commit, push, PR e merge |
| Alterações atuais | `M analisetemporaria.md` · `?? documentos/processamento.py` · `?? documentos/test_processamento.py` |
| `git add` / commit / push / PR | **não realizados** |
| `.env` / `uploads/` / `media/` | ignorados e não rastreados |
| Banco local | migrations aplicadas (`migrate --check` sem pendências); documento de teste ID 1 em `CONCLUIDO` |
