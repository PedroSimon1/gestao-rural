# LEIA-ME — Integração da Documentação

Guia rápido para Pedro Simon, Gustavo Lopes e agentes de IA (Claude Code, ChatGPT Codex e outros): como usar e manter a documentação do Gestão Rural durante a N2 Etapa 2.

---

## 1. Para que servem os documentos

| Documento                                                                          | Use quando precisar…                                                       |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [`ContextoProjeto.md`](../../ContextoProjeto.md)                                   | saber o que o sistema **faz hoje**, como está montado e o que falta        |
| [`docs/INDICE.md`](../INDICE.md)                                                   | encontrar qualquer documento e saber se ele é oficial, atual ou histórico  |
| [`docs/requisitos/matriz-n2-etapa2.md`](../requisitos/matriz-n2-etapa2.md)         | saber exatamente o que o professor pediu e a situação de cada item         |
| [`docs/arquitetura/ADR-001-supabase.md`](../arquitetura/ADR-001-supabase.md)       | entender a decisão Supabase e o que ela implica                            |
| [`Plano_Organizacao_Documental_…md`](Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md) | conhecer as regras de manutenção e as pendências desta fase      |
| [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md)                                 | criar branches, commitar, abrir PR, homologar, publicar, fazer hotfix      |

**Para agentes de IA:** leia primeiro o `ContextoProjeto.md`, depois a matriz e as regras para IA do `ContextoFluxoGit.md` (seção 13). Não trate itens PLANEJADO ou REQUISITO como existentes. Confirme no código antes de afirmar qualquer comportamento.

## 2. Como consultar o índice

1. Abra o [mapa rápido](../INDICE.md#2-mapa-rápido) para achar o documento certo.
2. Antes de usar um documento, confira a categoria e a autoridade dele na tabela de rastreabilidade (seção 9 do índice).
3. Caminhos em `código` começando com `../Documentos/` são relativos à raiz do repositório. Esses arquivos existem só na máquina local, não no GitHub.

## 3. Como usar a matriz de requisitos

- Cite o **ID** (por exemplo `FLU-04`, `RN-02`, `DEL-05`) em tarefas do Jira, nomes de branch, mensagens de commit e PRs.
- Ao concluir um item, atualize na matriz:
  - a **Situação**;
  - a **Evidência**: commit, PR ou teste.

  Sem evidência, a situação não muda.
- A coluna **Responsável** só é preenchida na Fase 2 (divisão de responsabilidades).
- Dúvidas novas viram uma linha na seção 8 da matriz (`Q-NN`).

## 4. Como registrar uma nova decisão de arquitetura

1. Crie `docs/arquitetura/ADR-NNN-assunto.md` com o próximo número (o próximo é `ADR-002`).
2. Use a mesma estrutura do ADR-001: identificação, contexto, problema, decisão, alternativas, consequências, riscos, pendências, critérios de validação e referências.
3. Estado inicial: `PROPOSTO` ou `ACEITO PARA PLANEJAMENTO — NÃO IMPLEMENTADO`. Mude para `IMPLEMENTADO` só com evidência.
4. Para mudar uma decisão aceita, crie um ADR novo que a substitui e marque o antigo com "Substituído por ADR-NNN". Não reescreva o ADR antigo.
5. Atualize o índice e a seção 26 do `ContextoProjeto.md`.

## 5. Quando atualizar o `ContextoProjeto.md`

Atualize quando:

- uma mudança for **integrada** em `develop`/`main`: banco, models, fluxo, telas, testes, deploy, segurança;
- um ADR for aceito ou substituído;
- um requisito oficial novo ou alterado for publicado pelo professor.

Ao atualizar:

- revise as seções 1.2 (referência de commit/data) e 21.1 (resultado real dos testes);
- não reaproveite contagens antigas;
- passe o item de PLANEJADO para IMPLEMENTADO e registre a versão anterior como HISTÓRICO na seção 26, se for relevante.

## 6. Como manter histórico sem duplicar

- O histórico fica no **Git**. Não crie cópias como `ContextoProjeto-v2.md`, `matriz (1).md` ou `final-final.md`.
- Cada assunto tem um documento dono (ver [plano, seção 7](Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md#7-estratégia-para-evitar-duplicações)). Os outros documentos fazem link, não copiam.
- Documento superado: marque-o como HISTÓRICO no índice e mantenha o arquivo.

## 7. Revisão antes do commit

Comandos só de leitura:

```bash
git status --short --branch       # confirmar branch e arquivos tocados
git diff --check                  # espaços em branco e marcadores de conflito
git diff                          # revisar alterações rastreadas
git diff --stat
git status --short --untracked-files=all   # novos arquivos (ex.: docs/)
git check-ignore -v .env README.txt        # confirmar que segredos continuam ignorados
```

Checklist:

- [ ] Só os arquivos pretendidos aparecem no `git status`.
- [ ] Nenhuma senha, token, chave, URL de conexão ou valor do `.env` no diff.
- [ ] Nenhum plano descrito como implementado.
- [ ] Links relativos funcionando.
- [ ] Índice atualizado se um documento foi criado, movido ou removido.
- [ ] `git add` com a lista explícita de arquivos (nunca `git add .` sem revisar).

## 8. Fluxo Git acordado

**Fluxo oficial:** o fluxo vigente e completo está em [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md) (v1.0, 24/10/2026). Resumo:

```text
feature/* · fix/* · docs/* · refactor/* · test/* · chore/*  ──PR──▶  develop  ──PR (homologado)──▶  main
hotfix/*  ──PR──▶  main  ──PR de sincronização──▶  develop
```

- `main` = produção; `develop` = integração, testes e homologação.
- Branches de tarefa saem da `develop` atualizada. Toda mudança entra por PR.
- Nenhum desenvolvimento ou push direto em `main` ou `develop`.
- Commit, push, PR e merge só com autorização da equipe.
- **HISTÓRICO:** até 24/10/2026, o fluxo documentado usava a branch `qa` (`feature/*` ou `docs/*` → `qa` → `main`). A `qa` foi excluída do GitHub e substituída pela `develop`.

**Situação real verificada em 24/10/2026:**

- Todos os PRs #1–#19 foram direto para a `main`.
- `main` e `develop` estão no mesmo commit (`f7786e8`).
- Não há proteção de branch nem CI. As regras valem por disciplina da equipe até a configuração recomendada em `ContextoFluxoGit.md`, seção 11.2.
- Na máquina local ainda existem a branch `qa` e a referência `origin/qa`. Não existe `develop` local. Limpeza manual: `ContextoFluxoGit.md`, seção 3.4.
- O trabalho desta documentação está na branch local `feature/Auditoria-Correcao`, criada a partir da `main` (`f7786e8`, igual à `develop`). Ela não segue o padrão `docs/*` em minúsculas.

**Sequência sugerida para integrar esta documentação** (não executada; requer autorização):

1. Revisar os arquivos (seção 7).
2. Opcionalmente, renomear a branch local para o padrão: `git branch -m docs/n2-etapa2-organizacao-documental`. Como a base é igual à `develop`, continua válida.
3. Fazer um commit só com a documentação, listando os arquivos explicitamente:
   - `ContextoProjeto.md`;
   - `ContextoFluxoGit.md`;
   - `docs/INDICE.md`;
   - `docs/requisitos/matriz-n2-etapa2.md`;
   - `docs/arquitetura/ADR-001-supabase.md`;
   - `docs/organizacao/Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md`;
   - `docs/organizacao/LEIA-ME-integracao.md`.
4. Fazer o push da branch e abrir o PR com base **`develop`**.
5. Depois da revisão e homologação, fazer o PR `develop` → `main`.

## 9. Arquivos que não podem ser publicados

| Arquivo / dado                               | Motivo                                                  |
| -------------------------------------------- | ------------------------------------------------------- |
| `.env`                                       | segredos locais (ignorado pelo Git)                     |
| `README.txt` / `Readme.txt` da entrega       | login, senha e chave de LLM (ignorado pelo Git); entregar por canal privado |
| Credenciais do Supabase (senha, string de conexão, chaves de serviço) | acesso total ao banco                     |
| Gemini API Keys                              | custo e abuso da conta                                  |
| `staticfiles/`, `media/`, `uploads/`, `.venv/` | artefatos locais (ignorados pelo Git)                  |
| Notas fiscais e dados reais do cliente       | dados pessoais                                          |

No `.env.example` entram só os **nomes** das variáveis, nunca os valores.

## 10. O que ainda depende de validação

| Item                                              | Onde acompanhar                                                        |
| ------------------------------------------------- | ---------------------------------------------------------------------- |
| Revisão do [`ContextoFluxoGit.md`](../../ContextoFluxoGit.md) e proteção de `main`/`develop` | [plano](Plano_Organizacao_Documental_Gestao_Rural_N2_Etapa2.md), ORG-2 |
| Organização das tarefas no Jira `GR` (**depois da consolidação documental**) | plano, ORG-3                                  |
| Escopo dos CRUDs e criação automática (Q-01, Q-02) | [matriz](../requisitos/matriz-n2-etapa2.md), seção 8                   |
| Canal de entrega do `Readme.txt` (Q-07)           | matriz, seção 8                                                         |
| Implementação do Supabase e validação do Psycopg 3 | [ADR-001](../arquitetura/ADR-001-supabase.md), seções 13 e 14          |
| Estado atual do serviço no Render                 | `ContextoProjeto.md`, seção 22.2                                        |
