# Documentação do Sistema — Gestão Rural

Documentação de referência do sistema **Gestão Rural**, escrita a partir do
código integrado em `develop` (`71297a0`, PR #59, 24/11/2026) e dos documentos
do projeto. Serve de base para entender o sistema antes de implementar uma
funcionalidade nova ou corrigir algo.

> **Como ler as afirmações.** Cada documento descreve o que **existe no código**.
> O que é decisão da equipe, requisito ainda não atendido ou risco conhecido
> aparece marcado como tal. *Implementado*, *integrado*, *validado localmente*,
> *homologado* e *publicado* são estados diferentes: esta documentação só afirma
> os dois primeiros e a validação local registrada nas auditorias.

## Índice

| # | Documento | Para que serve |
| --- | --- | --- |
| 01 | [Visão geral](01-visao-geral.md) | Problema, propósito, escopo, estado atual, tecnologias e glossário |
| 02 | [Arquitetura](02-arquitetura.md) | Camadas, apps, dependências entre módulos, estrutura de diretórios, ambientes |
| 03 | [Requisitos](03-requisitos.md) | Requisitos funcionais (RF) e não funcionais (RNF), com situação real e rastreio |
| 04 | [Regras de negócio](04-regras-de-negocio.md) | Regras oficiais (RN) e regras técnicas derivadas, com o ponto do código que as aplica |
| 05 | [Fluxos](05-fluxos.md) | Login, processamento da nota, conferência, confirmação, conta manual, cadastros, ciclo de vida da análise |
| 06 | [Modelo de dados](06-modelo-de-dados.md) | Tabelas, campos, constraints, gatilho no PostgreSQL, migrations |
| 07 | [Agents e contratos JSON](07-agents-e-contratos.md) | Gemini, Extrator, Classificador, JSON v1/v2, correções, códigos de erro |
| 08 | [Interface e rotas](08-interface-e-rotas.md) | URLs, telas, formulários, mensagens e comportamentos de tela |
| 09 | [Segurança e privacidade](09-seguranca-e-privacidade.md) | Controles existentes, dados pessoais, limites conhecidos |
| 10 | [Configuração e operação](10-configuracao-e-operacao.md) | Variáveis, ambientes, execução local, migrations, publicação, rotinas |
| 11 | [Testes](11-testes.md) | Estratégia, executor de testes, organização, como rodar |
| 12 | [Pendências e riscos](12-pendencias-e-riscos.md) | O que falta, decisões em aberto, achados da auditoria |
| 13 | [Guia para quem vai alterar o sistema](13-guia-do-desenvolvedor.md) | Onde mexer, invariantes que não podem quebrar, checklist por tipo de mudança |

Sugestão de leitura: **01 → 02 → 05** para uma visão rápida; **04 + 06** antes de
mexer em regra ou persistência; **13** antes de começar qualquer tarefa.

## Relação com os demais documentos

| Documento | Papel | Relação com esta pasta |
| --- | --- | --- |
| [`ContextoProjeto.md`](../../ContextoProjeto.md) | Histórico técnico detalhado, por tarefa (GR-xx) | Fonte das decisões e do histórico; tem seções antigas defasadas (ver [12](12-pendencias-e-riscos.md)) |
| [`docs/requisitos/matriz-n2-etapa2.md`](../requisitos/matriz-n2-etapa2.md) | Matriz de requisitos da N2 Etapa 2 (FUN, FLU, RN, ENT, UI, DEL, PT) | Rastreabilidade acadêmica; os requisitos daqui apontam para ela |
| [`docs/arquitetura/ADR-001-supabase.md`](../arquitetura/ADR-001-supabase.md) | Decisão do banco | Resumida em [02](02-arquitetura.md) |
| [`docs/contratos/`](../contratos/) | Contratos de integração e JSON fiscal v2 | Resumidos em [07](07-agents-e-contratos.md) |
| [`docs/operacao/GuiaOperacaoN2.md`](../operacao/GuiaOperacaoN2.md) | Roteiro de operação e entrega | Resumido em [10](10-configuracao-e-operacao.md) |
| [`docs/auditoria/`](../auditoria/) | Auditorias (GR-16 e 24/11/2026) | Achados consolidados em [12](12-pendencias-e-riscos.md) |
| [`README.md`](../../README.md) | Instruções públicas de instalação e execução | Complementar a [10](10-configuracao-e-operacao.md) |
| [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md) | Fluxo Git oficial | Referenciado em [13](13-guia-do-desenvolvedor.md) |

Em caso de divergência, **o código e os testes prevalecem**; depois, os
documentos mais recentes e as decisões registradas no `ContextoProjeto.md`.

## Convenções

- **Idioma:** português do Brasil, como o código, os comentários e as mensagens da interface.
- **Identificadores de rastreio:** `RF-xx`/`RNF-xx` (requisitos, seção 5 e 6 do `ContextoProjeto.md`),
  `RN-xx` (regras do professor), `FUN/FLU/UI/ENT/DEL/PT-xx` (matriz), `GR-xx` (tarefas do Jira),
  `F-1…F-6` (etapas da confirmação transacional, GR-22), `DQ-xx`, `D-xx`, `T-xx`, `Q-xx`
  (decisões e dúvidas da equipe).
- **Caminhos** são relativos à raiz do repositório.
- **Nenhum segredo** aparece aqui: só **nomes** de variáveis de ambiente.
  Nunca acrescente valores, chaves, senhas, strings de conexão ou dados reais de clientes.

## Manutenção desta documentação

- Atualize o documento correspondente quando mudar **comportamento, regra, modelo de dados,
  contrato, rota ou configuração**. Mudança só interna (refatoração sem efeito visível) não exige.
- Ao criar ou renomear um arquivo desta pasta, atualize o índice acima e o
  [`docs/INDICE.md`](../INDICE.md).
- Não apresente o planejado como implementado. Se a situação de algo mudar, registre também
  no `ContextoProjeto.md`.
- Edite pontualmente; não reescreva documentos inteiros nem duplique trechos grandes dos
  documentos de origem.
