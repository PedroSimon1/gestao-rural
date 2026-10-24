# ADR-001 — Adoção do Supabase PostgreSQL para a N2 Etapa 2

> **Estado: ACEITO PARA PLANEJAMENTO — NÃO IMPLEMENTADO.**
>
> Este registro documenta uma decisão da equipe. Nada do que está descrito aqui existe no código auditado (`f7786e8`, tag `n2-etapa1-final`).

---

## 1. Identificação

| Item                 | Valor                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------- |
| Identificador        | ADR-001                                                                               |
| Título               | Adoção do Supabase PostgreSQL para a N2 Etapa 2                                       |
| Data do registro     | 24/10/2026                                                                            |
| Decisores            | Equipe do projeto (Pedro Simon e Gustavo Lopes)                                       |
| Estado               | **ACEITO PARA PLANEJAMENTO — NÃO IMPLEMENTADO**                                       |
| Substitui            | Plano Render + **Neon** PostgreSQL de `tecnologias.pdf` (out/2026), somente no item "hospedagem do banco" |
| Substituído por      | —                                                                                     |
| Código de referência | `f7786e8` (`main` = `qa` na auditoria; hoje `main` = `develop`), sem banco de dados   |
| Documento central    | [`ContextoProjeto.md`](../../ContextoProjeto.md), seções 9.3, 10.4, 15, 22.2 e 26     |

## 2. Contexto

- A **N2 Etapa 1** foi entregue com uma arquitetura **stateless**:
  - sem banco: `DATABASES = {}` em `config/settings.py`;
  - sem models e sem migrations;
  - testes que **proíbem** banco: `config/test_sem_banco.py` e partes de `config/test_producao.py`.
- A **N2 Etapa 2** (entrega em 27/10/2026, 23h59) exige persistência relacional. Segundo `PROJETO ADMINISTRATIVO - N2 - Etapa 2.docx`, o sistema deve:
  - consultar no banco o fornecedor, o faturado e a classificação de despesa;
  - criar os registros ausentes;
  - criar o movimento e sua parcela;
  - manter cadastros com inativação e reativação.

  As entidades citadas são `PESSOAS`, `CLASSIFICACAO`, `MOVIMENTOCONTAS` e `PARCELACONTAS`. Ver [matriz de requisitos](../requisitos/matriz-n2-etapa2.md).
- Em outubro de 2026, `tecnologias.pdf` registrou o plano anterior:
  - manter o Django no Render Free;
  - adicionar PostgreSQL gerenciado pelo **Neon Free**;
  - usar Django ORM e Migrations;
  - o driver PostgreSQL ficou "a definir".
- Depois da auditoria de 24/10/2026, a equipe decidiu trocar o provedor do banco.

## 3. Problema arquitetural

Qual serviço gerenciado de PostgreSQL deve guardar os dados da Etapa 2? A escolha precisa:

- preservar o backend Django, os Agents e a hospedagem no Render;
- não alterar a autenticação atual nem a política de chave Gemini informada na tela.

## 4. Decisão

**O Supabase PostgreSQL será o serviço gerenciado de banco de dados do projeto na N2 Etapa 2.**

O Supabase será usado **somente como PostgreSQL gerenciado**. O backend Django continua responsável por:

- regras de negócio (inativação, reativação, múltiplas classificações e parcelas);
- consultas financeiras e consultas de existência (fornecedor, faturado, classificação);
- validações (formulários, schemas Pydantic, validador de PDF);
- orquestração dos Agents Extrator e Classificador;
- persistência por meio do **Django ORM**, com o esquema versionado por **Django Migrations**.

O acesso ao banco será feito pelo Django, no servidor. O navegador não acessará o Supabase diretamente.

**Fora do escopo desta decisão:**

| Componente Supabase                      | Situação                                                                        |
| ---------------------------------------- | ------------------------------------------------------------------------------- |
| Supabase Auth                            | **não adotado** — o login de demonstração (`usuarios/demo.py`) continua         |
| Supabase Storage                         | **não adotado** — a Etapa 1 não grava arquivos e não há necessidade confirmada  |
| API REST/GraphQL automática, Realtime, Edge Functions | **não adotados**                                                   |
| Chaves de API do Supabase (anon/service) | não são necessárias para acessar o banco pelo ORM; não devem ser expostas       |

## 5. Tecnologias preservadas

| Tecnologia                                | Papel                                            | Evidência                                        |
| ----------------------------------------- | ------------------------------------------------ | ------------------------------------------------ |
| Python 3.14 (`.python-version` = 3.14.7)  | linguagem                                        | `.python-version`                                |
| Django 6.1.1                              | backend, rotas, formulários, templates, sessão   | `requirements.txt`, `config/`                    |
| Django Templates + HTML/CSS/JavaScript    | interface integrada                              | `*/templates/`, `*/static/`                      |
| Google Gemini API (`google-genai` 2.24.0) | Agents Extrator e Classificador                  | `agents/`                                        |
| Pydantic 2.13.5                           | schemas e validação das respostas de IA          | `agents/*/schemas.py`                            |
| Gunicorn 26.2.0 + WhiteNoise 6.12.0       | servidor e estáticos em produção                 | `start.sh`, `config/settings.py`                 |
| Render                                    | hospedagem da aplicação Django                   | `build.sh`, `start.sh`, registro de 29/09/2026   |
| Git, GitHub, Jira                         | versionamento, PRs, tarefas                      | repositório, `ContextoTasksJira.md`              |

Tecnologias **adicionadas pela decisão** (PLANEJADO):

| Tecnologia                    | Papel                                     | Situação                                         |
| ----------------------------- | ----------------------------------------- | ------------------------------------------------ |
| Supabase PostgreSQL           | banco relacional gerenciado               | projeto Supabase **não criado/não confirmado**   |
| Django ORM                    | models, consultas e escrita               | nenhum model existe                              |
| Django Migrations             | versionamento do esquema                  | nenhuma migration existe; `build.sh` não executa `migrate` |
| Psycopg 3 (driver)            | conexão Django ↔ PostgreSQL               | **proposto, sujeito a validação técnica**; não está em `requirements.txt` |

## 6. Tecnologia substituída

| Item                  | Antes (HISTÓRICO)                            | Agora (PLANEJADO)          |
| --------------------- | -------------------------------------------- | -------------------------- |
| Hospedagem do banco   | Neon Free (`tecnologias.pdf`)                | Supabase PostgreSQL        |
| Banco QA / Produção   | "Neon QA" / "Neon Produção"                  | bancos Supabase independentes por ambiente (a definir) |
| Driver                | "a definir (por exemplo psycopg)"            | Psycopg 3 como candidato   |

O restante de `tecnologias.pdf` continua coerente com esta decisão: Render, Django, Agents, ORM, Migrations e ambientes separados. O PDF **não deve ser editado**. Ele permanece como registro histórico do plano Neon.

## 7. Justificativa

Motivos registrados pela equipe:

- usar o Supabase como infraestrutura PostgreSQL gerenciada;
- deixar aberta a evolução futura do produto dentro da mesma plataforma.

**Limites da justificativa:** não foram registrados estudo comparativo, medição de desempenho, análise de custos nem testes de conexão entre Supabase e Neon. Qualquer afirmação desse tipo exige evidência nova e deve ser acrescentada a este ADR.

## 8. Consequências técnicas

Quando a decisão for implementada, as seguintes mudanças serão necessárias (lista derivada do código atual; nenhuma foi feita):

| Área                       | Arquivo(s) afetado(s)                               | Mudança prevista                                                       |
| -------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| Configuração do banco      | `config/settings.py`                                | substituir `DATABASES = {}` por conexão PostgreSQL lida de variáveis de ambiente |
| Apps Django                | `config/settings.py`                                | incluir o(s) app(s) com os models da Etapa 2                           |
| Dependências               | `requirements.txt`                                  | acrescentar o driver (Psycopg 3, se validado)                          |
| Variáveis de ambiente      | `.env.example` (somente nomes)                      | documentar os nomes das variáveis de conexão; os valores nunca entram no Git |
| Publicação                 | `build.sh` ou comando de pre-deploy do Render       | executar `migrate`                                                     |
| Testes                     | `config/test_sem_banco.py`, `config/test_producao.py` | substituir as garantias de "sem banco" pelo novo contrato; testes com banco precisarão de `TestCase` e de um PostgreSQL de teste |
| Fluxo da tela              | `documentos/views.py`, templates                    | consultas de existência, criação e confirmação do lançamento           |
| Modelo de domínio          | novo(s) app(s)                                      | `PESSOAS`, `CLASSIFICACAO`, `MOVIMENTOCONTAS`, `PARCELACONTAS` — modelagem ainda **não definida** |

Os testes atuais vão **falhar de propósito** assim que qualquer item de banco for adicionado. Essa falha é esperada e deve ser tratada como parte da implementação, não como regressão.

## 9. Impactos na infraestrutura

| Ambiente        | Aplicação                        | Banco (PLANEJADO)                 | Situação                                    |
| --------------- | -------------------------------- | --------------------------------- | ------------------------------------------- |
| Desenvolvimento | local, branch de tarefa          | PostgreSQL local ou projeto Supabase de desenvolvimento (a definir) | não configurado |
| Homologação     | `develop` (homologação local; Render de homologação não definido) | projeto/banco Supabase de homologação | não configurado; não há serviço Render de homologação comprovado. Antes de 24/10/2026: "Render QA / `qa`" (HISTÓRICO; `qa` excluída) |
| Produção        | Render / `main`                  | projeto/banco Supabase de produção | não configurado                             |

Requisitos para a implementação:

- credenciais independentes por ambiente, cadastradas no painel do Render e no `.env` local, **nunca** no repositório;
- escolher o modo de conexão: conexão direta ou *connection pooler* do Supabase. Verificar se o Render alcança o endereço escolhido;
- se for usado o pooler em modo *transaction*, validar o comportamento de *prepared statements* do Psycopg 3 com o Django;
- definir a região do banco e verificar a latência com o Render.

## 10. Impactos na documentação

| Documento                                                     | Impacto                                                                 |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| [`ContextoProjeto.md`](../../ContextoProjeto.md)              | seções de tecnologias, arquitetura alvo, banco, ambientes, decisões, pendências e próximos passos passam a citar Supabase; Neon fica como HISTÓRICO |
| `tecnologias.pdf` (fora do repositório)                       | não editado; passa a ser HISTÓRICO quanto ao Neon                       |
| [`docs/INDICE.md`](../INDICE.md)                              | registra este ADR e o estado de `tecnologias.pdf`                       |
| [`docs/requisitos/matriz-n2-etapa2.md`](../requisitos/matriz-n2-etapa2.md) | itens de planejamento técnico (PT-*) apontam para este ADR    |

## 11. Riscos e limitações

| Risco                                                                         | Situação          |
| ----------------------------------------------------------------------------- | ----------------- |
| Prazo: decisão tomada a 3 dias da entrega (27/10/2026), sem implementação     | crítico           |
| Compatibilidade do Psycopg 3 com Python 3.14 e Django 6.1 no Render           | a validar         |
| Conectividade Render → Supabase (modo de conexão, rede, TLS)                  | a validar         |
| Limites e pausa por inatividade do plano gratuito do Supabase, somados à suspensão do Render Free | a confirmar nas regras vigentes do plano |
| Worker único do Gunicorn e chamadas longas ao Gemini mantendo conexões abertas | a avaliar        |
| Exposição acidental de credenciais em repositório **público**                 | mitigação: variáveis de ambiente, `.env` no `.gitignore`, revisão do diff |
| Confundir componentes do Supabase (Auth, Storage, chaves de API) com requisitos | mitigação: seção 4 deste ADR |

## 12. Alternativas consideradas

| Alternativa                                   | Situação                                                                       |
| --------------------------------------------- | ------------------------------------------------------------------------------ |
| Neon Free PostgreSQL                          | **plano anterior** (`tecnologias.pdf`); substituído por esta decisão. Não há avaliação comparativa registrada |
| Manter a arquitetura sem banco                | incompatível com os requisitos da Etapa 2                                      |
| PostgreSQL do próprio Render ou outro provedor | não há registro de avaliação                                                  |
| Usar Supabase Auth/Storage/API automática     | não adotado; sem necessidade confirmada                                        |

## 13. Pendências de implementação

| ID     | Pendência                                                                      |
| ------ | ------------------------------------------------------------------------------ |
| ADR1-P1 | Criar os projetos/bancos Supabase por ambiente (quem cria e quem tem acesso: a definir) |
| ADR1-P2 | Validar Psycopg 3 (versão, instalação no Render, Python 3.14)                 |
| ADR1-P3 | Definir os nomes das variáveis de conexão e o formato de configuração em `settings.py` |
| ADR1-P4 | Escolher conexão direta ou pooler, com os parâmetros correspondentes          |
| ADR1-P5 | Modelar as entidades da Etapa 2 (fase posterior; não faz parte deste ADR)     |
| ADR1-P6 | Incluir `migrate` na publicação                                                |
| ADR1-P7 | Substituir os testes que proíbem banco                                         |
| ADR1-P8 | Atualizar `.env.example` (somente nomes) e o painel do Render                  |

## 14. Critérios futuros de validação

A decisão só passa para **IMPLEMENTADO** quando houver evidência de que:

1. `python manage.py check` passa com a conexão configurada;
2. `python manage.py migrate` aplica as migrations no banco Supabase do ambiente;
3. a suíte de testes atualizada passa, incluindo testes com banco;
4. `python manage.py check --deploy` em modo produção mostra apenas os avisos aceitos;
5. o fluxo nota → consulta → criação → movimento/parcela → confirmação grava e lê no Supabase pelo Render;
6. nenhuma credencial aparece no repositório (`git diff`, `.env.example` somente com nomes);
7. este ADR e o `ContextoProjeto.md` são atualizados com o commit da implementação.

## 15. Referências

- `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/tecnologias.pdf` — plano anterior com Neon. Caminho relativo à raiz do repositório, fora do Git.
- `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/PROJETO ADMINISTRATIVO - N2 - Etapa 2.docx` — requisitos oficiais da Etapa 2.
- `../Documentos/Att-02--27-10--N2 - Avaliação (Parte 2)/Instruções Parte 2.pdf` — instruções do Classroom.
- [`ContextoProjeto.md`](../../ContextoProjeto.md) — auditoria de 24/10/2026.
- [`docs/requisitos/matriz-n2-etapa2.md`](../requisitos/matriz-n2-etapa2.md).
- Código: `config/settings.py`, `config/test_sem_banco.py`, `config/test_producao.py`, `build.sh`, `requirements.txt`.
- Histórico: PRs #1–#14 usaram PostgreSQL com `psycopg` 3.3.6; o PR #15 (`69b7ca4`) removeu o banco.
