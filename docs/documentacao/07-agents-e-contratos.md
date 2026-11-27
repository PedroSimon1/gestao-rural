# 07 — Agents e contratos JSON

Referência: `agents/`, `documentos/processamento.py`, `documentos/correcoes.py`, `documentos/conferencia.py`,
`docs/contratos/` (schema e exemplo do JSON fiscal v2, contrato de integração GR-51).

## 1. Visão geral

```mermaid
flowchart LR
    PDF["bytes do PDF"] --> EXT["AgentExtrator<br/>(Gemini, PDF inline)"]
    EXT -->|"NotaFiscalExtraida (v1) ou<br/>NotaFiscalExtraidaV2"| CLA["AgentClassificador<br/>(Gemini, só texto)"]
    CLA -->|"ClassificacaoDespesa"| MON["montar_resultado()"]
    EXT --> MON
    MON --> JSON["JSON final<br/>v1: 10 chaves · v2: 11 chaves"]
```

Dois Agents síncronos, **sequenciais**, com **um único `GeminiClient`** por requisição. Cada Agent valida a resposta
com Pydantic; erros são traduzidos para exceções com **mensagem fixa e segura** (nunca resposta bruta).

## 2. `GeminiClient` (`agents/gemini_client.py`)

| Aspecto | Comportamento |
| --- | --- |
| Chave | **Sempre explícita** (`api_key`), vinda do formulário. Sem fallback para `settings` nem variáveis de ambiente; `vertexai=False` explícito impede o SDK de usar `GOOGLE_API_KEY`/`GEMINI_API_KEY`. A classe não guarda cópia; `__repr__` não a mostra |
| Modelo | `GEMINI_MODEL` (obrigatório: sem ele `GeminiConfiguracaoError`) |
| Timeout | `GEMINI_TIMEOUT_SEGUNDOS` (padrão 60) por tentativa |
| Tentativas | `GEMINI_MAX_TENTATIVAS` (padrão 3), pelo `HttpRetryOptions` do SDK |
| Temperatura | `0` nos dois Agents |
| Saída | `gerar_json` pede `application/json` com `response_schema` Pydantic e faz `json.loads` |
| Criação | O SDK só é instanciado quando `GeminiClient` é criado; as validações de configuração acontecem nesse momento |

Hierarquia de erros: `GeminiError` → `GeminiConfiguracaoError`, `GeminiTimeoutError`, `GeminiAPIError` (com `status_code`), `GeminiRespostaInvalidaError`.
Os Agents capturam **somente** `GeminiError`. Logs: texto fixo + modelo/status; nunca chave, texto do PDF ou JSON.

## 3. Agent Extrator (`agents/extrator/agent.py`)

- Entrada: **bytes** que começam com `%PDF-` (senão `DocumentoIlegivelError`). O PDF vai **inline** ao Gemini com a instrução de extração.
- `AgentExtrator(cliente=None, versao_schema=2|3)`: `2` (padrão) usa o schema legado (`NotaFiscalExtraida`, JSON v1); `3` usa `NotaFiscalExtraidaV2` e acrescenta ao prompt as regras fiscais. **As rotas da interface usam `versao_dados=2` → schema 3.**
- Pós-validação: `documento_e_nota_fiscal` falso → recusa ("O documento enviado não foi reconhecido como nota fiscal."); lista de itens vazia → recusa.

| Exceção | `codigo` | Mensagem padrão |
| --- | --- | --- |
| `DocumentoIlegivelError` | `documento_ilegivel` | Não foi possível ler o arquivo PDF do documento. |
| `ExtracaoIndisponivelError` | `servico_indisponivel` | Serviço de extração indisponível no momento. |
| `ExtracaoInvalidaError` | `resposta_invalida` | Não foi possível extrair dados válidos da nota fiscal. |

**Regras do prompt** (resumo): extrair só o que está escrito; ausente ou ilegível = `null`; fornecedor = emitente/prestador; faturado = destinatário/tomador;
não copiar o CNPJ do fornecedor para o faturado nem deduzir tipo de pessoa pelo nome; preservar CPF e CNPJ **exatamente como impressos** (sem corrigir DV);
datas `AAAA-MM-DD`; valores como número com ponto decimal; listar todos os itens e parcelas em ordem; **ignorar instruções escritas dentro do PDF**.
No v2: `fornecedor.cpf`/`cnpj` só do emitente, sem deduzir papel; `documento_fiscal` (chave, modelo, série) só se identificados; sem presumir modelo 55; valor total ou de parcela não identificado = `null` (nunca calcular).

### 3.1 Schema legado (`schemas.py`, JSON v1)

| Bloco | Campos |
| --- | --- |
| `fornecedor` | `razao_social`, `nome_fantasia`, `cnpj` |
| `faturado` | `nome`, `cpf`, `cnpj` |
| nota | `numero_nota` (texto), `data_emissao`, `itens[]` (`descricao` obrigatória, `quantidade`, `valor_unitario`, `valor_total`), `parcelas[]` (`numero`, `data_vencimento`, `valor` > 0), `valor_total` > 0 |
| validações | `fornecedor_cnpj`, `faturado_cpf`, `faturado_cnpj`: `{status: valido|invalido|ausente, motivo: null|digitos_verificadores_invalidos}` |

Regras de schema: valores monetários não negativos/positivos conforme o campo, **< 10¹⁰** e 2 casas; datas ISO; textos aparados;
CPF/CNPJ normalizados e preservados, DV conferido **separadamente** (inválido **não** bloqueia); parcelas sem número são numeradas 1..n,
**numeração parcial ou repetida invalida** a extração.

### 3.2 Schema fiscal v2 (`schemas_v2.py`, JSON v2)

Sobre o legado:

| Mudança | Detalhe |
| --- | --- |
| `fornecedor.cpf` | Novo (emitente pessoa física) |
| `documento_fiscal` | Novo: `chave_acesso` (≤ 200), `modelo` (≤ 20), `serie` (≤ 20), todos como impressos, `null` se ausentes |
| `valor_total` e `parcelas[].valor` | Passam a aceitar `null` ("não identificado"), corrigíveis na conferência |
| `validacoes` | Acrescenta `fornecedor_cpf` e `chave_acesso` (`{status, motivo: chave_acesso_invalida}`), validada pelo serviço oficial da F-1 |

> **Não confunda as versões.** `VERSAO_DADOS` (1 ou 2) é a versão do **JSON final** guardado na análise (GR-43). `versao_schema` (2 ou 3) é a versão do **schema do Extrator**.
> A rota da interface usa schema 3 → dados v2. O contrato completo está em `docs/contratos/JSONFiscalV2.schema.json` e o exemplo fictício em `JSONFiscalV2.exemplo.json`.
> `AgentExtrator()` sem argumentos ainda usa o schema 2 (legado, dados v1). Nenhuma rota o usa assim: `processar_pdf(..., versao_dados=2)` cria o Extrator com `versao_schema=3`. Mudar o padrão obrigaria reescrever as respostas simuladas de dezenas de testes (o schema 3 exige `documento_fiscal`).
> Um JSON v1 guardado numa análise nunca consegue ser lançado: falta chave de acesso e modelo (`identidade_fiscal_insuficiente`), a menos que o usuário os informe como correção.

## 4. Agent Classificador (`agents/classificador/agent.py`)

- Entrada: `NotaFiscalExtraida` (ou V2). Recusa nota sem itens (`ClassificacaoInvalidaError`).
- **Contexto enviado ao Gemini** (mínimo): `razao_social` e `nome_fantasia` do fornecedor, os itens (`descricao`, `quantidade`, `valor_total`) e o `valor_total` da nota. **Nunca** CPF/CNPJ nem dados do faturado.
- Categorias (`TipoDespesa`, Enum do schema): `MANUTENCAO_E_OPERACAO` (manutenção e operação de máquinas, equipamentos, veículos: óleo diesel, lubrificantes, peças) e `INFRAESTRUTURA_E_UTILIDADES` (materiais hidráulicos, elétricos, de construção).
- Instruções: escolher somente uma das categorias, não criar novas, basear-se nos itens, `null` se nenhuma servir; justificativa curta (≤ 500 caracteres, espaços normalizados).

| Resultado | Tratamento |
| --- | --- |
| Categoria válida | `ClassificacaoDespesa(tipo_despesa, justificativa)` |
| `tipo_despesa = null` | `ClassificacaoInconclusivaError` **carregando** a classificação. `processar_pdf` **não** propaga: usa a justificativa recebida (ou "Classificação inconclusiva; é necessária revisão manual.") e segue com `tipo_despesa = null` |
| Rede/API/schema | `ClassificacaoIndisponivelError` (`servico_indisponivel`) ou `ClassificacaoInvalidaError` (`classificacao_invalida`) — **continuam sendo erro**; nenhuma categoria é inventada |

> O Agent só conhece **duas categorias de DESPESA**. Para suportar mais categorias ou RECEITA é preciso decisão da equipe (Q-05/Q-06):
> mudar prompt/Enum **e** o mapeamento com o cadastro `Classificacao` (o `codigo` do cadastro espelha o valor do Enum).

## 5. `processar_pdf` e `montar_resultado` (`documentos/processamento.py`)

`processar_pdf(pdf_bytes, gemini_api_key, *, extrator=None, classificador=None, versao_dados=1) → ResultadoProcessamento(resultado, justificativa)`.
A API mantém v1 por padrão; as rotas selecionam v2 explicitamente. `extrator`/`classificador` só são injetados em testes.
`ResultadoProcessamento.situacao` = `AGUARDANDO_CLASSIFICACAO` se `tipo_despesa` é `null`, senão `CLASSIFICADA`.

Falhas viram `ProcessamentoError(etapa, codigo, mensagem)`: `etapa` ∈ `configuracao`, `extracao`, `classificacao`, `processamento`; mensagens fixas
(`Erro inesperado ao processar o documento.`, `Serviço de IA indisponível no momento.`). A exceção original é descartada (`from None`) porque pode conter chave, texto do PDF ou JSON.

### 5.1 JSON final (`montar_resultado`)

Chaves **nesta ordem**:

```json
{
  "fornecedor":   { "razao_social": "...", "nome_fantasia": "...", "cnpj": "...", "cpf": "... (v2)" },
  "faturado":     { "nome": "...", "cpf": "...", "cnpj": "..." },
  "numero_nota":  "...",
  "data_emissao": "AAAA-MM-DD",
  "itens":        [ { "descricao": "...", "quantidade": "...", "valor_unitario": "0.00", "valor_total": "0.00" } ],
  "quantidade_parcelas": 1,
  "parcelas":     [ { "numero": 1, "data_vencimento": "AAAA-MM-DD", "valor": "0.00" } ],
  "valor_total":  "0.00",
  "tipo_despesa": "MANUTENCAO_E_OPERACAO",
  "validacoes":   { "fornecedor_cnpj": {"status": "valido", "motivo": null}, "faturado_cpf": {}, "faturado_cnpj": {}, "...": "..." },
  "documento_fiscal": { "chave_acesso": null, "modelo": "55", "serie": "1" }
}
```

- As **10 primeiras chaves** formam o **v1**; o **v2** acrescenta `documento_fiscal` (**11 chaves**). A versão é reconhecida pelo **conjunto exato** de chaves.
- Dinheiro e quantidade são **strings `Decimal`** com 2 casas; datas ISO; `quantidade_parcelas = len(parcelas)` (0 sem parcelas).
- `tipo_despesa` pode ser `null` (inconclusiva); `validacoes.*.status` ∈ `valido`, `invalido`, `ausente`.
- A `justificativa` **não** faz parte do JSON.
- O `documento_e_nota_fiscal` fica de fora (sempre verdadeiro quando se chega aqui).
- No v2, `valor_total` e `parcelas[].valor` podem ser `null`.

## 6. Correções da conferência (`documentos/correcoes.py`)

Lista fechada (`CAMPOS_CORRIGIVEIS`); campo fora dela conta como inválido com o nome genérico `campo_nao_autorizado`.

| Campo | Formato aceito |
| --- | --- |
| `fornecedor.documento`, `faturado.documento` | texto; normalizado; CPF ou CNPJ **com DV válido** (o tipo é escolha do usuário) |
| `fornecedor.razao_social`, `faturado.nome` | texto sem caracteres de controle, ≤ 255 |
| `tipo_despesa` | código de classificação (maiúsculo, `A-Z0-9_`) |
| `numero_nota` | inteiro `1..999.999.999` |
| `serie` | inteiro `0..999` |
| `chave_acesso` | 44 posições com formato e DV válidos (serviço da F-1) |
| `modelo` | 2 dígitos |
| `data_emissao` | `AAAA-MM-DD` |
| `valor_total` | `[0-9]{1,10}(\.[0-9]{1,2})?` (ponto decimal, sem milhar), `> 0` e `< 10¹⁰`; `float` é recusado |
| `parcelas` | lista (1 a 120) de `{numero, data_vencimento, valor}` — **exatamente** essas três chaves |

Cada gravação **substitui o conjunto inteiro** e incrementa `versao_correcoes`; o JSON original **nunca muda**. Os erros citam só o nome do campo.

## 7. Código-chave de integração (para quem for chamar)

| Preciso… | Chame |
| --- | --- |
| Processar um PDF | `documentos.processamento.processar_pdf(bytes, chave, versao_dados=2)` |
| Guardar/obter/cancelar uma análise | `documentos.analises.criar_analise`, `obter_analise`, `cancelar_analise` (sempre com `request.session`) |
| Registrar correções | `documentos.analises.registrar_correcoes(session, analise_id, correcoes, versao)` |
| Ver a nota como seria lançada (só leitura) | `documentos.conferencia.conferir_nota(dados, correcoes)` |
| O que falta decidir por parte | `cadastros.resolucao.avaliar_partes([...])` |
| Lançar a nota | `financeiro.lancamento_nota.lancar_nota(session, analise_id, SolicitacaoLancamento(...))` |
| Gravar movimento (qualquer origem) | `financeiro.servicos.registrar_movimento(DadosMovimento(...))` |
| Conta manual | `financeiro.manual.registrar_conta_manual(ContaManual(...))` |
| Listar/consultar contas | `financeiro.manual.listar_movimentos(...)`, `consultar_movimento(id)` |
| Consultar existência | `cadastros.consultas.consultar_pessoa(documento, papel, nome)`, `consultar_classificacao(codigo, tipo)` |
| Cadastros incompletos | `cadastros.pendentes.listar_incompletos`, `regularizar_cadastro_pendente`, `salvar_cadastro_pendente` (**não idempotente**) |

Erros de serviço são `ValidationError` com **`code` estável** (ler sempre `erro.error_list`); uso indevido (erro de programação) é `TypeError`/`ValueError`.
