# Gestão Rural - Contexto do Projeto

> **Contexto oficial e estável do projeto.** Registra a arquitetura consolidada, os contratos, as regras e o estado geral.
> Auditorias, investigações e decisões em andamento ficam em `analisetemporaria.md` (seção 19).
>
> Nunca registrar aqui: chaves, valores do `.env` ou dados pessoais reais.

---

## 1 - Visão Geral

- **Disciplina:** ESW424 – Prática de Engenharia de Software. Avaliação N2, 1ª etapa: atividade "Agentes Inteligentes".
- **Objetivo:** processar **notas fiscais de contas a pagar em PDF** de uma propriedade rural, usando **Agents de IA (Google Gemini)**:
  - extrair os dados da nota;
  - classificar o tipo de despesa;
  - devolver um **JSON** estruturado.
- **Finalidade do sistema:** base de um sistema de gestão financeira rural. O módulo financeiro (lançamentos, parcelas, amortizações) já existe como modelo, mas ainda não é alimentado pela extração.
- **Como funciona para o usuário:** uma **interface Web** (Django) em que o usuário:
  1. carrega o PDF;
  2. aciona o processamento por um botão;
  3. vê o JSON final na tela.
- **Agents:**
  - um Agent **extrai** os dados do PDF (Gemini, entrada multimodal);
  - outro Agent **classifica** a despesa a partir dos itens (Gemini).
  - Um serviço orquestra os dois e grava o resultado no banco.

---

## 2 - Requisitos da Atividade

Consolidados a partir dos slides da atividade (18 a 21).

**Funcionais:**

- Receber o PDF de uma nota fiscal de **contas a pagar**.
- Utilizar **Agents** (Gemini recomendado).
- Devolver os dados em **JSON**.
- **Interface Web:** upload do PDF → **botão** para processar → **JSON exibido na tela**.

**Campos exigidos no JSON:**

| Grupo | Campos |
| --- | --- |
| Fornecedor | razão social, nome fantasia, CNPJ |
| Faturado | nome completo, CPF |
| Nota | número, data de emissão |
| Itens | descrição dos produtos |
| Parcelas | quantidade, vencimento, **estrutura para múltiplas parcelas** |
| Financeiro | valor total |
| Classificação | **TipoDespesa**, interpretado pelo Gemini com base nos produtos |

**Regras:**

- **Não é necessário** criar uma entidade Produto.
- A classificação **não** é copiada do PDF: é interpretada pelo Gemini a partir dos produtos.
- Exemplos dos slides: Óleo Diesel → MANUTENÇÃO E OPERAÇÃO; Material Hidráulico → INFRAESTRUTURA E UTILIDADES.
- Os slides pedem "uma classificação de DESPESA por registro, porém com estrutura para receber mais de uma" (ver **DECISÃO DO MVP** na seção 11).

**Avaliação:**

| Peso | Critério |
| --- | --- |
| 40% | uso do Agent conforme estrutura |
| 30% | conteúdo do JSON |
| 30% | assertividade da classificação da despesa |

---

## 3 - Arquitetura Atual

| Camada | Tecnologia |
| --- | --- |
| Backend | Python + **Django 6.1** |
| Banco | **PostgreSQL** (`psycopg`); resultados em `JSONField` (`jsonb`) |
| IA | **Google Gemini** via SDK `google-genai`, com structured output (schemas **Pydantic v2**) |
| Interface | **Django Templates + HTML + CSS + JavaScript simples** (sem frontend separado, CDN ou build) |
| Configuração | `.env` carregado por `python-dotenv` |

**Fluxo principal:**

```
Navegador
 → DocumentoUploadForm → validar_pdf            (validação do PDF)
 → Documento (PENDENTE)                          (PostgreSQL + arquivo em media/)
 → botão Processar → processar_documento         (orquestração)
     → AgentExtrator      → Gemini → NotaFiscalExtraida
     → AgentClassificador → Gemini → ClassificacaoDespesa
 → JSON final → Documento.resultado_estruturado  (PostgreSQL, CONCLUIDO)
 → interface exibe resumo + JSON
```

**Coordenação dos Agents:** sequencial e síncrona. O Agent 1 extrai; o Agent 2 classifica a partir da saída do Agent 1; o serviço de orquestração persiste.

---

## 4 - Estrutura Principal

| Diretório | Responsabilidade |
| --- | --- |
| `config/` | settings do Django (`.env`, PostgreSQL, limite de upload, `GEMINI_*`) e URLs raiz (`/` → `/documentos/`, `admin/`, `documentos/`) |
| `documentos/` | model `Documento`, upload e validação de PDF, orquestração (`processamento.py`), views, templates e static da interface Web |
| `agents/` | pacote dos Agents; `gemini_client.py` é o **único** ponto de contato com o SDK da Gemini |
| `agents/extrator/` | `AgentExtrator` + schema `NotaFiscalExtraida` (extração do PDF) |
| `agents/classificador/` | `AgentClassificador` + schema `ClassificacaoDespesa` (TipoDespesa) |
| `financeiro/` | `LancamentoFinanceiro`, `Parcela`, `Amortizacao` (fora do fluxo da 1ª etapa) |
| `usuarios/` | `Usuario` (usuário customizado) e `Titular` |

Arquivos locais **não versionados:** `.env`, `uploads/` (PDFs de teste) e `media/` (PDFs enviados).

---

## 5 - Documento e Estados

`documentos/models.py::Documento`:

| Campo | Uso |
| --- | --- |
| `arquivo` | PDF em `media/documentos/` |
| `nome_original` | nome sanitizado |
| `enviado_em` | data do upload |
| `status` | estado do processamento |
| `resultado_estruturado` | JSON final (só em `CONCLUIDO`) |
| `metadados` | informações do processamento e erro seguro |

| Estado | Como se chega |
| --- | --- |
| `PENDENTE` | upload aceito (estado inicial) |
| `PROCESSANDO` | `processar_documento` reservou o documento (a partir de `PENDENTE` ou `ERRO`) |
| `CONCLUIDO` | Extrator e Classificador terminaram e o JSON foi gravado. **Estado final:** não reprocessa |
| `ERRO` | qualquer falha no processamento. Permite nova tentativa (volta a `PROCESSANDO`) |

```
PENDENTE → PROCESSANDO → CONCLUIDO
                ↓
               ERRO → PROCESSANDO (nova tentativa)
```

Um documento preso em `PROCESSANDO` (processo interrompido) é destravado manualmente no Django Admin, mudando o status para `ERRO`.

---

## 6 - Upload e Validação

| Componente | Local | Papel |
| --- | --- | --- |
| `DocumentoUploadForm` | `documentos/forms.py` | form com o campo `arquivo`; chama `validar_pdf` |
| `validar_pdf` | `documentos/validators.py` | fonte única da validação do PDF |
| `_salvar_documento` | `documentos/views.py` | cria o `Documento` (`PENDENTE`), usado pela tela e pelo endpoint JSON |

**Regras:**

- Só **PDF** (extensão `.pdf`); arquivo não vazio.
- Tamanho máximo: `MAX_PDF_UPLOAD_SIZE_MB` (padrão **10 MB**).
- `content_type` igual a `application/pdf`.
- Cabeçalho **`%PDF-`**.
- **Sanitização** do nome (`get_valid_filename`).
- Se a gravação falhar **depois** que o arquivo foi salvo no storage, o arquivo é **removido** (sem órfãos) e a exceção é relançada. A view mostra "Não foi possível salvar o documento."

---

## 7 - GeminiClient

`agents/gemini_client.py::GeminiClient`, compartilhado pelos Agents.

- **Configuração** (via `settings`, lida do `.env`):

  | Variável | Uso |
  | --- | --- |
  | `GEMINI_API_KEY` | chave da API (**nunca** registrar o valor) |
  | `GEMINI_MODEL` | modelo usado pelos dois Agents |
  | `GEMINI_TIMEOUT_SEGUNDOS` | timeout **por tentativa** (padrão 60) |
  | `GEMINI_MAX_TENTATIVAS` | tentativas **no total** (padrão 3) |

- **Métodos:** `gerar_conteudo(...) -> str` e `gerar_json(...) -> dict | list`. Os Agents usam `gerar_json` com schema Pydantic e `temperatura=0`.
- **Retry:** feito pelo SDK para HTTP 408/429/500/502/503/504, timeout e falha de conexão. Não criar loops de retry manuais.
- **Exceções** (base `GeminiError`):
  - `GeminiConfiguracaoError`: chave ou modelo ausentes/inválidos;
  - `GeminiTimeoutError`;
  - `GeminiAPIError(status_code)`: erro da API ou de rede;
  - `GeminiRespostaInvalidaError`: resposta vazia ou JSON inválido.
- As mensagens nunca contêm a chave.

---

## 8 - AgentExtrator

`agents/extrator/agent.py`:

```python
AgentExtrator(cliente=None).extrair_documento(documento) -> NotaFiscalExtraida
```

- Lê o PDF pelo storage e envia ao Gemini como `application/pdf`. **Não altera o `Documento`.**
- **Saída `NotaFiscalExtraida`** (`agents/extrator/schemas.py`):
  - `fornecedor{razao_social, nome_fantasia, cnpj}`;
  - `faturado{nome, cpf}`;
  - `numero_nota`;
  - `data_emissao` (`date`);
  - `itens[]{descricao, quantidade, valor_unitario, valor_total}`;
  - `parcelas[]{numero, data_vencimento, valor}`;
  - `valor_total` (`Decimal` > 0);
  - `validacoes` (calculado localmente).
- **Obrigatórios:** documento reconhecido como nota fiscal, ≥ 1 item com descrição e `valor_total`. Os demais campos, quando ausentes, ficam `null` (nunca inventados).
- **Política de CPF/CNPJ:**
  - o CPF/CNPJ extraído é **preservado** (normalizado: CPF com 11 dígitos, CNPJ com 14 caracteres, inclusive o **alfanumérico**);
  - a validade dos **dígitos verificadores** é conferida **localmente** e informada em `validacoes` (`valido` / `invalido` / `ausente`);
  - a **existência real** da pessoa ou empresa **não** é verificada;
  - **DV inválido não invalida a nota**, que continua sendo processada. Só uma estrutura impossível (tamanho errado, caracteres inválidos) invalida a resposta.
- **Exceções** (base `ExtratorError`):
  - `DocumentoIlegivelError` (`documento_ilegivel`);
  - `ExtracaoIndisponivelError` (`servico_indisponivel`);
  - `ExtracaoInvalidaError` (`resposta_invalida`).

---

## 9 - AgentClassificador

`agents/classificador/agent.py`:

```python
AgentClassificador(cliente=None).classificar(nota: NotaFiscalExtraida) -> ClassificacaoDespesa
```

- **Entrada:** o `NotaFiscalExtraida` produzido pelo Extrator. O Classificador envia ao Gemini **só** os itens (descrição, quantidade, valor), o fornecedor (razão social e nome fantasia) e o valor total. Não envia CPF, CNPJ nem dados do faturado.
- **Saída `ClassificacaoDespesa`:** `tipo_despesa` (Enum `TipoDespesa`) e `justificativa` (texto curto).
- **A classificação é produzida pelo Gemini a partir dos itens.** Não é copiada do PDF nem definida na interface.
- **Categorias atuais:**
  - `MANUTENCAO_E_OPERACAO`;
  - `INFRAESTRUTURA_E_UTILIDADES`.
- **Exceções** (base `ClassificadorError`):
  - `ClassificacaoIndisponivelError` (`servico_indisponivel`);
  - `ClassificacaoInvalidaError` (`classificacao_invalida`);
  - `ClassificacaoInconclusivaError` (`classificacao_inconclusiva`): os itens não se encaixam nas categorias.

---

## 10 - Orquestração

`documentos/processamento.py`:

```python
processar_documento(documento_id, *, extrator=None, classificador=None) -> Documento
```

```
PENDENTE ou ERRO → PROCESSANDO → AgentExtrator → AgentClassificador → JSON → CONCLUIDO
                                        └── qualquer falha ──────────────────→ ERRO
```

- **Reserva:** transação curta com **`transaction.atomic()` + `select_for_update()`**. A transação termina **antes** das chamadas à Gemini.
- **Concorrência:** uma segunda execução simultânea espera o lock, encontra `PROCESSANDO` e recebe `DocumentoEmProcessamentoError`, sem chamar os Agents.
- **`CONCLUIDO` não reprocessa:** o serviço devolve o documento sem gastar cota.
- **Documento inexistente:** `Documento.DoesNotExist`.
- **Erros persistidos de forma segura:**
  - em `ERRO`, `resultado_estruturado = {}` e `metadados["erro"] = {etapa, codigo, mensagem}`, com mensagem fixa e segura;
  - nunca são gravados traceback, `__cause__`, status HTTP, resposta bruta da Gemini ou chave;
  - não há gravação parcial: se a classificação falha, a extração é descartada.
- **Metadados de sucesso:** `metadados["processamento"]` com versão do resultado, datas de início e fim, versão de schema e modelo de cada Agent, e a **justificativa** da classificação.

---

## 11 - JSON Final

Estrutura oficial atual de `Documento.resultado_estruturado`:

```json
{
  "fornecedor": {"razao_social": "...", "nome_fantasia": "...", "cnpj": "..."},
  "faturado": {"nome": "...", "cpf": "..."},
  "numero_nota": "...",
  "data_emissao": "AAAA-MM-DD",
  "itens": [{"descricao": "...", "quantidade": "...", "valor_unitario": "0.00", "valor_total": "0.00"}],
  "quantidade_parcelas": 1,
  "parcelas": [{"numero": 1, "data_vencimento": "AAAA-MM-DD", "valor": "0.00"}],
  "valor_total": "0.00",
  "tipo_despesa": "MANUTENCAO_E_OPERACAO",
  "validacoes": {
    "fornecedor_cnpj": {"status": "valido", "motivo": null},
    "faturado_cpf": {"status": "invalido", "motivo": "digitos_verificadores_invalidos"}
  }
}
```

- **Valores monetários:** strings com 2 casas (`"3086.75"`), sem perda de precisão.
- **Datas:** ISO `AAAA-MM-DD`.
- **`quantidade_parcelas`:** `len(parcelas)` (`0` para nota à vista).
- **Persistência:** `JSONField` no PostgreSQL (`jsonb`), que **não preserva a ordem das chaves**. A ordem mostrada na tela é **apenas apresentação**: a view reordena.
- **Fora do JSON:** `documento_e_nota_fiscal` e a `justificativa`, que fica em `metadados`.

> **DECISÃO DO MVP:** `tipo_despesa` permanece **escalar**, uma classificação principal por documento, o que é suficiente para este MVP. A estrutura para várias classificações, mencionada nos slides, fica como **evolução futura**.

---

## 12 - Interface Web

| Rota | Nome | Função |
| --- | --- | --- |
| `/` | `inicio` | redireciona para `/documentos/` |
| `/documentos/` | `documento_inicio` | GET: formulário de upload + 10 documentos recentes. POST: upload (validação da GR-8) → página do documento |
| `/documentos/upload/` | `documento_upload` | endpoint **JSON** de upload (POST): 201 / 400 / 500 |
| `/documentos/<id>/` | `documento_detalhe` | página do documento (só leitura) |
| `/documentos/<id>/processar/` | `documento_processar` | POST: chama **somente** `processar_documento(pk)` e volta para a página do documento com uma mensagem |

**Página do documento por status:**

| Status | Exibição |
| --- | --- |
| `PENDENTE` | "Pronto para processar." + botão **Processar** |
| `PROCESSANDO` | mensagem + atualização automática a cada 5 s (`meta refresh`); sem botão |
| `CONCLUIDO` | **resumo** (tipo de despesa, valor total, parcelas, fornecedor, número, data) + **avisos de validação** de CPF/CNPJ + **justificativa** + **JSON final** formatado |
| `ERRO` | **mensagem segura** + orientação pelo código do erro + botão **Tentar novamente** |

- `documentos.js` só desabilita o botão e mostra "Enviando..." / "Processando..." (proteção **visual** contra clique duplo). A página funciona sem JavaScript.
- As views **não** usam Agents nem o `GeminiClient`: a única entrada de processamento é `processar_documento`.

---

## 13 - Segurança

Regras permanentes:

- `.env`, `uploads/` e `media/` **nunca** versionados (estão no `.gitignore`).
- **API Key nunca** no código, na documentação, em logs ou na interface.
- **CSRF** em todos os POSTs.
- **`@staff_member_required`** em todas as páginas (login pelo `/admin/login/`).
- **Escape automático** do Django; nada de `|safe` com conteúdo vindo do banco.
- **PDF não exposto por URL** (sem link para o arquivo; `MEDIA_URL` não é servido).
- Traceback, `__cause__`, status HTTP, modelo e resposta bruta da Gemini **não aparecem** na interface nem em `metadados`.
- Notas fiscais reais não são versionadas; os testes usam documentos fictícios.

---

## 14 - Testes

Estado consolidado: **303 testes passando** (`python manage.py test`).

| Área | Onde |
| --- | --- |
| GeminiClient | `agents/test_gemini_client.py` |
| Extrator | `agents/extrator/test_schemas.py`, `test_agent.py` |
| Classificador | `agents/classificador/test_schemas.py`, `test_agent.py` |
| Documento | `documentos/tests.py` |
| Upload e validação | `documentos/test_upload.py`, `documentos/test_interface.py` |
| Orquestração (incl. concorrência real) | `documentos/test_processamento.py` |
| Interface Web (incl. integração com Agents falsos) | `documentos/test_interface.py` |
| Financeiro | `financeiro/tests.py` |

**Regra:** testes automatizados **nunca** fazem chamadas reais à Gemini. Usam `GeminiClient` ou Agents falsos, o SDK patchado para falhar e `GEMINI_API_KEY=None`. Chamadas reais só em teste manual controlado, por causa da cota.

---

## 15 - Testes Reais Já Realizados

Os IDs abaixo são **referências do ambiente local de desenvolvimento**, não dados do sistema.

| Documento | Como | Resultado |
| --- | --- | --- |
| **ID 1** | processamento real pelo backend (shell, `processar_documento`) com PDF fictício | `CONCLUIDO` |
| **ID 2** | **upload e processamento real pela interface Web** com o mesmo PDF fictício | `CONCLUIDO` |

**Resultado do ID 2:**

- tipo de despesa **Manutenção e operação**;
- valor total **R$ 3.086,75**;
- **1** parcela;
- JSON exibido na tela;
- CPF fictício sinalizado como "dígitos verificadores inválidos", sem impedir o processamento;
- justificativa exibida.

---

## 16 - Git e Fluxo de Trabalho

```
main
 → feature/GR-N-descricao
 → implementação
 → testes (python manage.py test / check / git diff --check)
 → commit
 → push
 → Pull Request
 → merge
 → atualizar a main local
 → apagar a feature branch mergeada
```

- Mensagens de commit no padrão `tipo(escopo): descrição GR-N` (ex.: `feat(documentos): implementar interface web GR-14`).
- `git add` com a lista explícita de arquivos, seguido de `git diff --cached` antes do commit.
- **Não** apagar branches antigas automaticamente: conferir antes que foram mergeadas (`git branch --merged main`).

---

## 17 - Estado das Tarefas

| Tarefa | Descrição | Estado |
| --- | --- | --- |
| GR-6 | Modelar `Documento` | ✅ |
| GR-7 | Upload de PDF | ✅ |
| GR-8 | Validação de PDF | ✅ |
| GR-9 | `GeminiClient` | ✅ |
| GR-10 | Agent Extrator | ✅ |
| GR-11 | Agent Classificador | ✅ |
| GR-12 | Orquestração | ✅ |
| GR-14 | Interface Web | ✅ (mergeada pelo **PR #13**) |
| **GR-21** | **Validação final** | ✅ **validação concluída, aguardando commit/PR** |

Branch atual: **`feature/GR-21-validacao-final`**.

---

## 18 - GR-21 - Situação Atual

**Validação concluída, aguardando commit/PR.** A auditoria (código + slides) não encontrou nenhum problema **crítico**. O MVP foi **mantido como definido**, e **nenhum código precisou ser alterado**.

**Decisões consolidadas (escopo do MVP):**

- **Uma classificação principal por documento:** `tipo_despesa` escalar. Múltiplas classificações = evolução futura.
- **Somente duas categorias de TipoDespesa:** `MANUTENCAO_E_OPERACAO` e `INFRAESTRUTURA_E_UTILIDADES`, os exemplos da atividade. Itens fora delas → `ERRO` (`classificacao_inconclusiva`), com a limitação explicada na tela e nova tentativa.
- **README adiado** para evolução futura. Este arquivo é a documentação técnica consolidada.
- Django REST Framework (instalado, sem uso) não é alterado antes da entrega.

**Validação manual final concluída:**

- documento concluído conferido na interface;
- estado `ERRO` com mensagem segura e "Tentar novamente";
- arquivo ilegível → `ERRO`, sem chamar a Gemini;
- estado `PROCESSANDO` sem botões.

Os demais comportamentos (acesso, PDFs inválidos, CSRF, XSS, sem exposição de PDF ou dados internos) estão cobertos pela suíte automatizada.

**Nova chamada à Gemini dispensada:** os documentos ID 1 (backend) e ID 2 (interface) já são a evidência real do fluxo completo.

Detalhes: `analisetemporaria.md`.

---

## 19 - Arquivos de Contexto

| Arquivo | Papel |
| --- | --- |
| `ContextoProjeto.md` | **contexto oficial e estável**: arquitetura, contratos, regras, fluxo, comandos, decisões consolidadas e estado geral. Atualizado **só** quando algo se consolida (ex.: uma tarefa é mergeada ou uma decisão é tomada) |
| `analisetemporaria.md` | **área de trabalho**: auditorias, investigações, relatórios de execução, planos de etapa e decisões em andamento. Pode ser reescrito a cada tarefa |

Regra: informação temporária ou detalhada vai para `analisetemporaria.md`; quando virar decisão ou contrato estável, é resumida aqui. Assim este arquivo não cresce a cada tarefa.

---

## 20 - Comandos Essenciais

**Ambiente:**

```bash
source .venv/bin/activate          # ativar o ambiente virtual (Linux/macOS)
pip install -r requirements.txt
cp .env.example .env               # preencher DJANGO_SECRET_KEY, DB_*, GEMINI_* (nunca versionar)
```

**Django:**

```bash
python manage.py migrate
python manage.py createsuperuser   # a interface exige usuário staff
python manage.py check
python manage.py test              # não chama a Gemini real
python manage.py runserver         # com DJANGO_DEBUG=True no .env em desenvolvimento
```

Acesso: `http://127.0.0.1:8000/` → login do admin → `/documentos/`.

**Git:**

```bash
git status
git log --oneline --decorate
git branch -vv
git diff --check
git check-ignore -v .env uploads/ media/
```

**Gemini (configuração sem expor a chave):**

```bash
python manage.py shell -c 'from django.conf import settings; print("API Key carregada:", bool(settings.GEMINI_API_KEY)); print("Modelo:", settings.GEMINI_MODEL)'
```

- **Nunca** usar `print(settings.GEMINI_API_KEY)`.
- Uma variável exportada no terminal tem prioridade sobre o `.env` (use `unset GEMINI_MODEL` se necessário).
- Diagnóstico de 429/503 e demais erros da Gemini: `analisetemporaria.md` (guia da Gemini API).
