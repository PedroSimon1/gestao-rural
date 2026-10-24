# Matriz de Requisitos — N2 Etapa 2

> Matriz rastreável do que foi pedido para a **N2 Etapa 2** do Gestão Rural, com a situação de cada item no código auditado.
>
> **Responsáveis:** todos estão como `A DEFINIR`. A divisão entre Pedro Simon e Gustavo Lopes é feita na fase seguinte (ver seção 9).

---

## 1. Identificação

| Item                    | Valor                                                                      |
| ----------------------- | -------------------------------------------------------------------------- |
| Projeto                 | Gestão Rural (Projeto Administrativo-Financeiro) — ESW424, UniRV           |
| Entrega                 | **27/10/2026, 23h59** (Classroom: 45 pontos; documento do professor: peso 45%) |
| Data da consolidação    | 24/10/2026                                                                 |
| Referência de código    | `f7786e8`, tag `n2-etapa1-final` (= `main` = `qa` na auditoria; hoje `main` = `develop`), auditado em 24/10/2026 |
| Estado da matriz        | versão inicial para revisão; a organização das tarefas no Jira será feita **depois da consolidação documental** |

## 2. Fontes

| Código   | Fonte                                                         | Localização (relativa à raiz do repositório)                                                   | Autoridade |
| -------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------- |
| **PROF** | `PROJETO ADMINISTRATIVO - N2 - Etapa 2.docx`                  | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/`                                       | oficial (professor) |
| **CLASS** | `Instruções Parte 2.pdf` (captura da postagem do Classroom)  | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/`                                       | oficial (Classroom) |
| **AULA** | `03 - Aula - Pratica de Engenharia (Agents).pptx`             | `../Documentos/Att-01--21-09-Agent IA/Material/`                                               | oficial (material didático; fluxo de Agents e Etapa 1) |
| **CTX**  | `ContextoProjeto.md` (auditoria de 24/10/2026)                | [`../../ContextoProjeto.md`](../../ContextoProjeto.md)                                         | estado técnico verificado |
| **ADR1** | ADR-001 Supabase                                              | [`../arquitetura/ADR-001-supabase.md`](../arquitetura/ADR-001-supabase.md)                     | decisão da equipe |

As seções do documento PROF são citadas pelo título original: "Funcionalidades que serão implementadas", "Regras de negócios", "ATIVIDADE 2° Etapa", "Note que as seguintes entidades serão afetadas", "ENTREGA" e "RECOMENDAÇÃO DE LAYOUT".

## 3. Convenções

**Natureza do requisito:**

| Natureza                   | Critério                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------- |
| **OBRIGATÓRIO**            | redação imperativa na fonte oficial ("deve", "não podem", "devem")                          |
| **FUNCIONALIDADE LISTADA** | consta em "Funcionalidades que serão implementadas"; a extensão exigida nesta entrega precisa ser confirmada (ver Q-01) |
| **RECOMENDAÇÃO**           | apresentada pela fonte como recomendação (layout)                                           |
| **PLANEJAMENTO TÉCNICO**   | decisão ou necessidade técnica da equipe; não é exigência do professor                      |

**Situação no código `f7786e8`:**

| Situação                    | Significado                                                             |
| --------------------------- | ----------------------------------------------------------------------- |
| **IMPLEMENTADO**            | existe no código auditado                                               |
| **PARCIAL**                 | parte da base existe (normalmente da Etapa 1), mas não atende ao requisito |
| **NÃO IMPLEMENTADO**        | nenhuma evidência no código                                             |
| **PENDENTE DE CONFIRMAÇÃO** | depende de uma decisão ou de uma verificação externa                    |

## 4. Pré-requisito herdado da Etapa 1

A Etapa 2 começa "após a extração dos dados" da Etapa 1 (PROF, "ATIVIDADE 2° Etapa").

| ID     | Requisito                                                                   | Fonte        | Natureza    | Critério de aceite                                                     | Situação         | Evidência                                                     | Responsável |
| ------ | --------------------------------------------------------------------------- | ------------ | ----------- | ---------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------- | ----------- |
| BASE-01 | Extrair os dados da nota fiscal PDF e classificar a despesa com Agents (JSON) | AULA (slides 18–21); PROF | OBRIGATÓRIO | PDF → Extrator → Classificador → JSON com fornecedor, faturado, parcelas e tipo de despesa | **IMPLEMENTADO** (291 testes OK em 24/10/2026; Gemini real não chamado na auditoria) | `documentos/processamento.py`, `agents/extrator/`, `agents/classificador/` | A DEFINIR |

## 5. Matriz

### 5.A — Funcionalidades (PROF, "Funcionalidades que serão implementadas")

O documento agrupa as funcionalidades em **MANTER PESSOAS**, **MANTER CLASSIFICAÇÃO** e **REGISTRAR CONTAS**.

| ID     | Requisito                     | Fonte | Natureza               | Critério de aceite                                                                        | Situação         | Evidência                       | Responsável |
| ------ | ----------------------------- | ----- | ---------------------- | ----------------------------------------------------------------------------------------- | ---------------- | ------------------------------- | ----------- |
| FUN-01 | Manter Fornecedor             | PROF  | FUNCIONALIDADE LISTADA | incluir, consultar, editar, inativar e reativar fornecedor (`PESSOAS`), sem exclusão física | NÃO IMPLEMENTADO | sem models nem telas (CTX 8.1)  | A DEFINIR |
| FUN-02 | Manter Cliente                | PROF  | FUNCIONALIDADE LISTADA | idem para cliente (`PESSOAS`)                                                             | NÃO IMPLEMENTADO | idem                            | A DEFINIR |
| FUN-03 | Manter Faturado               | PROF  | FUNCIONALIDADE LISTADA | idem para faturado (`PESSOAS`)                                                            | NÃO IMPLEMENTADO | idem                            | A DEFINIR |
| FUN-04 | Manter Tipo de Receita        | PROF  | FUNCIONALIDADE LISTADA | idem para classificação do tipo RECEITA (`CLASSIFICACAO`)                                 | NÃO IMPLEMENTADO | idem                            | A DEFINIR |
| FUN-05 | Manter Tipo de Despesa        | PROF  | FUNCIONALIDADE LISTADA | idem para classificação do tipo DESPESA (`CLASSIFICACAO`)                                 | NÃO IMPLEMENTADO | o Enum `TipoDespesa` existe só no Agent; não há cadastro | A DEFINIR |
| FUN-06 | Registrar Contas a Pagar      | PROF  | FUNCIONALIDADE LISTADA | registrar movimento APAGAR com uma ou mais classificações e parcelas (`MOVIMENTOCONTAS`, `PARCELACONTAS`) | NÃO IMPLEMENTADO | sem persistência (CTX 15.1) | A DEFINIR |
| FUN-07 | Registrar Contas a Receber    | PROF  | FUNCIONALIDADE LISTADA | registrar movimento a receber com uma ou mais classificações de RECEITA e parcelas        | NÃO IMPLEMENTADO | os Agents só tratam despesa     | A DEFINIR |

### 5.B — Fluxo de processamento (PROF, "ATIVIDADE 2° Etapa")

| ID     | Requisito                                                         | Fonte | Natureza    | Critério de aceite                                                                                         | Situação         | Evidência                                         | Responsável |
| ------ | ----------------------------------------------------------------- | ----- | ----------- | ---------------------------------------------------------------------------------------------------------- | ---------------- | ------------------------------------------------- | ----------- |
| FLU-01 | Consultar no banco se o **FORNECEDOR** existe                     | PROF  | OBRIGATÓRIO | após a extração, buscar o fornecedor da nota em `PESSOAS` e obter "existe (com ID)" ou "não existe"         | NÃO IMPLEMENTADO | `DATABASES = {}`                                  | A DEFINIR |
| FLU-02 | Consultar no banco se o **FATURADO** existe                       | PROF  | OBRIGATÓRIO | idem para o faturado                                                                                       | NÃO IMPLEMENTADO | idem                                              | A DEFINIR |
| FLU-03 | Consultar no banco se a classificação da **DESPESA** existe       | PROF  | OBRIGATÓRIO | buscar a classificação atribuída pelo Classificador em `CLASSIFICACAO` (tipo DESPESA)                      | NÃO IMPLEMENTADO | idem; mapeamento Enum → descrição indefinido (Q-05) | A DEFINIR |
| FLU-04 | Mostrar na tela o resultado das consultas                         | PROF  | OBRIGATÓRIO | para cada item, mostrar nome/razão social, CNPJ ou CPF quando houver, e "NÃO EXISTE" ou "EXISTE – ID: n", como no exemplo do professor | NÃO IMPLEMENTADO | a tela atual mostra só resumo e JSON | A DEFINIR |
| FLU-05 | Criar o novo fornecedor (se for o caso)                           | PROF  | OBRIGATÓRIO | fornecedor inexistente é gravado em `PESSOAS` (tipo CLIENTE-FORNECEDOR); o existente não é duplicado        | NÃO IMPLEMENTADO | —                                                 | A DEFINIR |
| FLU-06 | Criar o novo faturado (se for o caso)                             | PROF  | OBRIGATÓRIO | faturado inexistente é gravado em `PESSOAS` (tipo FATURADO), sem duplicar                                   | NÃO IMPLEMENTADO | —                                                 | A DEFINIR |
| FLU-07 | Criar a nova despesa (se for o caso)                              | PROF  | OBRIGATÓRIO | classificação inexistente é gravada em `CLASSIFICACAO` (tipo DESPESA), sem duplicar                         | NÃO IMPLEMENTADO | —                                                 | A DEFINIR |
| FLU-08 | Criar um novo registro do movimento                               | PROF  | OBRIGATÓRIO | `MOVIMENTOCONTAS` tipo APAGAR, ligado ao fornecedor, ao faturado e à(s) classificação(ões)                  | NÃO IMPLEMENTADO | —                                                 | A DEFINIR |
| FLU-09 | Criar a(s) parcela(s) do movimento                                | PROF  | OBRIGATÓRIO | `PARCELACONTAS` ligado ao movimento; o exemplo do professor mostra uma parcela "ÚNICA"; RN-06 admite várias | PARCIAL         | o Extrator já entrega a lista `parcelas` com vencimento e valor; nada é gravado | A DEFINIR |
| FLU-10 | Informar ao usuário que o registro foi lançado com sucesso        | PROF  | OBRIGATÓRIO | mensagem de sucesso exibida depois da gravação completa                                                    | NÃO IMPLEMENTADO | —                                                 | A DEFINIR |

### 5.C — Regras de negócio (PROF, "Regras de negócios")

Os IDs RN-01 a RN-06 são os mesmos da seção 7.1 do `ContextoProjeto.md`.

| ID    | Requisito                                                                                         | Fonte | Natureza    | Critério de aceite                                                              | Situação         | Evidência                                                     | Responsável |
| ----- | ------------------------------------------------------------------------------------------------- | ----- | ----------- | ------------------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------- | ----------- |
| RN-01 | Cadastros **não podem ser excluídos**                                                             | PROF  | OBRIGATÓRIO | nenhuma operação da interface apaga fisicamente pessoas ou classificações         | NÃO IMPLEMENTADO | sem cadastros                                                 | A DEFINIR |
| RN-02 | Cadastros devem ser **INATIVADOS**                                                                | PROF  | OBRIGATÓRIO | "excluir" muda o status para INATIVO                                            | NÃO IMPLEMENTADO | —                                                             | A DEFINIR |
| RN-03 | Deve ser possível **REATIVAR** um registro INATIVO                                                | PROF  | OBRIGATÓRIO | existe uma ação ou caminho que volta o status para ATIVO                        | NÃO IMPLEMENTADO | a recomendação de layout não diz como listar inativos (Q-04) | A DEFINIR |
| RN-04 | Conta a pagar pode ser classificada em **uma ou mais** classificações de despesa                  | PROF  | OBRIGATÓRIO | o modelo permite N classificações por movimento                                | NÃO IMPLEMENTADO | `tipo_despesa` é escalar (CTX 27); AULA pede "estrutura para receber mais de uma" | A DEFINIR |
| RN-05 | Conta a receber pode ser classificada em **uma ou mais** classificações de receita                | PROF  | OBRIGATÓRIO | idem para RECEITA                                                               | NÃO IMPLEMENTADO | —                                                             | A DEFINIR |
| RN-06 | Conta a pagar ou a receber pode ter **uma ou mais PARCELAS** com **datas de vencimento distintas** | PROF  | OBRIGATÓRIO | o modelo permite N parcelas, cada uma com o seu vencimento preservado            | PARCIAL          | `NotaFiscalExtraida.parcelas` (lista) com `data_vencimento`  | A DEFINIR |

### 5.D — Entidades mencionadas (PROF, "Note que as seguintes entidades serão afetadas")

Só os atributos **citados pelo professor** estão listados. A modelagem completa (campos, chaves, cardinalidades) é da fase de implementação.

| ID     | Entidade          | Atributos citados (exemplo do professor)                                   | Fonte | Natureza    | Critério de aceite                                     | Situação         | Evidência | Responsável |
| ------ | ----------------- | -------------------------------------------------------------------------- | ----- | ----------- | ------------------------------------------------------ | ---------------- | --------- | ----------- |
| ENT-01 | `PESSOAS`         | `Tipo` (CLIENTE-FORNECEDOR / FATURADO), `RazaoSocial`                      | PROF  | OBRIGATÓRIO | tabela existe e guarda fornecedores e faturados       | NÃO IMPLEMENTADO | sem models | A DEFINIR |
| ENT-02 | `CLASSIFICACAO`   | `Tipo` (DESPESA), `Descricao` (ex.: MANUTENÇÃO E OPERAÇÃO)                 | PROF  | OBRIGATÓRIO | tabela existe e guarda tipos de despesa e de receita  | NÃO IMPLEMENTADO | sem models | A DEFINIR |
| ENT-03 | `MOVIMENTOCONTAS` | `Tipo` (APAGAR)                                                            | PROF  | OBRIGATÓRIO | tabela existe e guarda os movimentos a pagar/receber  | NÃO IMPLEMENTADO | sem models | A DEFINIR |
| ENT-04 | `PARCELACONTAS`   | `Identificacao` (ÚNICA)                                                    | PROF  | OBRIGATÓRIO | tabela existe e guarda as parcelas de cada movimento  | NÃO IMPLEMENTADO | sem models | A DEFINIR |

### 5.E — Recomendações de interface (PROF, "RECOMENDAÇÃO DE LAYOUT")

O documento traz duas capturas de tela de **outro projeto** como referência visual (menu lateral, busca, tabela e formulário). Elas não definem campos do Gestão Rural.

| ID    | Requisito                                                       | Fonte | Natureza     | Critério de aceite                                          | Situação         | Evidência | Responsável |
| ----- | --------------------------------------------------------------- | ----- | ------------ | ----------------------------------------------------------- | ---------------- | --------- | ----------- |
| UI-01 | A tabela de registros abre **vazia**                            | PROF  | RECOMENDAÇÃO | ao abrir o cadastro, nenhum registro é carregado            | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-02 | Carregar dados pela **Busca** ou pelo botão **TODOS**           | PROF  | RECOMENDAÇÃO | os dois caminhos preenchem a tabela                         | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-03 | **TODOS** carrega os registros com status ATIVO                 | PROF  | RECOMENDAÇÃO | inativos não aparecem em TODOS                              | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-04 | **Ordenação** por coluna na tabela                              | PROF  | RECOMENDAÇÃO | clicar no cabeçalho ordena pela coluna                      | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-05 | **Busca** por mais de um elemento                               | PROF  | RECOMENDAÇÃO | a busca combina mais de um campo ou termo                   | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-06 | Ações na tabela: **Editar** e **Excluir (lógico)**              | PROF  | RECOMENDAÇÃO | cada linha oferece as duas ações; "Excluir" não apaga        | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-07 | No CREATE, campo STATUS oculto = ATIVO                          | PROF  | RECOMENDAÇÃO | novo registro nasce ATIVO sem o usuário escolher            | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-08 | No UPDATE, campo STATUS oculto                                  | PROF  | RECOMENDAÇÃO | o formulário de edição não expõe o status                   | NÃO IMPLEMENTADO | —         | A DEFINIR |
| UI-09 | No DELETE, STATUS passa a INATIVO (**status dos registros**)    | PROF  | RECOMENDAÇÃO | excluir = inativar (ver RN-01/RN-02)                        | NÃO IMPLEMENTADO | —         | A DEFINIR |

### 5.F — Entrega (PROF, "ENTREGA"; CLASS)

| ID     | Requisito                                                                                         | Fonte        | Natureza    | Critério de aceite                                                                                     | Situação                    | Evidência                                                                           | Responsável |
| ------ | ------------------------------------------------------------------------------------------------- | ------------ | ----------- | ------------------------------------------------------------------------------------------------------ | --------------------------- | ----------------------------------------------------------------------------------- | ----------- |
| DEL-01 | **Hospedar** o sistema                                                                            | PROF, CLASS  | OBRIGATÓRIO | a versão da Etapa 2 está acessível pela URL pública, com o banco do ambiente de produção               | PARCIAL                     | a Etapa 1 está no Render (registro de 29/09/2026, **não reverificado**)              | A DEFINIR |
| DEL-02 | **Subir no GitHub**                                                                               | PROF         | OBRIGATÓRIO | o código da Etapa 2 integrado ao repositório                                                           | PARCIAL                     | o repositório existe (público); a Etapa 2 não tem commits                           | A DEFINIR |
| DEL-03 | Postar o link do GitHub e do site no **Classroom**                                                | PROF, CLASS  | OBRIGATÓRIO | os dois links publicados na atividade até 27/10/2026, 23h59                                            | NÃO IMPLEMENTADO            | ação de entrega                                                                     | A DEFINIR |
| DEL-04 | `Readme.txt` com link da hospedagem, login, senha e Key (LLM)                                     | CLASS        | OBRIGATÓRIO | arquivo entregue com os quatro itens, **por canal privado** (ver seção 7)                              | PENDENTE DE CONFIRMAÇÃO     | existe um `README.txt` local ignorado pelo Git (conteúdo não lido); canal de entrega indefinido (Q-07) | A DEFINIR |
| DEL-05 | O **código da última atualização no GitHub** deve aparecer na **tela principal**                  | CLASS        | OBRIGATÓRIO | a tela principal mostra o identificador do último commit publicado, igual ao do GitHub                 | NÃO IMPLEMENTADO            | nenhuma referência a commit ou versão na interface (CTX 8.1)                        | A DEFINIR |
| DEL-06 | Prazo                                                                                             | PROF, CLASS  | OBRIGATÓRIO | entrega até 27/10/2026, 23h59                                                                          | PENDENTE                    | —                                                                                   | A DEFINIR |

### 5.G — Planejamento técnico (equipe)

| ID    | Item                                                                  | Fonte        | Natureza             | Critério de aceite                                                        | Situação         | Evidência                                                  | Responsável |
| ----- | --------------------------------------------------------------------- | ------------ | -------------------- | ------------------------------------------------------------------------- | ---------------- | ---------------------------------------------------------- | ----------- |
| PT-01 | Supabase PostgreSQL como banco gerenciado                             | ADR1         | PLANEJAMENTO TÉCNICO | ADR-001, seção 14                                                         | NÃO IMPLEMENTADO | `DATABASES = {}`                                           | A DEFINIR |
| PT-02 | Django ORM e Migrations para persistência                             | ADR1, `tecnologias.pdf` | PLANEJAMENTO TÉCNICO | models e migrations aplicados no banco de cada ambiente     | NÃO IMPLEMENTADO | sem `migrations/`                                          | A DEFINIR |
| PT-03 | Psycopg 3 como driver (candidato)                                     | ADR1         | PLANEJAMENTO TÉCNICO | compatibilidade validada (Python 3.14, Django 6.1, Render)                | NÃO IMPLEMENTADO | ausente de `requirements.txt`                              | A DEFINIR |
| PT-04 | Substituir os testes que proíbem banco                                | CTX 21.3     | PLANEJAMENTO TÉCNICO | a suíte valida o novo contrato com banco                                  | NÃO IMPLEMENTADO | `config/test_sem_banco.py`, `config/test_producao.py`      | A DEFINIR |
| PT-05 | Bancos e credenciais independentes por ambiente (dev / QA / produção) | `tecnologias.pdf`, ADR1 | PLANEJAMENTO TÉCNICO | cada ambiente aponta para o seu banco; nenhum segredo no Git | NÃO IMPLEMENTADO | —                                                     | A DEFINIR |
| PT-06 | `migrate` no processo de publicação                                   | ADR1         | PLANEJAMENTO TÉCNICO | build ou pre-deploy aplica as migrations                                  | NÃO IMPLEMENTADO | `build.sh` sem `migrate`                                   | A DEFINIR |

## 6. Resumo quantitativo

| Grupo                     | Itens | OBRIGATÓRIO | FUNC. LISTADA | RECOMENDAÇÃO | PLAN. TÉCNICO |
| ------------------------- | ----: | ----------: | ------------: | -----------: | ------------: |
| BASE (Etapa 1)            | 1     | 1           | —             | —            | —             |
| FUN                       | 7     | —           | 7             | —            | —             |
| FLU                       | 10    | 10          | —             | —            | —             |
| RN                        | 6     | 6           | —             | —            | —             |
| ENT                       | 4     | 4           | —             | —            | —             |
| UI                        | 9     | —           | —             | 9            | —             |
| DEL                       | 6     | 6           | —             | —            | —             |
| PT                        | 6     | —           | —             | —            | 6             |
| **Total**                 | **49** | **27**     | **7**         | **9**        | **6**         |

Situação em `f7786e8`: 1 IMPLEMENTADO (BASE-01), 4 PARCIAL (FLU-09, RN-06, DEL-01, DEL-02), 2 PENDENTE (DEL-04, DEL-06) e 42 NÃO IMPLEMENTADO.

## 7. Restrições de segurança aplicadas à entrega

- O `Readme.txt` (DEL-04) contém login, senha e chave de LLM. O repositório `PedroSimon1/gestao-rural` é **público**, então esse arquivo **não pode ser versionado**. Hoje `README.txt` está no `.gitignore`.
- A instrução do Classroom diz "Subir. Readme.txt", sem dizer onde. A recomendação é anexar o arquivo **somente na atividade do Classroom** ou entregá-lo por outro canal privado aprovado pelo professor (Q-07).
- A chave Gemini continua sendo informada na tela a cada processamento e nunca é armazenada. A chave que vai no `Readme.txt` é a que o professor usará para testar; avaliar se deve ser uma chave dedicada e revogável (Q-08).

## 8. Dúvidas de escopo em aberto

| ID   | Dúvida                                                                                                        | Itens afetados          |
| ---- | ------------------------------------------------------------------------------------------------------------- | ----------------------- |
| Q-01 | As telas CRUD completas de **todas** as funcionalidades "Manter/Registrar" são obrigatórias nesta entrega, ou basta o fluxo de lançamento a partir da nota ("ATIVIDADE 2° Etapa")? | FUN-01..07, UI-01..09   |
| Q-02 | Depois de mostrar as consultas, a criação dos registros é automática ou pede confirmação do usuário? O texto diz "após mostrar a mensagem, o sistema deve-se: criar…" | FLU-04..10              |
| Q-03 | Como identificar uma pessoa existente: por CNPJ/CPF normalizado, por razão social ou pelos dois?                | FLU-01, FLU-02, FLU-05, FLU-06 |
| Q-04 | Como o usuário encontra e reativa um registro inativo, se TODOS mostra só ATIVO?                                | RN-03, UI-03            |
| Q-05 | Quais categorias valem e como o valor do Enum (`MANUTENCAO_E_OPERACAO`) corresponde à `Descricao` gravada? O cliente usa Insumos/Operacionais/Venda produção | FLU-03, FLU-07, FUN-05  |
| Q-06 | O Classificador deve passar a devolver mais de uma classificação por nota (RN-04)?                              | RN-04, FLU-07, FLU-08   |
| Q-07 | Por qual canal o `Readme.txt` será entregue sem ser publicado no GitHub?                                       | DEL-04                  |
| Q-08 | Qual chave de LLM será fornecida ao professor, e com que limites e revogação?                                   | DEL-04                  |
| Q-09 | O "código da última atualização no GitHub" é o hash do commit (curto ou completo), uma tag ou outro identificador? Como obtê-lo no Render? | DEL-05 |
| Q-10 | Contas a receber (FUN-07, RN-05) entram no fluxo automático nesta etapa? Os Agents atuais só tratam notas de despesa | FUN-07, RN-05        |
| Q-11 | `CLIENTE-FORNECEDOR` é um único valor de `Tipo` ou dois valores distintos?                                      | ENT-01, FUN-01, FUN-02  |

Quem decide: Q-01, Q-02, Q-07 e Q-09 dependem do professor ou de interpretação da equipe; as demais são decisões técnicas da equipe.

## 9. Preparação para a divisão de responsabilidades

A coluna **Responsável** fica como `A DEFINIR`. Na fase seguinte:

1. responder ou registrar uma decisão provisória para Q-01 e Q-02, que mudam o tamanho do escopo;
2. agrupar os IDs em pacotes de trabalho coerentes (por exemplo: infraestrutura de banco, modelo, fluxo, cadastros, entrega);
3. atribuir os pacotes e, depois da consolidação documental, registrá-los no Jira (projeto `GR`), citando os IDs desta matriz;
4. atualizar a coluna **Situação** só com evidência (commit, teste ou PR).
