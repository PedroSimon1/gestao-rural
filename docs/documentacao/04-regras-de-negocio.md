# 04 — Regras de negócio

Duas camadas de regras:

1. **Regras oficiais do professor** (RN-01 a RN-07), que são requisito.
2. **Regras técnicas derivadas**, decididas pela equipe (identificadas por `DQ-xx`, `D-xx`, `T-xx`, `Q-xx`) ou
   impostas pelo próprio código. Cada uma indica **onde é aplicada**: ao mudar a regra, mude também esse ponto e os testes.

Princípio geral: **toda regra é revalidada no servidor, no momento de gravar**, sem confiar no que a tela
validou nem no que veio dos Agents. Quando possível, o banco também a garante.

## 1. Regras oficiais (professor)

| ID | Regra | Como o sistema atende | Onde |
| --- | --- | --- | --- |
| RN-01 | Cadastros **não podem ser excluídos** | `delete()` levanta `ExclusaoNaoPermitida` (modelo e queryset); FKs `PROTECT`; não há rota de exclusão | `cadastros/models.py` (`SemExclusaoQuerySet`, `ComStatus.delete`); `financeiro/models.py` (`RegistroFinanceiro`) |
| RN-02 | Cadastros devem ser **INATIVADOS** | "Excluir" = `status = INATIVO`, por ação confirmada | `ComStatus.inativar`, telas `pessoa_status`, `classificacao_status` |
| RN-03 | Deve ser possível **REATIVAR** | Ação `reativar`, também confirmada; pessoa e cada papel têm status **independentes** | idem |
| RN-04 | Conta a pagar pode ter **uma ou mais** classificações de **DESPESA** | `MovimentoClassificacao` N:1; exatamente **uma principal** | `financeiro/servicos.py` |
| RN-05 | Conta a receber pode ter **uma ou mais** classificações de **RECEITA** | idem | idem |
| RN-06 | Conta pode ter **uma ou mais parcelas** com vencimentos próprios | `ParcelaConta`, 1 a 120 por movimento | `financeiro/servicos.py` |
| RN-07 | No cadastro novo o `STATUS` é ATIVO e oculto; "TODOS" lista só ATIVO | Cadastros novos nascem ATIVO; "TODOS" filtra ATIVO; em Contas, "TODOS" usa `CONFIRMADO` (estado financeiro, outro domínio) | `cadastros/views*.py`, `financeiro/views_consultas.py` |

Observação: `RN-02/03` são **parciais** apenas para a manutenção financeira (movimento e parcelas não têm
cancelamento nem reativação implementados).

## 2. Pessoas e papéis

| Regra | Origem | Onde |
| --- | --- | --- |
| A pessoa é identificada **só pelo CPF/CNPJ normalizado**; nunca pelo nome ou razão social | DQ-08 / Q-03 | `cadastros/consultas.py`, `resolucao.py`; `Pessoa.documento` único |
| Normalização: remove `.`, `-`, `/` e espaços; letras em maiúsculas | — | `cadastros/validators.py::normalizar_documento` |
| CPF: 11 dígitos com DV válido. CNPJ: 14 caracteres, **numérico ou alfanumérico** (IN RFB 2.229/2024), com DV válido | — | `validators.py`, `agents/extrator/schemas.py` |
| **Qualquer papel aceita CPF ou CNPJ**; o tipo do documento não é deduzido pelo papel | D-03, DQ-12 | `Pessoa`, `resolucao.py` |
| Papéis: `FORNECEDOR`, `CLIENTE`, `FATURADO`; a mesma pessoa pode ter vários; um registro por (pessoa, papel) | DQ-06 | `PapelPessoa` (unique) |
| O rótulo "CLIENTE-FORNECEDOR" é só de interface; não existe quarto papel | DQ-06 | — |
| Pessoa **COMPLETA** exige documento válido; **INCOMPLETA** não tem documento (nenhum documento fictício ou inválido é guardado) | DQ-05 | `Pessoa` (constraint `pessoa_documento_coerente_com_situacao`) |
| Cadastro incompleto **não pode ser usado em lançamento** até ser **regularizado** (mesmo registro, vínculos preservados) | DQ-05, DQ-13 | `Pessoa.regularizar`, `registrar_movimento` (`pessoa_incompleta`) |
| Pessoa ou papel **INATIVO** encontrado é identificado como INATIVO e **nunca é reativado automaticamente**; exige decisão explícita | DQ-07 / T-05 | `resolucao.py`, `Pessoa.atribuir_papel` (não muda status) |
| "Vigente" = papel ATIVO de pessoa ATIVA | — | `PapelPessoaQuerySet.vigentes` |
| `razao_social` não pode ser vazia; é normalizada (espaços colapsados) | — | `Pessoa` (constraint e `_normalizar`) |
| CPF aparece mascarado (`*******` + 4 últimos) em `__str__`, logs e erros | privacidade | `Pessoa.__str__` |
| Pessoas e papéis nunca somem: pessoa com papéis é protegida (`PROTECT`) | RN-01 | `PapelPessoa.pessoa` |

### 2.1 Resolução das pessoas da nota (F-4)

`cadastros/resolucao.py`. As decisões do usuário são **autorizações, não ordens**: uma decisão desnecessária é ignorada.

| Situação da parte da nota | O que acontece | Decisão necessária |
| --- | --- | --- |
| Pessoa ATIVA com papel ATIVO | Reutiliza o mesmo ID; **nenhuma escrita**; nome diferente na nota não altera o cadastro | — |
| Documento válido sem pessoa | Cria pessoa **COMPLETA** com o papel | `CRIAR_PESSOA` (+ nome) |
| Pessoa existe sem o papel | Atribui o papel no mesmo registro | `ATRIBUIR_PAPEL` (`CRIAR_PESSOA` **não** autoriza isso) |
| Pessoa INATIVA | Reativa a pessoa | `REATIVAR_PESSOA` |
| Papel INATIVO | Reativa o papel | `REATIVAR_PAPEL` |
| Documento ausente ou inválido | **Bloqueio**; nada é gravado, mesmo com todas as decisões | — (corrigir na conferência) |
| Cadastro incompleto selecionado | Regulariza no mesmo registro com o documento da nota | `REGULARIZAR` (+ papel/status se faltarem) |
| Mesmo documento nas duas partes | Uma só pessoa, um papel por parte, sem duplicar | Decisões em **cada** parte; nomes iguais, senão `nomes_divergentes` |

Bloqueios (nenhuma decisão resolve): `documento_ausente`, `documento_invalido`, `nome_ausente`, `nome_invalido`,
`nomes_divergentes`, `documento_em_uso`, `selecao_invalida`. Corrida persistente: `cadastro_concorrente`.

Todas as decisões são conferidas **antes** de gravar; qualquer falha desfaz tudo da chamada (savepoint), sem invalidar a transação externa.
Pessoas e papéis lidos são bloqueados com `FOR NO KEY UPDATE`, em ordem de `pk`.

## 3. Classificações

| Regra | Origem | Onde |
| --- | --- | --- |
| Identidade = (`tipo`, `codigo`); **imutável** depois de criada; só `descricao` e `status` mudam | GR-36/47 | `Classificacao._validar_identidade` |
| `codigo`: maiúsculas, números e `_` (ex.: `MANUTENCAO_E_OPERACAO`) | — | constraint `classificacao_codigo_valido` |
| Tipos: `DESPESA` e `RECEITA` | — | `TipoClassificacao` |
| Busca por código em **qualquer status**: INATIVA é identificada, não recriada | T-05 | `ClassificacaoQuerySet.por_codigo` |
| Carga inicial: `MANUTENCAO_E_OPERACAO`, `INFRAESTRUTURA_E_UTILIDADES` (DESPESA); **nenhuma RECEITA** | Q-05 | migration `cadastros/0003` |
| O código válido **não se limita** ao Enum do Agent: o usuário pode criar outra classificação de despesa na conferência | FLU-07 (PR #56) | `ClassificacaoNaNotaForm` |
| Classificação inativa ou de tipo errado **bloqueia** o lançamento (nada é reativado) | — | `registrar_movimento` (`classificacao_inativa`, `classificacao_incompativel`) |

## 4. Movimentos e parcelas

`financeiro/servicos.py::registrar_movimento` (única porta de gravação de movimentos).

| Regra | Código de erro (`ValidationError.code`) |
| --- | --- |
| Tipo ∈ {`APAGAR`, `ARECEBER`}; origem ∈ {`NOTA_FISCAL`, `MANUAL`} | `tipo`, `origem` |
| `valor_total`: `Decimal` finito, **> 0**, **< R$ 10 bilhões**, no máximo **2 casas** | `valor_tipo`, `valor`, `valor_centavos` |
| **APAGAR** exige contraparte com papel **FORNECEDOR** vigente e **faturado** com papel **FATURADO** vigente | `faturado`, `pessoa_*`, `papel_*` |
| **ARECEBER** exige contraparte com papel **CLIENTE** vigente; faturado opcional (se informado, vigente) | idem |
| Pessoa incompleta, inativa ou sem papel vigente é recusada; **nada é criado nem reativado** aqui | `pessoa_incompleta`, `pessoa_inativa`, `papel_ausente`, `papel_inativo`, `pessoa_inexistente` |
| APAGAR usa classificações `DESPESA`; ARECEBER, `RECEITA` | `classificacao_incompativel` |
| **Pelo menos uma** classificação, sem repetição, **exatamente uma principal** (booleano de verdade) | `sem_classificacao`, `classificacao_repetida`, `principal`, `principal_tipo` |
| **Pelo menos uma parcela**, no máximo **120**; numeradas **1..n sem lacunas**; vencimento é `date` | `sem_parcela`, `parcela_quantidade`, `parcela_numero`, `parcela_numeracao`, `parcela_repetida`, `parcela_vencimento` |
| Valor de cada parcela com as mesmas regras do total | `parcela_valor*` |
| **Soma das parcelas = `valor_total`** exatamente | `parcela_soma` |
| O banco confere a soma de novo **no COMMIT** (gatilho diferido) | `movimento_soma_das_parcelas` |
| Movimento `CONFIRMADO` tem ao menos uma parcela ATIVA | `movimento_com_parcela_ativa` |

Imutabilidade: `tipo`, `origem`, `status`, `contraparte`, `faturado`, `valor_total`, `analise_origem_id`,
`chave_idempotencia` e `criado_em` do movimento não mudam depois de gravados; em parcelas, `identificador`,
`movimento`, `numero`, `data_vencimento`, `valor`, `status` e `criado_em`. O cancelamento será uma operação
própria (**não implementada**). `update()`, `bulk_update()` e `bulk_create(update_conflicts)` também recusam.

Um movimento **nasce `CONFIRMADO`**: não existe rascunho.

**Baixa de parcela** (D1, 27/11/2026): cada parcela ATIVA de movimento CONFIRMADO pode ser marcada como paga (a pagar) ou recebida (a receber) com uma
data que não seja futura, e a baixa pode ser desfeita. Não há pagamento parcial, estorno com histórico nem cancelamento (sem contrato aprovado).
Duas baixas simultâneas da mesma parcela: só uma passa (a linha é bloqueada).

**Aviso de conta parecida** (2C): antes de registrar uma conta manual, e na confirmação de uma nota, o sistema lista as contas CONFIRMADAS com a mesma
contraparte, o mesmo valor total e o mesmo primeiro vencimento. Na conta manual o registro só segue com a ciência do usuário; na nota é só aviso (a
identidade fiscal é a trava de verdade).

**Validade da análise** (D2): 30 minutos desde a criação; cada salvamento das correções renova por mais 30 minutos, com teto de 3 horas desde a criação.

### 4.1 Idempotência

| Origem | Chave | Comportamento |
| --- | --- | --- |
| Nota fiscal | `analise_origem_id` (UUID da análise), único | Repetir com os mesmos dados devolve o movimento existente (`criado=False`); com dados diferentes, recusa `analise_ja_lancada` |
| Manual | `chave_idempotencia` (UUID gerado ao abrir o formulário), único, **só para origem MANUAL** | Mesma chave e mesmos dados devolve o existente; outros dados, `solicitacao_ja_registrada`; chaves diferentes gravam contas diferentes, mesmo com dados idênticos |

O índice único decide envios simultâneos. A chave nunca é usada junto de `analise_origem_id`.

## 5. Nota fiscal: identidade, duplicidade e conferência

### 5.1 Identidade fiscal (`financeiro/identidade_fiscal.py`, F-1)

| Regra | ID |
| --- | --- |
| A **chave de acesso válida** identifica a nota; sem ela, **CNPJ do emitente + modelo + série + número** | DQ-10 / D-01 |
| Chave: 44 posições; as 12 primeiras do CNPJ aceitam letras; **DV módulo 11** (valor do caractere = ASCII − 48, pesos 2 a 9) | NT Conjunta 2025.001 |
| Chave **inválida** (formato ou DV) **bloqueia**, mesmo com os demais campos | DQ-16 / T-04 |
| Chave válida **divergente** dos campos informados bloqueia | DQ-16 |
| Só **NF-e (55)** e **NFC-e (65)** com **emitente CNPJ**; NFS-e, outros modelos e emitente CPF ficam bloqueados | DQ-17 / T-06 |
| Dados insuficientes bloqueiam (`identidade_fiscal_insuficiente`) | DQ-10 |
| A identidade é **única no banco**, inclusive em transações concorrentes; um movimento **cancelado não libera** a identidade | DQ-15, DQ-18 |
| Os quatro campos (CNPJ, modelo, série, número) têm de bater com os da chave (constraint) | `nota_fiscal_chave_coerente` |
| Sem modelo e sem chave (como no JSON v1), a conferência sempre acusa `identidade_fiscal_insuficiente` | — |

### 5.2 Conferência (`documentos/conferencia.py`, F-3)

`conferir_nota(dados, correcoes)` monta a nota que seria lançada: para cada campo da lista fechada vale a **correção**, se houver,
senão o **valor extraído**. Tudo é revalidado com as mesmas regras, **só leitura**.

- **Campos corrigíveis** (lista fechada, D-02/D-03/G-01): `fornecedor.documento`, `fornecedor.razao_social`, `faturado.documento`,
  `faturado.nome`, `tipo_despesa`, `numero_nota`, `serie`, `chave_acesso`, `modelo`, `data_emissao`, `valor_total`, `parcelas`.
  Campo fora da lista é recusado.
- **CPF e CNPJ extraídos para a mesma parte**: nenhum é escolhido automaticamente (`escolha_necessaria`); o usuário escolhe na conferência (D-03).
- O **nome** só é exigido quando a pessoa **ainda não existe**; a **data de emissão** não é gravada no movimento (o modelo não a tem).
- **Pessoa/classificação inativa e papel ausente não são "problema de dado"**: aparecem nas consultas e pedem decisão explícita.
- **Classificação inexistente** é um problema (`classificacao_inexistente`) até o usuário escolher uma cadastrada ou criar.
- Os problemas voltam como **código + campo**, nunca com valores ou documentos.
- Valores corrigidos: `[0-9]{1,10}(\.[0-9]{1,2})?` com ponto decimal e sem separador de milhar (`"1.250"` seria R$ 1,25). Datas `AAAA-MM-DD`. Caracteres de controle e *surrogates* são recusados.
- O JSON original (`dados`) **nunca muda**; as correções ficam em campo próprio, que cada gravação substitui por inteiro, com **controle otimista por versão** (`versao_correcoes`).

### 5.3 Análise pendente (`documentos/analises.py`)

| Regra | ID |
| --- | --- |
| Validade de **30 minutos**, **sem renovação** ao salvar correções | DQ-09, T-05 |
| A análise pertence à **sessão**: o cookie guarda um código aleatório, o banco guarda o **hash SHA-256**. Outra sessão recebe "análise não encontrada" (sem revelar existência) | DQ-09 |
| Estados: `PENDENTE`, `CONFIRMADA`, `CANCELADA`, `EXPIRADA`; os três últimos são finais | — |
| Ao confirmar, cancelar ou expirar: `dados` e `correcoes` são apagados; ficam só o estado, as datas e os **nomes** dos campos corrigidos (sem valores) | DQ-20 |
| Expirar bloqueia o uso, mas os dados só são apagados quando a análise é acessada, quando qualquer análise é criada, no login/logout ou pelo comando `expirar_analises` | — |
| Login troca o código e **cancela as pendentes do anterior**; logout cancela as pendentes da sessão antes do `flush` | GR-43 |
| Nenhuma linha de análise é excluída fisicamente | — |
| O UUID da análise é o `analise_origem_id` do movimento (idempotência) | DQ-09 |
| Formato de `dados`: v1 (10 chaves) ou v2 (11 chaves, com `documento_fiscal`), reconhecido pelo conjunto **exato** de chaves; nada é convertido; outro conjunto é recusado | P-09 |
| Confirmar exige a `versao_correcoes` que o usuário viu; se outra aba mudou, recusa (`correcoes_desatualizadas`) | DQ-19, DQ-21 |

### 5.4 Confirmação transacional (`financeiro/lancamento_nota.py`, F-5)

Dentro de **uma** transação (`transaction.atomic(durable=True)`, em `confirmar_analise`), nesta ordem:

1. `conferir_nota` — qualquer problema recusa (`conferencia_pendente`);
2. `resolver_partes` (F-4) — pessoas e papéis conforme as decisões;
3. `registrar_movimento` — `APAGAR`, origem `NOTA_FISCAL`, **uma** classificação (a da nota) como principal, parcelas da nota, `analise_origem_id`;
4. `registrar_identidade_fiscal` — `NotaFiscalLancada` 1:1 com o movimento.

Qualquer exceção desfaz **tudo** (cadastros, papéis, movimento, parcelas, identidade) e a análise **continua PENDENTE**.
O resultado só é devolvido depois do COMMIT. `lancar_nota` **não pode** ser chamada dentro de outra transação (`RuntimeError`).

## 6. Contas manuais (`financeiro/manual.py`)

- Origem sempre `MANUAL`; `analise_origem_id` nulo; delega a `registrar_movimento`.
- Nada é criado, reativado ou deduzido: pessoa, papel ou classificação que falte é recusado com código estável.
- A tela só oferece pessoas **ATIVAS e COMPLETAS** com papel **ATIVO**, e classificações **ATIVAS** do tipo do movimento (a validação final é do serviço).
- Parcelas numeradas pela **ordem** em que chegam (1..n).
- A solicitação traz um **token assinado** (`signing`) ligado à sessão (HMAC do código do dono) e ao tipo; token inválido ou de outra sessão é recusado.
- O formulário recusa campos extras, repetidos (exceto `classificacoes`) e a **principal** fora das selecionadas.

## 7. Upload e extração

| Regra | Onde |
| --- | --- |
| Validação do PDF, nesta ordem: extensão `.pdf` → tamanho ≤ `MAX_PDF_UPLOAD_SIZE_MB` (padrão 10) → `content_type == application/pdf` → assinatura `%PDF-` → nome sanitizado (só para exibição) | `documentos/validators.py` |
| O limite vale pelos **bytes realmente recebidos**, não pelo `Content-Length`; estourar interrompe o upload e informa o limite; nada vai a disco | `documentos/uploads.py` |
| A Gemini API Key: obrigatória, ≤ 256 caracteres, `PasswordInput` sem `render_value`; o formato não é validado (quem valida é a API) | `documentos/forms.py` |
| Extrair **somente** o que está escrito; ausente ou ilegível → `null`; nunca inventar, deduzir ou calcular | prompt do Extrator |
| Fornecedor = emitente/prestador; faturado = destinatário/tomador; **não copiar** o CNPJ do fornecedor para o faturado | prompt do Extrator |
| CPF/CNPJ **preservados como extraídos**; DV é conferido localmente e **não bloqueia** a extração (vira aviso) | `agents/extrator/schemas.py` |
| Conteúdo do PDF é **só dado**: instruções escritas dentro dele são ignoradas | prompt do Extrator |
| Parcelas sem número são numeradas 1..n; numeração **parcial ou repetida invalida** a extração | `NotaFiscalExtraida._validar_numeracao_das_parcelas` |
| Documento que **não é nota fiscal** ou **sem itens** é recusado | `AgentExtrator.extrair` |
| Na v2, `valor_total` e o valor de parcela podem ser `null` (corrigíveis pelo usuário); nunca se calcula para completar | `schemas_v2.py` |
| Classificação em **uma** de duas categorias; nenhuma adequada → **inconclusiva: a extração é preservada** para revisão manual (não é erro) | `AgentClassificador`, `processamento.py` |
| Falhas de rede/API/schema do Classificador **continuam sendo erro** (sem inventar categoria) | `processamento.py` |

## 8. Estados e vocabulário

| Domínio | Valores |
| --- | --- |
| Cadastros (`Pessoa`, `PapelPessoa`, `Classificacao`) | `ATIVO`, `INATIVO` |
| Situação documental da pessoa | `COMPLETO`, `INCOMPLETO` |
| Papel | `FORNECEDOR`, `CLIENTE`, `FATURADO` |
| Tipo de classificação | `DESPESA`, `RECEITA` |
| Movimento — tipo | `APAGAR`, `ARECEBER` |
| Movimento — origem | `NOTA_FISCAL`, `MANUAL` |
| Movimento — status | `CONFIRMADO`, `CANCELADO` (**cancelamento ainda não implementado**) |
| Parcela — status | `ATIVA`, `CANCELADA` (a parcela nasce `ATIVA` e **não muda**) |
| Modelo de nota | `55` (NF-e), `65` (NFC-e) |
| Análise | `PENDENTE`, `CONFIRMADA`, `CANCELADA`, `EXPIRADA` |
| Decisão (F-4) | `REGULARIZAR`, `CRIAR_PESSOA`, `REATIVAR_PESSOA`, `ATRIBUIR_PAPEL`, `REATIVAR_PAPEL` |
| Situação de consulta | `EXISTE`, `NAO_EXISTE`, `DOCUMENTO_AUSENTE`, `DOCUMENTO_INVALIDO`, `CLASSIFICACAO_AUSENTE` |

> **Atenção:** `CONFIRMADO` (movimento) é um estado **financeiro**, diferente de `ATIVO` (cadastro) e de "quitado". "Quitado" é derivado: todas as
> parcelas ATIVAS com `pago_em` preenchido. Não os confunda ao implementar filtros, "TODOS" ou baixa de parcelas.
