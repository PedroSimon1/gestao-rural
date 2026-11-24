# Índice Documental — Gestão Rural

> Estado atual: auditoria de 24/11/2026 em `5f19ce0` (seção 12), que sucede a GR-16 de 27/10/2026 (seção 11). Entradas antigas abaixo preservam a organização histórica. Use os documentos atuais das seções 11 e 12 para operação e evidências.

## 1. Identificação

| Item                    | Valor                                                                                  |
| ----------------------- | -------------------------------------------------------------------------------------- |
| Projeto                 | Gestão Rural (Projeto Administrativo-Financeiro) — ESW424, UniRV                        |
| Finalidade deste índice | dizer **quais documentos existem, para que servem, onde estão e qual a autoridade de cada um** |
| Data da organização     | 24/10/2026                                                                             |
| Estado da documentação  | Fases 1 e 2 integradas à `develop`; auditorias GR-16 (27/10/2026) e de 24/11/2026 em `docs/organizacao/` e `docs/auditoria/`. Defasagens remanescentes listadas em [`auditoria/Auditoria-2026-11-24.md`](auditoria/Auditoria-2026-11-24.md), item B-01 |
| Mantido junto com       | [`../ContextoProjeto.md`](../ContextoProjeto.md) e [`organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md`](organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md) |

**Como ler os caminhos:**

- **No repositório:** o caminho tem link relativo e funciona no GitHub.
- **Fora do repositório:** o caminho está em `código` e é relativo à **raiz do repositório**. Esses arquivos existem só na máquina local da equipe e não estão no Git.

Estes documentos não estão no Git e não devem ser versionados: os acadêmicos ficam fora para preservar os originais; os restritos, porque contêm segredos.

## 2. Mapa rápido

| Preciso saber…                                     | Consulte                                                                  |
| -------------------------------------------------- | ------------------------------------------------------------------------- |
| o estado real do sistema e da Etapa 1              | [`ContextoProjeto.md`](../ContextoProjeto.md)                             |
| o que o professor pediu na Etapa 2                 | [`requisitos/matriz-n2-etapa2.md`](requisitos/matriz-n2-etapa2.md)        |
| por que Supabase e não Neon                        | [`arquitetura/ADR-001-supabase.md`](arquitetura/ADR-001-supabase.md)      |
| como a documentação é organizada e mantida         | [`organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md`](organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md) |
| como integrar a documentação ao fluxo de trabalho  | [`organizacao/LEIA-ME-integracao.md`](organizacao/LEIA-ME-integracao.md)  |
| quem faz o quê na Etapa 2, pacotes e tarefas do Jira | [`organizacao/Plano_Responsabilidades_N2_Etapa2.md`](organizacao/Plano_Responsabilidades_N2_Etapa2.md) |
| como criar branches, commitar e abrir PRs          | [`ContextoFluxoGit.md`](../ContextoFluxoGit.md)                           |
| como os componentes de Pedro e Gustavo se integram na GR-51 | [`contratos/ContratoIntegracaoGR51.md`](contratos/ContratoIntegracaoGR51.md) |
| o estado do projeto, riscos e ações recomendadas mais recentes | [`auditoria/Auditoria-2026-11-24.md`](auditoria/Auditoria-2026-11-24.md) |
| a documentação completa do sistema (visão geral, arquitetura, requisitos, regras, fluxos, dados, Agents, segurança, operação, testes, pendências) | [`documentacao/README.md`](documentacao/README.md) |

## 3. Documentos oficiais (professor e Classroom)

| Documento                                          | Finalidade                                                                                   | Localização                                                                 | Estado |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------ |
| `PROJETO ADMINISTRATIVO - N2 - Etapa 2.docx`       | funcionalidades, regras de negócio, fluxo da Etapa 2, entidades, entrega, recomendação de layout | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/`                    | localizado, lido |
| `Instruções Parte 2.pdf`                           | captura da postagem do Classroom: prazo 27/10, 45 pontos, `Readme.txt`, código do commit na tela | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/`                    | localizado, lido (imagem) |
| `03 - Aula - Pratica de Engenharia (Agents).pptx`  | conceito de Agents e A2A; requisitos da Etapa 1 (slides 18–21)                               | `../Documentos/Att-01--21-09-Agent IA/Material/`                            | localizado, lido |
| Notas fiscais de teste (`danfe (ciclano - pecas).pdf`, `nota_fiscal_teste_cpf_invalido.pdf`) | entradas de exemplo para o processamento                      | `../Documentos/Att-01--21-09-Agent IA/Nota Fiscal - Teste/`                 | localizado |

## 4. Documentação conceitual (cliente e requisitos)

| Documento                                                   | Finalidade                                                              | Localização                                                      | Estado |
| ----------------------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------- | ------ |
| `Documento de Requisitos Cliente (1).docx` (DR 0001/2026)   | problema do produtor rural, categorias do cliente, visão do sistema completo | `../Documentos/Material-Suporte/Material Suporte/`             | localizado, lido |
| `Modelo de especificação de requisitos.pdf`                 | modelo do professor para a especificação                                | `../Documentos/Material-Suporte/Material Suporte/`               | localizado |
| `Documento-SistemaFinanceiro-V0.91.docx`                    | especificação de requisitos da equipe (V0.91)                           | `../Documentos/Documentação/V0.91/`                              | localizado, lido (texto) |
| `DOCUMENTACAOREQUISITOS_PedroSimon_GustavoLopes.pdf`        | versão PDF da especificação V0.91                                       | `../Documentos/Documentação/V0.91/`                              | localizado, lido (texto) |
| `Analise_Tecnica_Documento_Requisitos_Cliente.pdf`, `Documentacao_Explicacao_Modelo_Requisitos.pdf`, `Projeto_Gestao_Financeira_Rural.pdf` | material de apoio produzido para interpretar os requisitos | `../Documentos/Material-Suporte/Material Tratado/`               | localizado; apoio |

## 5. Documentação técnica

| Documento                                                        | Finalidade                                                             | Localização | Estado |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------- | ----------- | ------ |
| [`ContextoProjeto.md`](../ContextoProjeto.md)                    | fonte central de verdade técnica e conceitual; seção 36 = auditoria GR-16 (27/10/2026) | repositório | seção 37 registra a auditoria de 24/11/2026; seções antigas são histórico datado |
| [`ADR-001-supabase.md`](arquitetura/ADR-001-supabase.md)          | decisão Supabase PostgreSQL para a Etapa 2                             | repositório | ACEITO; implementado (GR-33, PR #22). O texto de contexto e a seção de implementação ainda descrevem `DATABASES = {}` e a GR-33 como não integrada (defasagem registrada na auditoria de 24/11/2026) |
| [`ContratoIntegracaoGR51.md`](contratos/ContratoIntegracaoGR51.md) | contrato técnico de integração da GR-51 (Agents, GR-40, GR-43, financeiro) | repositório | **MINUTA 0.2** (27/10/2026): decisões D-01 a D-05 incorporadas; demais aguardando ratificação |
| [`matriz-n2-etapa2.md`](requisitos/matriz-n2-etapa2.md)           | rastreabilidade dos requisitos da Etapa 2                              | repositório | novo |
| `tecnologias.pdf`                                                | stack da Etapa 2 com Render + **Neon** (out/2026)                      | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/` | localizado; **histórico quanto ao Neon** (substituído pelo ADR-001) |
| `MVPcompleto.pdf`                                                | arquitetura e execução do MVP da Etapa 1                               | `../Documentos/Att-01--21-09-Agent IA/Documentação/` | localizado; histórico (anterior ao PR #15) |
| Código e testes                                                  | implementação real                                                     | `agents/`, `cadastros/`, `documentos/`, `financeiro/`, `usuarios/`, `config/`, `build.sh`, `start.sh` | referência `5f19ce0` (24/11/2026) |

## 6. Processos e gerenciamento

| Documento                         | Finalidade                                                    | Localização                                                     | Estado |
| --------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------- | ------ |
| [`ContextoFluxoGit.md`](../ContextoFluxoGit.md) | fluxo Git oficial: `develop` (integração/homologação) → `main` (produção); nomes, commits, PR, hotfix, proteção, regras para IA | repositório (raiz) | **criado em 24/10/2026 (v1.0)**; não existia antes. O fluxo anterior com `qa` está registrado como HISTÓRICO nele |
| [`Plano_Responsabilidades_N2_Etapa2.md`](organizacao/Plano_Responsabilidades_N2_Etapa2.md) | decisões Q-01/Q-02 da equipe, divisão Pedro/Gustavo, pacotes P01–P10, contrato a acordar e tarefas propostas para o Jira | repositório | **criado em 24/10/2026**; aprovado para planejamento, em revisão; nada implementado |
| `ContextoTasksJira.md`            | retrato das tarefas Jira (projeto `GR`)                       | `../Documentos/Att-01--21-09-Agent IA/Contexto/Novo Contexto/`  | localizado; **retrato de 23/09/2026**, anterior à Etapa 2 |
| Jira (projeto `GR`)               | status atual das tarefas e responsáveis                       | serviço externo                                                 | **não consultado** (sem acesso nesta sessão); tarefas da Etapa 2 **preparadas** no plano de responsabilidades (seção 6), ainda **não cadastradas** |
| `FluxoAtividadeAula.pdf`          | roteiro de execução e apresentação da atividade em aula       | `../Documentos/Att-01--21-09-Agent IA/Documentação/`            | localizado; Etapa 1 |
| GitHub (PRs #1–#19, branches)     | histórico de integração                                       | `https://github.com/PedroSimon1/gestao-rural`                   | consultado em 24/10/2026 |

## 7. Documentos históricos

São referências do passado. **Não tratar como estado atual.**

| Documento                                                   | O que registra                                                     | Localização                                                  |
| ----------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------ |
| `Mini_Documentacao_Tecnologias_Gestao_Rural.pdf`            | stack inicial (DRF, PostgreSQL, React futuro), removida no PR #15   | `../Documentos/Att-01--21-09-Agent IA/Contexto/`             |
| `contextoatividade.md` (22/09/2026)                         | contexto da atividade de Agents antes da entrega da Etapa 1         | `../Documentos/Att-01--21-09-Agent IA/Contexto/`             |
| `contextolopes.md` (22/09/2026)                             | contexto preparado para Gustavo Lopes na Etapa 1                    | `../Documentos/Att-01--21-09-Agent IA/Contexto/`             |
| `Guia_Tarefas_Gustavo_Gestao_Rural.pdf`                     | guia das tarefas de Gustavo Lopes na Etapa 1                        | `../Documentos/Att-01--21-09-Agent IA/Contexto/`             |
| `TarefasRealizadasSimon.pdf`, `TarefasRealizadasLopes.pdf`  | relatos das tarefas da Etapa 1                                      | `../Documentos/Att-01--21-09-Agent IA/Documentação/`         |
| `Demonstração-Gestao-Rural-n2.mp4`                          | vídeo de demonstração da Etapa 1                                    | `../Documentos/Entregas/`                                    |
| `tecnologias.pdf` (item Neon)                               | plano Neon substituído pelo ADR-001                                 | ver seção 5                                                  |
| `analisetemporaria.md`                                      | rascunho de trabalho; removido do Git em `d37caa9`                   | só no histórico Git                                          |
| Fluxo com a branch `qa`                                     | `feature/*`/`docs/*` → `qa` → `main` (29/09–24/10/2026); `qa` excluída e substituída pela `develop` | [`ContextoFluxoGit.md`](../ContextoFluxoGit.md), seção 2.1 |
| Rascunhos externos `Indice_Documental_Gestao_Rural.md`, `matriz-n2-etapa2.md`, `Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md` (24/10/2026) | versões preliminares produzidas fora do repositório; **substituídas** pelos documentos de `docs/` | `../` (pasta-pai do repositório) |

## 8. Documentos restritos

Classes de documentos que **nunca** podem ser publicadas no repositório (que é público) nem copiadas para a documentação:

| Classe                                 | Exemplos                                                       | Regra                                                                              |
| -------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Variáveis de ambiente                  | `.env`, valores no painel do Render                            | ignorado pelo Git; na documentação, registrar **somente nomes** de variáveis       |
| `README.txt` / `Readme.txt` de entrega | link da hospedagem, login, senha, chave de LLM                 | ignorado pelo Git; entregar por canal privado (Classroom ou outro aprovado)        |
| Credenciais de banco                   | senha/URL de conexão do Supabase, chaves de serviço             | só em variáveis de ambiente; nunca em Markdown, código ou `.env.example`           |
| Chaves de IA                           | Gemini API Keys                                                | digitadas na tela; nunca versionadas                                               |
| Dados reais do cliente                 | notas fiscais reais, CPF/CNPJ reais                            | não versionar; usar documentos de teste                                            |

## 9. Tabela de rastreabilidade

| Nome                                                | Finalidade                         | Localização                                            | Categoria   | Autoridade                       | Disponibilidade    | Situação de atualização                    |
| --------------------------------------------------- | ---------------------------------- | ------------------------------------------------------ | ----------- | -------------------------------- | ------------------ | ------------------------------------------ |
| `PROJETO ADMINISTRATIVO - N2 - Etapa 2.docx`        | requisitos da Etapa 2              | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/` | Oficial     | máxima para requisitos acadêmicos | localizado         | original preservado                        |
| `Instruções Parte 2.pdf`                            | critérios de entrega               | idem                                                   | Oficial     | máxima para entrega              | localizado         | original preservado                        |
| `03 - Aula - Pratica de Engenharia (Agents).pptx`   | Agents e Etapa 1                   | `../Documentos/Att-01--21-09-Agent IA/Material/`       | Oficial     | máxima para a Etapa 1            | localizado         | original preservado                        |
| `Documento de Requisitos Cliente (1).docx`          | requisitos do cliente              | `../Documentos/Material-Suporte/Material Suporte/`     | Oficial (cliente) | máxima para o negócio      | localizado         | original preservado                        |
| `Documento-SistemaFinanceiro-V0.91.docx` + PDF      | especificação da equipe            | `../Documentos/Documentação/V0.91/`                    | Histórica / Planejamento | complementar        | localizado         | não atualizada desde 31/08/2026            |
| `ContextoProjeto.md`                                | estado técnico consolidado         | [repositório](../ContextoProjeto.md)                   | Técnica atual | máxima para o estado implementado | localizado       | atualizado em 24/10/2026, sem commit       |
| `docs/arquitetura/ADR-001-supabase.md`              | decisão de banco                   | [repositório](arquitetura/ADR-001-supabase.md)         | Planejamento | decisão mais recente da equipe   | localizado         | criado em 24/10/2026                       |
| `docs/requisitos/matriz-n2-etapa2.md`               | rastreabilidade da Etapa 2         | [repositório](requisitos/matriz-n2-etapa2.md)          | Técnica atual | derivada das fontes oficiais     | localizado         | criado em 24/10/2026                       |
| `docs/INDICE.md`                                    | índice                             | este arquivo                                           | Processo    | organizacional                   | localizado         | criado em 24/10/2026                       |
| `docs/organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md` | procedimento de organização | [repositório](organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md) | Processo | organizacional | localizado | criado em 24/10/2026                       |
| `docs/organizacao/LEIA-ME-integracao.md`            | guia de integração                 | [repositório](organizacao/LEIA-ME-integracao.md)       | Processo    | organizacional                   | localizado         | criado em 24/10/2026                       |
| `docs/organizacao/Plano_Responsabilidades_N2_Etapa2.md` | escopo e responsabilidades da Etapa 2 | [repositório](organizacao/Plano_Responsabilidades_N2_Etapa2.md) | Planejamento / Processo | decisão da equipe para planejamento | localizado | criado em 24/10/2026, em revisão |
| `tecnologias.pdf`                                   | stack da Etapa 2 (Neon)            | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/` | Histórica (Neon) / Técnica (demais itens) | substituída pelo ADR-001 no item banco | localizado | não editar               |
| `Mini_Documentacao_Tecnologias_Gestao_Rural.pdf`    | stack inicial                      | `../Documentos/Att-01--21-09-Agent IA/Contexto/`       | Histórica   | nenhuma sobre o estado atual     | localizado         | superada                                   |
| `ContextoTasksJira.md`                              | tarefas Jira                       | `../Documentos/Att-01--21-09-Agent IA/Contexto/Novo Contexto/` | Processo / Histórica | o Jira atual prevalece | localizado | retrato de 23/09/2026                      |
| Jira `GR`                                           | status e responsáveis              | externo                                                | Processo    | máxima para status de tarefas    | **não consultado** | tarefas propostas no plano de responsabilidades; cadastro após a revisão |
| `ContextoFluxoGit.md`                               | regras de Git                      | [repositório](../ContextoFluxoGit.md)                  | Processo    | máxima para o fluxo Git          | localizado         | criado em 24/10/2026 (v1.0)                |
| `MVPcompleto.pdf`, `FluxoAtividadeAula.pdf`         | MVP e roteiro da Etapa 1           | `../Documentos/Att-01--21-09-Agent IA/Documentação/`   | Histórica   | complementar                     | localizado         | anterior ao PR #15                         |
| `.env`, `README.txt`                                | segredos e entrega                 | raiz do repositório (ignorados pelo Git)               | Restrita    | —                                | existem localmente; conteúdo não lido | nunca publicar |

## 10. Manutenção deste índice

- Ao criar, mover, renomear ou arquivar um documento, atualize as seções 3 a 9 no mesmo commit.
- Não registre conteúdo restrito aqui, só a existência da classe.
- As regras gerais estão no [plano de organização](organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md), seções 6 a 8.

## 11. Atualização integrada GR-16 — 27/10/2026

| Documento | Finalidade atual |
| --- | --- |
| [README](../README.md) | Instalar/iniciar com PostgreSQL/TLS, testes, fluxos, limites e publicação humana |
| [Contexto](../ContextoProjeto.md#auditoria-gr16) | Auditoria completa na seção 36; histórico anterior preservado |
| [Matriz](requisitos/matriz-n2-etapa2.md) | 49 requisitos com evidências e pendências atuais |
| [Auditoria GR-16](organizacao/GR-16-auditoria-aaa80cc.md) | Base, método, testes, divergências do Jira e bloqueios |
| [Operação](operacao/GuiaOperacaoN2.md) | DEV/TEST/QA/PROD, migrations, validação, limpeza e entrega restrita |
| [Contrato GR-51](contratos/ContratoIntegracaoGR51.md) | Adendo integrado, T-05/P-09 e fronteiras de F-6 |
| [Alinhamento F-6](contratos/F6-idempotencia-alinhamento.md) | Lacuna reproduzida e proposta não aprovada de operação idempotente |

Implementado/integrado/validado localmente não significa homologado ou publicado.
O documento restrito de credenciais permanece fora do Git e não foi lido.

## 12. Auditoria de 24/11/2026

Referência `5f19ce0`; `main` (`c3d4239`, PR #58) tem a mesma árvore da `develop`.

| Documento | Finalidade |
| --- | --- |
| [Auditoria 24/11/2026](auditoria/Auditoria-2026-11-24.md) | Verificações executadas (1.153 testes OK), pontos fortes, achados A-01 a B-05 por severidade e ações recomendadas |

Achados que exigem ação antes de publicar: Django 6.1.1 sem as correções de
segurança 6.1.2/6.1.3 (A-01). Nenhuma alteração de código ou dependência foi
feita pela auditoria. `.env` e `README.txt` não foram lidos.

## 13. Documentação do sistema — 24/11/2026

Pasta [`documentacao/`](documentacao/README.md): documentação de referência escrita a partir do código integrado (`71297a0`).
Descreve o que existe; o planejado e os riscos aparecem marcados. Código e testes prevalecem em caso de divergência.

| Documento | Finalidade |
| --- | --- |
| [README](documentacao/README.md) | Índice, convenções e manutenção |
| [01 Visão geral](documentacao/01-visao-geral.md) | Problema, escopo, estado atual, tecnologias, glossário |
| [02 Arquitetura](documentacao/02-arquitetura.md) | Camadas, apps, dependências, ambientes |
| [03 Requisitos](documentacao/03-requisitos.md) | RF e RNF com a situação real |
| [04 Regras de negócio](documentacao/04-regras-de-negocio.md) | RN oficiais e regras técnicas, com o ponto do código |
| [05 Fluxos](documentacao/05-fluxos.md) | Login, processamento, conferência, confirmação, conta manual, cadastros |
| [06 Modelo de dados](documentacao/06-modelo-de-dados.md) | Tabelas, constraints, gatilho, migrations |
| [07 Agents e contratos](documentacao/07-agents-e-contratos.md) | Gemini, Extrator, Classificador, JSON v1/v2, correções |
| [08 Interface e rotas](documentacao/08-interface-e-rotas.md) | URLs, telas, formulários |
| [09 Segurança e privacidade](documentacao/09-seguranca-e-privacidade.md) | Controles, LGPD, riscos |
| [10 Configuração e operação](documentacao/10-configuracao-e-operacao.md) | Variáveis, migrations, publicação, rotinas |
| [11 Testes](documentacao/11-testes.md) | Executor, organização, convenções |
| [12 Pendências e riscos](documentacao/12-pendencias-e-riscos.md) | O que falta, decisões em aberto, achados |
| [13 Guia do desenvolvedor](documentacao/13-guia-do-desenvolvedor.md) | Onde mexer, invariantes, receitas |
