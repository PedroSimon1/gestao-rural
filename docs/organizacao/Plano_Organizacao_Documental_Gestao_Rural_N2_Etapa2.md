# Plano de Organização Documental — Gestão Rural, N2 Etapa 2

| Item            | Valor                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------- |
| Data            | 24/10/2026                                                                                    |
| Fase            | **Fase 1 — Organização documental** (antes da divisão de responsabilidades e da implementação) |
| Escopo          | somente documentação Markdown; nenhuma alteração em código, dependências, configuração, banco, Jira ou deploy |
| Branch de trabalho | `feature/Auditoria-Correcao` (local, sem commit)                                           |

Legenda dos status deste plano: **FEITO** (executado e verificado nesta fase), **PENDENTE** (ainda não executado), **BLOQUEADO** (depende de acesso ou decisão externa).

---

## 1. Objetivo

Deixar a documentação da N2 Etapa 2 organizada, rastreável e confiável, para que a equipe (Pedro Simon e Gustavo Lopes) e os agentes de IA (Claude Code, ChatGPT Codex e outros):

- saibam o que existe no código e o que é só requisito ou plano;
- encontrem os requisitos oficiais e suas fontes;
- conheçam as decisões de arquitetura vigentes (Supabase) e as históricas (Neon);
- possam dividir as responsabilidades na fase seguinte sem retrabalho.

## 2. Contexto inicial

- **Código:** `f7786e8` (`main` = `qa` = remoto na auditoria; depois `qa` foi excluída e `develop` criada no mesmo commit), tag `n2-etapa1-final`. A Etapa 1 está completa, sem banco, com 291 testes OK na auditoria de 24/10/2026.
- **Etapa 2:** entrega em 27/10/2026, 23h59. Nenhuma implementação, branch ou PR existe.
- **Documentação de partida:**
  - `ContextoProjeto.md` reescrito na auditoria de 24/10/2026, sem commit;
  - documentos acadêmicos e de contexto fora do repositório, em `../Documentos/`;
  - três rascunhos externos na pasta-pai do repositório (índice, matriz e plano).
- **Decisão nova:** após a auditoria, a equipe escolheu o Supabase PostgreSQL no lugar do Neon (ver [ADR-001](../arquitetura/ADR-001-supabase.md)).

## 3. Inventário de documentos

O inventário completo, com localização, categoria, autoridade e disponibilidade, está em [`docs/INDICE.md`](../INDICE.md), seção 9. Resumo por categoria:

| Categoria             | Documentos                                                                                         |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| Oficial               | documento da Etapa 2 (docx), Instruções Parte 2 (Classroom), aula de Agents (pptx), requisitos do cliente |
| Técnica atual         | `ContextoProjeto.md`, matriz da Etapa 2, código e testes em `f7786e8`                              |
| Planejamento          | ADR-001 (Supabase); itens de `tecnologias.pdf` que continuam válidos                               |
| Processo              | `ContextoTasksJira.md` (23/09/2026), GitHub, este plano, o guia de integração                      |
| Histórica             | Mini Documentação, V0.91, contextos de 22/09, guias e relatórios da Etapa 1, Neon em `tecnologias.pdf`, `analisetemporaria.md` |
| Restrita              | `.env`, `README.txt` de entrega, credenciais de banco, chaves de IA                                |

## 4. Estrutura documental

```text
gestao-rural/
├── ContextoProjeto.md                      # fonte central de verdade (estado real)
├── ContextoFluxoGit.md                     # fluxo Git oficial (develop → main)
└── docs/
    ├── INDICE.md                           # onde está cada documento e qual a sua autoridade
    ├── requisitos/
    │   └── matriz-n2-etapa2.md             # o que o professor pediu, com a situação de cada item
    ├── arquitetura/
    │   └── ADR-001-supabase.md             # decisões de arquitetura numeradas (ADR-NNN-assunto.md)
    └── organizacao/
        ├── Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md   # este plano
        └── LEIA-ME-integracao.md           # como usar e integrar a documentação
```

Os documentos acadêmicos continuam fora do repositório, em `../Documentos/`, sem alteração. Esta estrutura é só da documentação e não mexe na organização do código Django.

## 5. Hierarquia das fontes

| Assunto                 | Fonte principal                                     | Em caso de conflito                                            |
| ----------------------- | --------------------------------------------------- | -------------------------------------------------------------- |
| Requisitos acadêmicos   | documento do professor e Classroom                  | prevalece o documento oficial mais recente                     |
| Requisitos do cliente   | Documento de Requisitos do Cliente                  | registrar a divergência com o professor; não decidir sozinho   |
| Implementação existente | código verificado e testes                          | o código prevalece sobre qualquer texto                        |
| Arquitetura atual       | código e ADRs aceitos                               | ADR mais recente prevalece sobre planos antigos                |
| Decisões futuras        | ADRs                                                | decisão sem ADR = proposta                                     |
| Estado de tarefas       | Jira atual                                          | `ContextoTasksJira.md` é só retrato histórico                  |
| Fluxo de desenvolvimento | [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md) (v1.0, 24/10/2026) | prevalece sobre resumos (como o [guia de integração](LEIA-ME-integracao.md)) e sobre o fluxo antigo com `qa` (HISTÓRICO) |
| Histórico               | documentos e commits anteriores                     | nunca sobrescreve o estado atual                               |

## 6. Critérios para manutenção

1. **`ContextoProjeto.md`** é atualizado quando uma mudança é **integrada** (merge em `develop`/`main`) ou quando uma decisão de arquitetura é aceita. Não é diário de trabalho.
2. **Matriz:** ao concluir um item, mude a **Situação** e preencha a **Evidência** (commit, PR ou teste). Sem evidência, a situação não muda.
3. **ADRs:** cada decisão de arquitetura relevante vira um ADR novo e numerado. Um ADR aceito não é reescrito; quando mudar, cria-se outro que o substitui, e o antigo recebe "Substituído por".
4. **Índice:** é atualizado no mesmo commit em que um documento é criado, movido ou arquivado.
5. **Datas:** sempre absolutas (dd/mm/aaaa).
6. **Marcas de classificação:** usar a legenda do `ContextoProjeto.md` (IMPLEMENTADO, VALIDADO, REQUISITO, PLANEJADO, EM DESENVOLVIMENTO, PENDENTE DE CONFIRMAÇÃO, HISTÓRICO).

## 7. Estratégia para evitar duplicações

- Cada assunto tem **um** documento dono:

  | Assunto                         | Documento dono                     |
  | ------------------------------- | ---------------------------------- |
  | estado real                     | `ContextoProjeto.md`               |
  | requisitos da Etapa 2           | a matriz                           |
  | decisões                        | os ADRs                            |
  | localização dos documentos      | o índice                           |

  Os outros documentos **apontam** para o dono, em vez de copiar o conteúdo.
- O `ContextoProjeto.md` resume os requisitos (seção 3.3) e as decisões (seção 26), mas remete à matriz e ao ADR para o detalhe.
- Não criar versões paralelas com nomes diferentes (`-v2`, `(1)`, `final`). O histórico fica no Git.
- Os rascunhos externos da pasta-pai (`../Indice_Documental_Gestao_Rural.md`, `../matriz-n2-etapa2.md`, `../Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md`) foram **substituídos** pelos documentos de `docs/`. Não foram usados como fonte de autoridade nem alterados. Cabe à equipe arquivá-los ou apagá-los.

## 8. Tratamento de documentos históricos

- Documentos históricos **não são editados nem apagados**; são marcados como HISTÓRICO no índice.
- Quando um plano é substituído (por exemplo, Neon → Supabase), o documento novo cita o antigo, e o `ContextoProjeto.md` mantém a decisão anterior na seção 26 como HISTÓRICO.
- Fatos de auditoria (commit `f7786e8`, tag, 291 testes, ausência de banco) **não mudam** por causa de uma decisão nova. Eles descrevem o estado daquela data.

## 9. Segurança das informações

- Nunca registrar em Markdown: senhas, tokens, chaves de API, credenciais PostgreSQL ou Supabase, valores do `.env`, conteúdo do `README.txt` ou dados reais do cliente.
- `.env` e `README.txt` estão no `.gitignore` (verificado em 24/10/2026). O repositório é **público**.
- O `Readme.txt` exigido pelo Classroom deve ser entregue por canal privado (ver [matriz](../requisitos/matriz-n2-etapa2.md), seção 7).
- Antes de cada commit, conferir o diff à procura de segredos (ver [guia de integração](LEIA-ME-integracao.md), seção 7).

## 10. Atualizações realizadas nesta fase

| # | Ação                                                                                  | Status    |
| - | ------------------------------------------------------------------------------------- | --------- |
| 1 | Diagnóstico do Git: branch `feature/Auditoria-Correcao`, só `ContextoProjeto.md` modificado, sem arquivos não rastreados | FEITO |
| 2 | Localização e classificação das fontes em `../Documentos/`                            | FEITO     |
| 3 | Releitura das fontes oficiais da Etapa 2 (docx, Classroom, `tecnologias.pdf`, slides) | FEITO     |
| 4 | Criação de `docs/` com `requisitos/`, `arquitetura/` e `organizacao/`                  | FEITO     |
| 5 | Criação do [ADR-001](../arquitetura/ADR-001-supabase.md)                               | FEITO     |
| 6 | Criação da [matriz da Etapa 2](../requisitos/matriz-n2-etapa2.md) (49 itens)          | FEITO     |
| 7 | Criação do [índice](../INDICE.md)                                                      | FEITO     |
| 8 | Criação deste plano e do [guia de integração](LEIA-ME-integracao.md)                   | FEITO     |
| 9 | Atualização pontual do `ContextoProjeto.md` (Supabase, Neon como histórico, links), preservando a auditoria | FEITO |
| 10 | Revisão cruzada de links e consistência; `git diff --check`                          | FEITO     |
| 11 | Revisão humana dos documentos pela equipe                                            | PENDENTE  |
| 12 | Criação do [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md) (fluxo `develop` → `main`; `qa` como HISTÓRICO) e atualização das referências ao fluxo | FEITO |
| 13 | Commit, PR para `develop` e depois para `main`                                       | PENDENTE (exige autorização) |

## 11. Documentos ainda não localizados ou não consultados

| Item                    | Situação                                                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| `ContextoFluxoGit.md`   | não existia; **criado em 24/10/2026** (v1.0) a partir da decisão da equipe              |
| Jira `GR` atual         | **não consultado**; a organização das tarefas será feita depois da consolidação documental |
| Painel do Render / URL pública | não verificados desde 29/09/2026                                                    |
| Projeto Supabase        | não existe evidência de criação                                                            |

## 12. Pendências para encerrar esta fase

| ID    | Pendência                                                                  | Status    |
| ----- | -------------------------------------------------------------------------- | --------- |
| ORG-1 | Revisão dos sete documentos por Pedro Simon e Gustavo Lopes                 | PENDENTE  |
| ORG-2 | Revisar o `ContextoFluxoGit.md` e configurar a proteção de `main`/`develop` (ação de administrador) | PENDENTE |
| ORG-3 | Organizar o Jira (épicos e tarefas da Etapa 2) **depois da consolidação documental** | PENDENTE (após ORG-1 e ORG-5) |
| ORG-4 | Decidir o destino dos rascunhos externos da pasta-pai                      | PENDENTE  |
| ORG-5 | Integrar a documentação ao Git (`docs/*` → `develop` → `main`) com autorização | PENDENTE |
| ORG-6 | Registrar uma resposta ou decisão provisória para Q-01 e Q-02 da matriz    | PENDENTE  |

## 13. Checklist de validação

| Verificação                                                                  | Status    |
| ---------------------------------------------------------------------------- | --------- |
| Sete documentos existem nos caminhos definidos (seis da organização + `ContextoFluxoGit.md`) | FEITO |
| Links relativos entre os documentos conferidos                               | FEITO     |
| Nenhum segredo ou valor do `.env` nos documentos                              | FEITO     |
| Nenhum arquivo de código, configuração ou dependência alterado               | FEITO     |
| Auditoria preservada no `ContextoProjeto.md` (`f7786e8`, tag, 291 testes, sem banco) | FEITO |
| Supabase descrito como **planejado**, nunca como implementado                | FEITO     |
| Neon preservado como HISTÓRICO                                               | FEITO     |
| `git diff --check` sem erros                                                  | FEITO     |
| `ContextoFluxoGit.md` criado e referências ao fluxo atualizadas (`qa` → `develop`) | FEITO |
| Jira conferido                                                               | ADIADO (após a consolidação documental) |
| Revisão humana                                                               | PENDENTE  |

## 14. Critérios para iniciar a divisão de responsabilidades (Fase 2)

A Fase 2 pode começar quando:

1. a equipe revisou e aceitou a matriz e o ADR-001 (ORG-1);
2. existe resposta ou decisão provisória para **Q-01** (escopo dos CRUDs) e **Q-02** (criação automática ou com confirmação), porque elas definem o tamanho do trabalho;
3. o [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md) foi revisado pela equipe (ORG-2);
4. a documentação foi integrada ou, no mínimo, está disponível para os dois integrantes.

Dado o prazo de 27/10/2026, o critério 4 pode ser aceito de forma provisória, desde que isso fique registrado. A organização das tarefas no Jira vem depois da consolidação documental.
