# Gestão Rural — Documento de handoff (estado atual e GR-21: validação final)

> **Para que serve este arquivo:** quem abrir só este documento deve conseguir entender o projeto, o que o professor pediu, como o sistema foi implementado (GR-6 a GR-14), o resultado da **auditoria final da GR-21** e o que falta para encerrar a atividade.
>
> **Estado atual:** GR-6 a GR-14 **concluídas e mergeadas** (a GR-14 pelo PR #13). **GR-21 (validação final) é a tarefa atual**, na branch `feature/GR-21-validacao-final`. **GR-21 validada:** auditoria ✅, decisões ✅ (MVP mantido; seção 20), validação manual final ✅ (seção 18.1); correções de código e nova chamada à Gemini **dispensadas**. **Nenhum código foi alterado.** Situação: **validação concluída, aguardando commit/PR** (etapa 6, seção 21).
>
> **Contexto estável do projeto:** `ContextoProjeto.md` (arquitetura, contratos, regras e decisões consolidadas). Este arquivo guarda a auditoria e as etapas em andamento.
>
> **Fonte de verdade:** o código da `main` em `acedf6b` (a branch da GR-21 está idêntica a ela) e os slides da atividade (`03 - Aula - Pratica de Engenharia (Agents).pptx`, slides 18–21), lidos diretamente nesta auditoria.
>
> **Regras deste documento:**
> - nenhuma chave, segredo ou valor real do `.env` aparece aqui;
> - nenhum dado pessoal real aparece aqui;
> - `999.999.999-99` é um CPF **explicitamente fictício**, do PDF de demonstração.

---

## Sumário

**Parte I — Projeto**
1. [A atividade (slides 18–21)](#1-a-atividade-slides-1821)
2. [Estado das tarefas](#2-estado-das-tarefas)
3. [Estrutura atual do projeto](#3-estrutura-atual-do-projeto)
4. [Projeto × atividade (resumo)](#4-projeto--atividade-resumo)

**Parte II — Sistema implementado (GR-6 a GR-14)**
5. [Documento, upload e validação (GR-6/7/8)](#5-documento-upload-e-validação-gr-678)
6. [GeminiClient (GR-9)](#6-geminiclient-gr-9)
7. [AgentExtrator (GR-10)](#7-agentextrator-gr-10)
8. [AgentClassificador (GR-11)](#8-agentclassificador-gr-11)
9. [Orquestração `processar_documento` (GR-12)](#9-orquestração-processar_documento-gr-12)
10. [Interface Web (GR-14)](#10-interface-web-gr-14)

**Parte III — GR-21: auditoria final**
11. [Requisito por requisito](#11-requisito-por-requisito)
12. [Fluxo completo](#12-fluxo-completo)
13. [JSON final](#13-json-final)
14. [Agents e classificação](#14-agents-e-classificação)
15. [Segurança](#15-segurança)
16. [Erros](#16-erros)
17. [Testes](#17-testes)
18. [Testes manuais já realizados e conferência com o PDF](#18-testes-manuais-já-realizados-e-conferência-com-o-pdf)
19. [Achados e limitações conhecidas](#19-achados-e-limitações-conhecidas)
20. [Decisões da GR-21](#20-decisões-da-gr-21)
21. [Plano da GR-21](#21-plano-da-gr-21)
22. [Arquivos](#22-arquivos)

**Parte IV — Operação**
23. [Guia da Gemini API](#23-guia-da-gemini-api)
24. [Checklist de segurança](#24-checklist-de-segurança)
25. [Estado do Git](#25-estado-do-git)

---

# Parte I — Projeto

## 1. A atividade (slides 18–21)

Transcrição fiel dos slides da atividade (N2, 1ª etapa; entrega prevista nos slides: 23/09/2025; peso 35%):

- **Slide 18:** "Será implementado um processador de PDF, utilizando Agents (recomenda-se Gemini), para extrair os dados de uma nota fiscal (**CONTAS A PAGAR**) e devolver em formato **JSON**."
  - Campos obrigatórios:
    - Fornecedor: Razão Social / Fantasia / CNPJ;
    - Faturado: Nome Completo / CPF;
    - Número da Nota Fiscal;
    - Data de Emissão;
    - Descrição dos produtos\*;
    - QuantidadeParcela\*;
    - Data de Vencimento;
    - ValorTotal;
    - TipoDespesa\*.
  - Observações:
    - Descrição dos produtos: "não será necessário criar uma entidade PRODUTOS";
    - Quantidade de Parcelas: "uma parcela, porém com estrutura para receber mais de uma";
    - **Classificação da DESPESA: "uma classificação de DESPESA por registro, porém com estrutura para receber mais de uma".**
- **Slide 19:** "DESPESA não é um campo extraído. Deverá ser interpretado pelo Gemini. Conforme os produtos da Nota Fiscal, classifica-se o registro."
  - Exemplos: Óleo Diesel → **MANUTENÇÃO E OPERAÇÃO**; Material Hidráulico → **INFRAESTRUTURA E UTILIDADES**.
  - **Os slides não trazem uma lista completa de categorias**; a documentação do cliente fala em subcategorias financeiras (Insumos / Operacionais), noutro contexto.
- **Slide 20:** interface gráfica Web. O usuário carrega o PDF e, "através de um Button", solicita a extração, "que aciona o Gemini que extrai e devolve os dados em formato JSON na TELA".
- **Slide 21 (avaliação):**

  | Peso | Critério |
  | --- | --- |
  | 40% | Uso do Agent conforme estrutura |
  | 30% | Conteúdo do JSON |
  | 30% | Assertividade na classificação da DESPESA |

- **Slides 10–16 (estrutura de Agents):**
  - pacote `agents/<agente>/` com `__init__.py`;
  - uma classe por Agent;
  - coordenação **sequencial síncrona** (Agent1 extrai → Agent2 age depois).

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
| GR-12 | Orquestração PDF → Agents → JSON | ✅ mergeada | PR #12 (`2f7f742`, merge `292ee0c`) |
| GR-14 | Interface Web | ✅ **mergeada** | **PR #13** (`f0fdde0`, merge `acedf6b`) |
| **GR-21** | **Validação final** | ✅ **validação concluída, aguardando commit/PR** (sem alteração de código) | branch `feature/GR-21-validacao-final` |

**Testes na `main`:** `python manage.py test` → **303 — OK**, e **0** tentativas de conexão externa com a rede bloqueada (seção 17).

---

## 3. Estrutura atual do projeto

```
gestao-rural/
├── config/
│   ├── settings.py              load_dotenv(); PostgreSQL; MAX_PDF_UPLOAD_SIZE_MB; GEMINI_*
│   └── urls.py                  "" → /documentos/ (inicio) · admin/ · include("documentos.urls")
├── documentos/
│   ├── models.py                Documento (GR-6)
│   ├── forms.py, validators.py  DocumentoUploadForm → validar_pdf (GR-8)
│   ├── processamento.py         processar_documento (GR-12)
│   ├── urls.py                  "" · upload/ · <int:pk>/ · <int:pk>/processar/ (GR-14)
│   ├── views.py                 _salvar_documento · upload_documento (JSON) · documento_inicio · documento_detalhe · documento_processar
│   ├── templates/documentos/    base.html · inicio.html · detalhe.html
│   ├── static/documentos/       documentos.css · documentos.js
│   ├── admin.py                 DocumentoAdmin (status editável)
│   ├── tests.py, test_upload.py, test_processamento.py, test_interface.py
│   └── migrations/0001_initial.py
├── agents/
│   ├── gemini_client.py         GR-9 (único ponto de contato com o SDK)
│   ├── extrator/                GR-10 — agent.py, schemas.py, testes
│   └── classificador/           GR-11 — agent.py, schemas.py, testes
├── financeiro/, usuarios/       models de apoio (fora do fluxo da 1ª etapa)
├── uploads/teste-gr10/          PDF fictício — IGNORADO pelo Git
├── media/                       PDFs enviados — IGNORADO pelo Git
├── ContextoProjeto.md           contexto oficial e estável do projeto
└── analisetemporaria.md         este documento   (README.md adiado: decisão D-I3)
```

---

## 4. Projeto × atividade (resumo)

| Requisito dos slides | Situação |
| --- | --- |
| PDF de NF → Agents (Gemini) → JSON | ✅ implementado e validado com a Gemini real (IDs 1 e 2) |
| Interface Web: carregar PDF → Button → JSON na tela | ✅ implementado e validado no navegador (ID 2) |
| Campos do slide 18 (fornecedor, faturado, número, data, produtos, quantidade de parcelas, vencimento, valor total, TipoDespesa) | ✅ todos presentes no JSON |
| Estrutura para mais de uma parcela | ✅ lista `parcelas` |
| Estrutura para mais de uma classificação de DESPESA | **decisão do MVP:** uma classificação principal por documento (`tipo_despesa` escalar); múltiplas classificações ficam como evolução futura (D-I1) |
| TipoDespesa interpretado pelo Gemini a partir dos produtos | ✅ (2 categorias, as dos exemplos do slide 19; notas fora delas terminam em `ERRO`: limitação aceita, D-I2) |
| Sem entidade Produto | ✅ |

Detalhe, arquivo por arquivo, com testes e evidências: **seção 11**.

---

# Parte II — Sistema implementado (GR-6 a GR-14)

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

⚠️ O PostgreSQL (`jsonb`) **não preserva a ordem das chaves** ao ler de volta. A interface reordena para exibir (`_json_ordenado`, seção 10.2).

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

## 10. Interface Web (GR-14)

Mergeada pelo PR #13. Django templates + HTML + 1 CSS + 1 JS mínimo; sem frontend separado, CDN ou dependências novas.

### 10.1 URLs e views

| Método | URL | Nome | View | Comportamento |
| --- | --- | --- | --- | --- |
| GET | `/` | `inicio` | `RedirectView` | → `/documentos/` |
| GET, POST | `/documentos/` | `documento_inicio` | `documento_inicio` | GET: formulário + 10 documentos recentes (`-enviado_em`). POST: `DocumentoUploadForm` → `_salvar_documento` → redirect ao detalhe; inválido → erro no campo; `DatabaseError`/`OSError` → "Não foi possível salvar o documento." |
| POST | `/documentos/upload/` | `documento_upload` | `upload_documento` | endpoint JSON da GR-7 (201/400/500), mantido |
| GET | `/documentos/<pk>/` | `documento_detalhe` | `documento_detalhe` | só leitura de `status`, `resultado_estruturado` e `metadados`; apresentação por status |
| POST | `/documentos/<pk>/processar/` | `documento_processar` | `documento_processar` | **só chama `processar_documento(pk)`**; mensagens: `CONCLUIDO` → "Processamento concluído."; `ERRO` → "O processamento falhou. Veja os detalhes abaixo."; `DocumentoEmProcessamentoError` → info; `DoesNotExist` → 404; outra exceção → `logger.exception` + mensagem genérica |

Todas com `@staff_member_required` (login pelo `/admin/login/`) e CSRF nos POSTs. `views.py` importa de `documentos.processamento` apenas `processar_documento` e `DocumentoEmProcessamentoError`; **não** menciona `agents`, `GeminiClient` nem `genai` (há teste).

### 10.2 Página do documento por status

| Status | Conteúdo | Botão |
| --- | --- | --- |
| `PENDENTE` | "Pronto para processar." | **Processar** (form POST + CSRF) |
| `PROCESSANDO` | "Processando... a página atualiza automaticamente." + `meta refresh` de 5 s | nenhum |
| `CONCLUIDO` | resumo (tipo de despesa com rótulo, valor em R$, parcelas, fornecedor, número, data) + avisos de CPF/CNPJ com DV inválido + justificativa + **JSON final** (`<pre>`, reordenado pela ordem do contrato, escapado) | nenhum |
| `ERRO` | `metadados.erro.mensagem` + sugestão por `codigo` | **Tentar novamente** (form POST + CSRF) |

- **JavaScript** (`documentos.js`, com `defer`): só nos forms `data-submit-lock`. No 1º submit, desabilita o botão e troca o texto ("Enviando..." / "Processando..."); não cancela o POST; sem `fetch`, `innerHTML` ou `eval`. É **proteção visual**; a real é o lock da GR-12. Tudo funciona sem JS.
- **Validação manual da GR-14** (Documento ID 2 pela interface, com a Gemini real → `CONCLUIDO`): seção 18.

---

# Parte III — GR-21: auditoria final

Tudo abaixo foi conferido no **código real** da `main` (`acedf6b`), não apenas neste documento.

## 11. Requisito por requisito

| # | Requisito (slides) | Situação | Onde (código) | Teste automatizado | Evidência manual | Limitação |
| --- | --- | --- | --- | --- | --- | --- |
| A | Receber PDF de NF de contas a pagar | ✅ IMPLEMENTADO | `documentos/views.py::documento_inicio` (+ `upload_documento`), `forms.py`, `validators.py::validar_pdf` | `test_interface.UploadHtmlTests`, `test_upload` | ID 2 enviado pelo navegador | "contas a pagar" não é verificado (qualquer NF é aceita) |
| B | Utilizar Agents (Gemini) | ✅ IMPLEMENTADO | `agents/extrator/agent.py::AgentExtrator`, `agents/classificador/agent.py::AgentClassificador`, `agents/gemini_client.py` | `agents/*/test_agent.py`, `test_gemini_client` | ID 1 (shell) e ID 2 (interface) com a Gemini real | Agent2 **classifica**; a persistência é do serviço (nos slides, o exemplo de Agent2 "persiste"). Ver M6 |
| C | Devolver JSON | ✅ IMPLEMENTADO | `documentos/processamento.py::_montar_resultado` → `Documento.resultado_estruturado` | `test_processamento.MontarResultadoTests` | JSON do ID 2 | — |
| D | Interface Web: carregar PDF, **Button**, JSON na **tela** | ✅ IMPLEMENTADO | `views.py` (`documento_inicio`, `documento_detalhe`, `documento_processar`), `templates/documentos/*.html` | `test_interface` (83) | ID 2: upload → Processar → JSON na tela | acesso só para staff (login do admin) |
| E1 | Fornecedor: Razão Social / Fantasia / CNPJ | ✅ | `extrator/schemas.py::Fornecedor` | `extrator/test_schemas` | razão social e CNPJ do ID 2 conferem com o PDF | nome fantasia `null` quando o PDF não o traz (caso do DANFE de teste; correto) |
| E2 | Faturado: Nome Completo / CPF | ✅ | `Faturado(nome, cpf)` | idem | conferem com o PDF | CPF com DV inválido é preservado e sinalizado |
| E3 | Número da NF / Data de Emissão | ✅ | `numero_nota`, `data_emissao` (ISO) | idem | conferem com o PDF | `data_emissao` pode ser `null` se ilegível |
| E4 | Descrição dos produtos | ✅ | `itens[].descricao` (obrigatória; + quantidade e valores) | idem | 10 itens do ID 2 conferem com o PDF | — |
| E5 | QuantidadeParcela | ✅ | `quantidade_parcelas = len(parcelas)` em `_montar_resultado` | `MontarResultadoTests.test_quantidade_de_parcelas` (0, 1, 3) | ID 2: 1 | nota à vista → `0` e `parcelas: []` |
| E6 | Data de Vencimento | ✅ | `parcelas[].data_vencimento` | `extrator/test_schemas` | vencimento do ID 2 confere | só existe dentro de parcelas; pode ser `null` |
| E7 | ValorTotal | ✅ | `valor_total` (obrigatório, > 0, 2 casas) | idem | R$ 3.086,75 = "valor total da nota" do PDF | — |
| E8 | TipoDespesa | ✅ IMPLEMENTADO (uma classificação por documento) | `ClassificacaoDespesa.tipo_despesa` → `resultado["tipo_despesa"]` (string única) | `classificador/*`, `test_processamento` | ID 2: `MANUTENCAO_E_OPERACAO` | o slide 18 menciona "estrutura para receber mais de uma"; **decisão do MVP:** uma classificação principal por documento; múltiplas ficam como evolução futura (D-I1) |
| F | Múltiplas parcelas | ✅ | lista `parcelas` + numeração 1..n | `ParcelasTests`, `test_quantidade_de_parcelas` | ID 2 tem 1 parcela (conforme o PDF) | múltiplas parcelas **não** foram testadas com a Gemini real (só com dados fictícios nos testes) |
| G | TipoDespesa interpretado pelo Gemini a partir dos produtos | ✅ | `AgentClassificador` envia `itens` (descrição/quantidade/valor), fornecedor e total ao Gemini; `TipoDespesa` sai do schema `ClassificacaoDespesa` | `classificador/test_agent` | justificativa exibida no ID 2 | **limitação aceita do MVP (D-I2):** só 2 categorias; itens fora delas → `ERRO` (`classificacao_inconclusiva`), com a limitação explicada na tela e "Tentar novamente" |
| H | Sem entidade Produto | ✅ | itens só no JSON; nenhum model Produto | — | — | — |

---

## 12. Fluxo completo

```
PDF ─► documento_inicio (POST) ─► DocumentoUploadForm ─► validar_pdf (GR-8)
    ─► _salvar_documento ─► Documento PENDENTE ─► redirect /documentos/<id>/
    ─► botão Processar (POST + CSRF) ─► documento_processar ─► processar_documento(pk)
          ─► _reservar (atomic + select_for_update; transação curta) ─► PROCESSANDO
          ─► AgentExtrator.extrair_documento ─► NotaFiscalExtraida
          ─► AgentClassificador.classificar(nota) ─► ClassificacaoDespesa
          ─► _montar_resultado ─► _registrar_sucesso ─► resultado_estruturado + CONCLUIDO
    ─► redirect ─► documento_detalhe ─► resumo + JSON na tela
```

- **Nenhum ponto quebrado:** confirmado pelos testes de integração (`ProcessarIntegracaoTests`: view real + serviço real + Agents falsos) e pelo teste manual do ID 2.
- **Sem duplicação de lógica de negócio:**
  - a validação existe só no form/`validar_pdf`;
  - a gravação do documento só em `_salvar_documento`;
  - o processamento só em `processar_documento`;
  - as views não chamam Agents.
- **Duplicação menor:** a ordem das chaves do JSON existe em dois lugares, `_montar_resultado` (persistência) e `CHAVES_RESULTADO` (`views.py`, apresentação). Achado **M2**.

---

## 13. JSON final

**Chaves persistidas** (`_montar_resultado`; conferidas no banco local para ID 1 e ID 2): `fornecedor`, `faturado`, `numero_nota`, `data_emissao`, `itens`, `quantidade_parcelas`, `parcelas`, `valor_total`, `tipo_despesa`, `validacoes`. **Não** contém `documento_e_nota_fiscal` nem `justificativa` (a justificativa fica em `metadados`).

| Aspecto | Resultado |
| --- | --- |
| Tipos | textos `str \| null`; CNPJ 14 caracteres e CPF 11 dígitos (normalizados); `quantidade_parcelas` `int`; `tipo_despesa` `str` |
| Datas | ISO `AAAA-MM-DD` (validadas; `dd/mm/aaaa` rejeitado); na tela, `dd/mm/aaaa` |
| Valores monetários | strings com 2 casas (`"3086.75"`), sem perda de precisão; quantidade sem quantizar; na tela, `R$ 3.086,75` |
| Múltiplas parcelas | lista ordenada; numeração 1..n quando ausente; numeração parcial ou repetida → rejeitada |
| Campos ausentes | opcionais → `null` (não inventados); obrigatórios: `valor_total` (> 0), ≥ 1 item com descrição, `documento_e_nota_fiscal = true` |
| Ordem | **persistência:** `jsonb` não preserva a ordem; **apresentação:** `_json_ordenado` reordena pela ordem do contrato. A ordem é só de apresentação; nenhum consumidor depende dela |
| `validacoes` | calculado localmente (não vem do Gemini): `fornecedor_cnpj`/`faturado_cpf` → `valido`/`invalido`/`ausente` |

**Decisão do MVP (D-I1):** `tipo_despesa` permanece **escalar**, uma classificação principal por documento. A estrutura para várias classificações, mencionada no slide 18, fica como evolução futura.

---

## 14. Agents e classificação

| Ponto | Confirmado no código |
| --- | --- |
| Estrutura (slides 14–16) | `agents/extrator/` e `agents/classificador/` com `__init__.py`, `agent.py` (classe `AgentExtrator`/`AgentClassificador`) e `schemas.py`; cliente compartilhado em `agents/gemini_client.py` |
| Coordenação (slides 10–11) | **sequencial síncrona**: Agent1 (extrai) → Agent2 (classifica), orquestrados por `processar_documento`, que persiste |
| Reuso do `GeminiClient` | os dois Agents usam só `gerar_json` com schema Pydantic e `temperatura=0`, com criação preguiçosa; nenhum outro arquivo usa o SDK |
| Entrada do Classificador | `classificar(nota)` exige `NotaFiscalExtraida` (`isinstance`) |
| Uso dos produtos | contexto enviado: `itens[].descricao/quantidade/valor_total` + fornecedor (razão social/fantasia) + `valor_total`; **sem** CPF, CNPJ ou faturado |
| Origem do TipoDespesa | resposta do Gemini validada por `ClassificacaoDespesa` (Enum); **nada é copiado do PDF** e **nada é hardcoded na interface** (`ROTULOS_TIPO_DESPESA` em `views.py` só traduz o rótulo para exibição) |
| Categorias | `MANUTENCAO_E_OPERACAO`, `INFRAESTRUTURA_E_UTILIDADES` (exatamente os 2 exemplos do slide 19) |
| Inconclusiva | `tipo_despesa = null` → `ClassificacaoInconclusivaError` → `ERRO` (`classificacao_inconclusiva`); a tela explica a limitação do MVP e oferece "Tentar novamente". **Limitação aceita (D-I2)** |
| Justificativa | `ClassificacaoDespesa.justificativa` (1–500 caracteres) → `metadados.processamento.classificacao.justificativa` → exibida no detalhe |
| Resultado real | ID 2 (nota de peças de máquinas agrícolas) → "Manutenção e operação", **coerente** com o slide 19 |

---

## 15. Segurança

| Item | Verificação | Resultado |
| --- | --- | --- |
| `.env` ignorado | `git check-ignore -v .env` → `.gitignore:12` | ✅ |
| `uploads/` ignorado | `.gitignore:20` | ✅ |
| `media/` ignorado | `.gitignore:19` | ✅ |
| Chave real versionada | auditoria da GR-14 (valor real e padrão `AIza…` ausentes); a GR-21 não alterou arquivos | ✅ |
| Chave/modelo na interface | testes `nao_mostra_metadados_internos_nem_modelo`, `nao_exibe_dados_internos` | ✅ |
| CSRF | `ProcessarRotaEAcessoTests.test_csrf_obrigatorio` (403 sem token) | ✅ |
| Acesso staff | `@staff_member_required` em todas as páginas; testes de anônimo e não-staff | ✅ |
| XSS | escape automático; sem `\|safe`/`autoescape off` (teste); `<script>` testado em nome, JSON e mensagens | ✅ |
| PDF exposto | sem link para `arquivo`/`MEDIA`; `MEDIA_URL` não é servido | ✅ |
| Traceback / dados internos da Gemini | não persistidos em `metadados` (GR-12) nem exibidos (GR-14); testado | ✅ |

---

## 16. Erros

| Situação | Comportamento real | Coberto por |
| --- | --- | --- |
| PDF inválido (extensão, vazio, tamanho, content-type, cabeçalho) | upload rejeitado; mensagem no campo; nenhum `Documento` | `UploadHtmlTests`, `test_upload` |
| Documento ilegível (sem arquivo, removido, vazio) | `ERRO` / `documento_ilegivel`; Gemini **não** é chamado; sugestão "Envie o arquivo PDF novamente." | `ProcessamentoComAgentsReaisTests`, `DetalheErroTests` |
| Serviço indisponível (429/503/timeout/rede/config) | `ERRO` / `servico_indisponivel`; "Tente novamente mais tarde." + botão "Tentar novamente" | `FalhasDoGeminiTests`, `ProcessarIntegracaoTests` |
| Resposta inválida / não é nota fiscal | `ERRO` / `resposta_invalida` | `RespostaInvalidaTests`, `ProcessamentoErroExtracaoTests` |
| Classificação inválida | `ERRO` / `classificacao_invalida` | `ProcessamentoErroClassificacaoTests` |
| Classificação inconclusiva | `ERRO` / `classificacao_inconclusiva`; sugestão explica a limitação do MVP; **extração descartada** | idem + `ProcessarIntegracaoTests` |
| Erro interno | `ERRO` / `erro_interno`; `logger.exception`; mensagem genérica | `ProcessamentoErroInesperadoTests`, `ProcessarServicoMockadoTests` |
| Documento `PROCESSANDO` | POST → "O documento já está sendo processado."; sem Agents; lock testado com 2 threads | `ReservaConcorrenteTests`, `ProcessamentoEstadosTests` |
| Reprocessar após `ERRO` | permitido; erro antigo limpo; pode terminar `CONCLUIDO` | `test_erro_pode_reprocessar`, `ProcessarIntegracaoTests` |
| Reprocessar `CONCLUIDO` | não chama Agents (sem cota) | `test_documento_concluido_nao_reprocessa` |

---

## 17. Testes

| Arquivo | Testes | Área |
| --- | --- | --- |
| `documentos/test_upload.py` | 12 | upload JSON (GR-7) + caminho 500 / `_salvar_documento` |
| `documentos/tests.py` | 3 | model `Documento` |
| (validação GR-8) | — | coberta em `test_upload` e `test_interface` (não há arquivo próprio) |
| `agents/test_gemini_client.py` | 27 | `GeminiClient` |
| `agents/extrator/test_schemas.py` + `test_agent.py` | 52 + 34 | Extrator |
| `agents/classificador/test_schemas.py` + `test_agent.py` | 11 + 15 | Classificador |
| `documentos/test_processamento.py` | 49 | orquestração (inclui concorrência real) |
| `documentos/test_interface.py` | 83 | interface Web (inclui integração view + serviço real + Agents falsos) |
| `financeiro/tests.py` | 17 | models financeiros |
| `usuarios/tests.py` | 0 | — |
| **Total** | **303** | `python manage.py test` → OK |

**Nenhum teste usa a Gemini real:**

- **Conferido por código:** todos os testes de Agents, serviço e interface usam `mock.Mock(spec=GeminiClient)`, Agents falsos ou `genai.Client` patchado para falhar, além de `GEMINI_API_KEY=None`.
- **Conferido por execução:** a suíte completa rodou com `socket.connect` bloqueado para qualquer host que não fosse localhost (PostgreSQL). Resultado: **303 OK e 0 tentativas de conexão externa**.

---

## 18. Testes manuais já realizados e conferência com o PDF

| Documento | Como | Resultado |
| --- | --- | --- |
| **ID 1** | shell, `processar_documento` com a Gemini real (GR-12; seção 9.6) | `CONCLUIDO`; `quantidade_parcelas = 1`; `MANUTENCAO_E_OPERACAO`; CNPJ válido; CPF fictício inválido |
| **ID 2** | **navegador**: upload → Processar, com a Gemini real (GR-14) | `CONCLUIDO`; "Processamento concluído."; tela com Manutenção e operação, **R$ 3.086,75**, **1** parcela, fornecedor IGUACU MAQUINAS AGRICOLAS LTDA, nota 000.084.682, 19/09/2025; aviso de CPF fictício inválido; justificativa; JSON formatado; nada interno exposto. CSS/JS com HTTP 200; o único 404 foi `/favicon.ico` (irrelevante) |

**Conferência do JSON do ID 2 com o texto do PDF** (GR-21, **sem chamar a Gemini**: `pdftotext` no PDF fictício + leitura do `resultado_estruturado` salvo no banco local):

| Campo | Confere com o PDF? |
| --- | --- |
| razão social, CNPJ, nome do faturado, CPF, número, data de emissão | ✅ todos presentes no PDF |
| valor total R$ 3.086,75 | ✅ = "VALOR TOTAL DA NOTA". A soma dos 10 itens é R$ 3.754,67 = "VALOR TOTAL DOS PRODUTOS"; a diferença é o **desconto de R$ 667,92** impresso no PDF, então a extração está correta |
| parcela (valor e vencimento) | ✅ presentes no PDF; `quantidade_parcelas = 1` |
| 10 itens | ✅ as 10 descrições estão no PDF |
| nome fantasia | `null`: o DANFE não imprime nome fantasia separado; correto não inventar |
| `validacoes` | CNPJ `valido`; CPF fictício `invalido` (esperado) |

**Sem evidência real (aceito):** uma nota com **várias parcelas** e uma nota da categoria **INFRAESTRUTURA E UTILIDADES**. Faltam PDFs fictícios desses casos. Os dois comportamentos estão cobertos por testes automatizados, e a etapa 5 foi dispensada (seção 21).

### 18.1 Validação manual final da GR-21 (etapa 4) — concluída

Feita no navegador (`runserver`), **sem chamar a Gemini**:

| Cenário | Resultado |
| --- | --- |
| **IDs 1 e 2** (`CONCLUIDO`) | ID 2 conferido pela interface: resumo correto, JSON exibido, "Manutenção e operação", **R$ 3.086,75**, **1** parcela, justificativa exibida, CPF fictício inválido sinalizado corretamente, **sem botão de reprocessamento** |
| **Estado `ERRO`** | documento de teste exibiu o erro seguro e o botão "Tentar novamente" |
| **`documento_ilegivel`** | **ID 4** criado como `PENDENTE`; arquivo removido manualmente do storage; ao processar → `ERRO` com "Não foi possível ler o arquivo PDF do documento." + "Envie o arquivo PDF novamente." + botão "Tentar novamente". O caminho falha **antes** de chamar a Gemini |
| **Estado `PROCESSANDO`** | ID 4 colocado temporariamente em `PROCESSANDO` pelo Django Admin: status "Processando", mensagem "Processando... a página atualiza automaticamente.", **nenhum** botão Processar ou Tentar novamente. Depois o ID 4 foi **restaurado para `ERRO`** |
| **Demais comportamentos** (login/staff, PDFs inválidos, CSRF, XSS, PDF não exposto, sem traceback/chave/modelo) | **não repetidos manualmente:** já cobertos pela suíte automatizada (seções 15–17) |

---

## 19. Achados e limitações conhecidas

### CRÍTICO (pode comprometer a entrega)

**Nenhum.** Todos os campos obrigatórios existem, o fluxo exigido funciona ponta a ponta com a Gemini real e a suíte está verde.

### IMPORTANTE → decididos na etapa 2 como limitações ou escopo do MVP

Encontrados na auditoria (etapa 1) e **resolvidos por decisão consciente de escopo** (etapa 2, seção 20). **Não são correções pendentes.**

| # | Achado da auditoria | Como fica no MVP | Evolução futura possível |
| --- | --- | --- | --- |
| **I1** | o slide 18 menciona "estrutura para receber mais de uma" classificação de DESPESA; o JSON tem `tipo_despesa` escalar | **limitação aceita:** uma classificação principal por documento (`"tipo_despesa": "MANUTENCAO_E_OPERACAO"`); JSON e Classificador inalterados | lista de classificações no JSON (ex.: `classificacoes`) |
| **I2** | uma nota com itens fora das 2 categorias termina em `ERRO` (`classificacao_inconclusiva`), sem JSON na tela | **limitação aceita:** categorias só `MANUTENCAO_E_OPERACAO` e `INFRAESTRUTURA_E_UTILIDADES` (os exemplos da atividade); a tela explica a limitação e permite nova tentativa | ampliar `TipoDespesa`, ou concluir com a extração e `tipo_despesa: null` |
| **I3** | não existe `README.md` de execução | **adiado:** o `ContextoProjeto.md` é a documentação técnica consolidada (inclui comandos de execução) | README público/de execução |

### MELHORIA (pode ficar para depois)

| # | Achado |
| --- | --- |
| M1 | `djangorestframework` está em `requirements.txt` e em `INSTALLED_APPS`, mas **não é usado**. **Decisão D-M1: não alterar antes da entrega** |
| M2 | Ordem das chaves do JSON definida em dois lugares (`_montar_resultado` e `CHAVES_RESULTADO` em `views.py`) |
| M3 | Processamento síncrono (até cerca de 6 min no pior caso); em produção seria em segundo plano |
| M4 | Arquivo vazio mostra a mensagem do Django ("O arquivo submetido está vázio.") em vez da mensagem da GR-8 |
| M5 | `/favicon.ico` 404 (irrelevante) |
| M6 | Nos slides, o exemplo tem Agent2 "persiste"; aqui o Agent2 **classifica** e a persistência é do serviço. Está dentro da proposta (A2A sequencial), mas **vale explicar na apresentação** |
| M7 | Módulo `financeiro` (`LancamentoFinanceiro`/`Parcela`) não é alimentado pela extração (2ª etapa) |
| M8 | Com `DJANGO_DEBUG=False` e `ALLOWED_HOSTS = []`, o `runserver` recusa requisições; a demonstração usa `DJANGO_DEBUG=True` (comandos em `ContextoProjeto.md`, seção 20) |
| M9 | "Contas a pagar" não é verificado; qualquer NF válida é aceita |

**Documentação:** a única divergência encontrada (este arquivo ainda dizia "GR-14 aguardando commit/PR") foi corrigida na etapa 1.

**Código morto:** nenhum relevante. `ProcessamentoError` é base de `DocumentoEmProcessamentoError`; o endpoint JSON `upload_documento` não é usado pela tela, mas é mantido de propósito (contrato da GR-7).

---

## 20. Decisões da GR-21

Tomadas na etapa 2. **Decisão geral: manter o MVP como está; nenhum código é alterado.**

| # | Tema | Decisão | Justificativa |
| --- | --- | --- | --- |
| **D-I1** | Estrutura para múltiplas classificações | **Aceito como limitação do MVP.** Continua `"tipo_despesa": "<VALOR>"`, valor único por documento; **sem** `classificacoes`; JSON e `AgentClassificador` inalterados | o MVP trabalha com uma classificação principal por nota fiscal; múltiplas classificações ficam como evolução futura |
| **D-I2** | Notas fora das 2 categorias | **Aceito como limitação do MVP.** Categorias continuam só `MANUTENCAO_E_OPERACAO` e `INFRAESTRUTURA_E_UTILIDADES`; fora delas → `ClassificacaoInconclusivaError` → `ERRO` (`classificacao_inconclusiva`) → a interface mostra a limitação e permite nova tentativa. **Sem** ampliar categorias e **sem** `CONCLUIDO` com `tipo_despesa: null` | as duas categorias correspondem aos exemplos fornecidos na atividade e bastam para o escopo atual |
| **D-I3** | README | **Não criar `README.md` na GR-21** | o `ContextoProjeto.md` já é a documentação técnica consolidada; um README público/de execução pode vir depois |
| **D-M1** | Django REST Framework (sem uso) | **Não alterar** | evitar mudanças desnecessárias antes da entrega |

---

## 21. Plano da GR-21

| Etapa | Situação |
| --- | --- |
| 1 — Auditoria | ✅ concluída |
| 2 — Decisões | ✅ concluída (MVP mantido; seção 20) |
| 3 — Correções de código | ⏭ não necessária (nenhuma correção aprovada) |
| 4 — Validação manual final | ✅ concluída (seção 18.1) |
| 5 — Nova chamada à Gemini | ⏭ **dispensada** |
| 6 — Encerramento | ⬅ **AGORA**: validação concluída, aguardando commit/PR |

**Por que a etapa 5 foi dispensada:** já existem **duas evidências reais** com a Gemini, o **ID 1** (pelo backend) e o **ID 2** (pela interface Web), ambos `CONCLUIDO` e conferidos com o PDF (seção 18). Uma nova execução da mesma nota **não acrescenta evidência** e só consome cota. Os casos sem evidência real (várias parcelas, categoria INFRAESTRUTURA) dependeriam de novos PDFs fictícios e estão cobertos por testes automatizados.

**Etapa 6 — Encerramento:** `check`, `test`, `git diff --check`, `git status` e `git diff` executados (seção 25).

> **Observação de estabilidade:** na **primeira** execução da suíte no encerramento houve **1 falha intermitente** (`FAILED (failures=1)`), com **nenhum código alterado**. O nome do teste não foi capturado, porque essa execução mostrou só o resumo. Em seguida a suíte completa passou em **19 execuções consecutivas** (303 OK), e os testes sensíveis a tempo ou transação (`ReservaConcorrenteTests` e as classes `...FalhaAoSalvarTests`) passaram em mais **20 execuções**. **Não reproduzido.** Se reaparecer, rodar `python manage.py test -v 2` e registrar o teste, para tratar numa tarefa própria.

Falta, **somente com autorização**:

1. `git add analisetemporaria.md ContextoProjeto.md`;
2. `git diff --cached`;
3. commit, push e PR para a `main`.

---

## 22. Arquivos

**Alterados na GR-21 (só documentação):**

| Arquivo | Situação |
| --- | --- |
| `analisetemporaria.md` | modificado (auditoria + decisões) |
| `ContextoProjeto.md` | **novo** (contexto estável; decisões consolidadas) |

**Nenhum arquivo de código será alterado na GR-21** (etapa 3 não necessária). Continuam intocados: `agents/**` (incluindo `gemini_client.py`, extrator e classificador), `documentos/processamento.py`, `models.py`, `forms.py`, `validators.py`, `views.py`, `urls.py`, `migrations/**`, templates, CSS, JS, `config/**`, `requirements.txt`, `.env` e `.env.example`. Nenhum `README.md` é criado (D-I3).

---

# Parte IV — Operação

## 23. Guia da Gemini API

### 23.1 Conferir a configuração sem expor a chave

```bash
python manage.py shell -c 'from django.conf import settings; print("API Key carregada:", bool(settings.GEMINI_API_KEY)); print("Modelo:", settings.GEMINI_MODEL)'
```

- Esperado: `API Key carregada: True` e `Modelo: <modelo configurado>`. **Nunca** use `print(settings.GEMINI_API_KEY)`.
- `.env`: `GEMINI_API_KEY=`, `GEMINI_MODEL=`, `GEMINI_TIMEOUT_SEGUNDOS=60`, `GEMINI_MAX_TENTATIVAS=3`.
- O modelo vem **só** de `GEMINI_MODEL` (`.env` → `settings` → `GeminiClient.modelo` → `/v1beta/models/<modelo>:generateContent`). Os dois Agents usam o mesmo.
- Cada `manage.py shell` relê o `.env`. **O `runserver` precisa ser reiniciado** depois de alterar o `.env`.
- ⚠️ Uma **variável exportada no terminal vence o `.env`** (`load_dotenv()` não sobrescreve). Confira com `echo $GEMINI_MODEL` e remova com `unset GEMINI_MODEL`.

### 23.2 Retry e timeout

- **Retry:** 3 tentativas no total por chamada, feitas pelo SDK (408/429/500/502/503/504, timeout, conexão). Não crie retry manual. Não resolve cota diária esgotada.
- **Timeout:** 60 s por tentativa. Pior caso por documento (2 chamadas) ≈ 6 min.

### 23.3 Diagnóstico por sintoma

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

### 23.4 Modelos já testados

Resultado do momento de cada teste; nada é permanente.

| Modelo | Observado |
| --- | --- |
| `gemini-3.8-flash` | 503 e depois 429 por cota; usável em outro momento |
| `gemini-3.7-flash` | 503 |
| `gemini-3.5-flash-lite` | processou o PDF com structured output |

### 23.5 Teste manual do processamento pelo shell (API real; uma vez só)

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

### 23.6 Se a Gemini parar de funcionar

1. Não altere código.
2. Confira a chave e o modelo (23.1).
3. Leia `metadados["erro"]` (na tela ou no admin) e o log do terminal.
4. 429 → cota; 503 → aguardar; timeout → serviço, rede e PDF.
5. CPF/CNPJ inválido ou classificação inconclusiva **não** são falha da API.
6. Rode `python manage.py test`, que não chama a API real.
7. Só altere código se testes ou auditoria indicarem defeito interno.

---

---

## 24. Checklist de segurança

Situação confirmada nas auditorias da GR-14 e da GR-21:

- [x] `.env` nunca vai para o Git (`git check-ignore -v .env` → `.gitignore:12`; não rastreado).
- [x] A API Key nunca aparece em commit, PR, chat, log, **tela** ou documentação. Se vazar, revogue no AI Studio. *(Confirmado: o valor real e padrões de chave Google estão ausentes de todos os arquivos versionáveis; a tela não mostra chave.)*
- [x] `uploads/` e `media/` continuam ignorados; notas fiscais reais nunca são versionadas (`.gitignore:20` e `:19`; não rastreados).
- [x] A interface não expõe PDFs por URL, nem traceback, `__cause__`, status HTTP ou modelo em uso (testes + validação manual).
- [x] Formulários com `{% csrf_token %}`; nada de `|safe` em conteúdo vindo do banco (testes de CSRF e de templates).
- [x] Testes automatizados nunca chamam a API real; documentos de teste são fictícios.
- [x] Antes do commit: `git status` e `git diff` (executados na auditoria final).
- [x] `git diff --cached` executado antes do commit da GR-14 (PR #13).
- [x] GR-21: `git status` e `git diff` executados no encerramento.
- [ ] GR-21: `git diff --cached`, **pendente** até o `git add`.

---

## 25. Estado do Git

| Item | Estado |
| --- | --- |
| Branch | `feature/GR-21-validacao-final` |
| Base | `main` em `acedf6b` (merge da GR-14, **PR #13**); a branch está idêntica à `main` |
| Working tree antes da auditoria | limpa |
| GR-21 | **validação concluída, aguardando commit/PR** |
| Alterações da GR-21 | `M analisetemporaria.md` · `?? ContextoProjeto.md`: **só documentação; nenhum código alterado** |
| Arquivos do commit | `analisetemporaria.md`, `ContextoProjeto.md` |
| `git add` / commit / push / PR | **não realizados** |
| `.env` / `uploads/` / `media/` | ignorados e não rastreados |
| Banco local (referências de desenvolvimento) | migrations aplicadas; ID 1 e ID 2 em `CONCLUIDO`; ID 4 em `ERRO` (teste de `documento_ilegivel`) |
