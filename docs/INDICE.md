# Índice Documental — Gestão Rural

## 1. Identificação

| Item                    | Valor                                                                                  |
| ----------------------- | -------------------------------------------------------------------------------------- |
| Projeto                 | Gestão Rural (Projeto Administrativo-Financeiro) — ESW424, UniRV                        |
| Finalidade deste índice | dizer **quais documentos existem, para que servem, onde estão e qual a autoridade de cada um** |
| Data da organização     | 24/10/2026                                                                             |
| Estado da documentação  | Fase 1 (organização documental) integrada à `develop` pelo PR #20; Fase 2 (escopo e responsabilidades) em revisão local na branch `docs/n2-etapa2-escopo-responsabilidades`, sem commit |
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
| [`ContextoProjeto.md`](../ContextoProjeto.md)                    | fonte central de verdade técnica e conceitual; auditoria de 24/10/2026 | repositório | atualizado em 24/10/2026; em 25/10/2026, estado da GR-33 (branch `feature/gr-33-configurar-supabase`, não integrada) |
| [`ADR-001-supabase.md`](arquitetura/ADR-001-supabase.md)          | decisão Supabase PostgreSQL para a Etapa 2                             | repositório | ACEITO — IMPLEMENTAÇÃO EM ANDAMENTO (GR-33, branch `feature/gr-33-configurar-supabase`, não integrada); antes: ACEITO PARA PLANEJAMENTO |
| [`ContratoIntegracaoGR51.md`](contratos/ContratoIntegracaoGR51.md) | contrato técnico de integração da GR-51 (Agents, GR-40, GR-43, financeiro) | repositório | **MINUTA 0.2** (27/10/2026): decisões D-01 a D-05 incorporadas; demais aguardando ratificação |
| [`matriz-n2-etapa2.md`](requisitos/matriz-n2-etapa2.md)           | rastreabilidade dos requisitos da Etapa 2                              | repositório | novo |
| `tecnologias.pdf`                                                | stack da Etapa 2 com Render + **Neon** (out/2026)                      | `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/` | localizado; **histórico quanto ao Neon** (substituído pelo ADR-001) |
| `MVPcompleto.pdf`                                                | arquitetura e execução do MVP da Etapa 1                               | `../Documentos/Att-01--21-09-Agent IA/Documentação/` | localizado; histórico (anterior ao PR #15) |
| Código e testes                                                  | implementação real                                                     | `agents/`, `documentos/`, `usuarios/`, `config/`, `build.sh`, `start.sh` | referência `f7786e8` |

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
