# ADR-001 — Adoção do Supabase PostgreSQL para a N2 Etapa 2

> **Estado: ACEITO — IMPLEMENTAÇÃO EM ANDAMENTO (GR-33: conexão configurada).**
>
> Este registro documenta uma decisão da equipe. Nada do que está descrito aqui existe no código auditado (`f7786e8`, tag `n2-etapa1-final`).
>
> **Atualização de 25/10/2026 (GR-33):** a conexão PostgreSQL foi configurada na branch `feature/gr-33-configurar-supabase`, ainda **não integrada** a `develop`. Não há models, migrations nem `migrate` na publicação. Detalhes na seção 13.1.
>
> **Atualização de 26/10/2026 (GR-34):** a equipe aprovou T-06 (bancos por ambiente) e PT-06 (migrations manuais, sem `migrate` na publicação). Detalhes na seção 13.2.
>
> Estado anterior (HISTÓRICO, 24/10/2026): ACEITO PARA PLANEJAMENTO — NÃO IMPLEMENTADO.

---

## 1. Identificação

| Item                 | Valor                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------- |
| Identificador        | ADR-001                                                                               |
| Título               | Adoção do Supabase PostgreSQL para a N2 Etapa 2                                       |
| Data do registro     | 24/10/2026                                                                            |
| Decisores            | Equipe do projeto (Pedro Simon e Gustavo Lopes)                                       |
| Estado               | **ACEITO — IMPLEMENTAÇÃO EM ANDAMENTO (GR-33: conexão configurada)**; antes: ACEITO PARA PLANEJAMENTO — NÃO IMPLEMENTADO |
| Substitui            | Plano Render + **Neon** PostgreSQL de `tecnologias.pdf` (out/2026), somente no item "hospedagem do banco" |
| Substituído por      | —                                                                                     |
| Código de referência | `f7786e8` (`main` = `qa` na auditoria; hoje `main` = `develop`), sem banco de dados. Conexão em andamento: branch `feature/gr-33-configurar-supabase` (não integrada) |
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

Tecnologias **adicionadas pela decisão** (situação na branch `feature/gr-33-configurar-supabase`, 25/10/2026):

| Tecnologia                    | Papel                                     | Situação                                         |
| ----------------------------- | ----------------------------------------- | ------------------------------------------------ |
| Supabase PostgreSQL           | banco relacional gerenciado               | **EM ANDAMENTO**: um único projeto, `gestao-rural-homologacao` (São Paulo), criado por Pedro Simon; conexão configurada em `config/settings.py` |
| Django ORM                    | models, consultas e escrita               | engine `django.db.backends.postgresql` configurado; nenhum model existe |
| Django Migrations             | versionamento do esquema                  | nenhuma migration existe; `build.sh` não executa `migrate` |
| Psycopg 3 (driver)            | conexão Django ↔ PostgreSQL               | `psycopg[binary]==3.3.6` em `requirements.txt`; instalado e validado localmente; build no Render **não validado** |

## 6. Tecnologia substituída

| Item                  | Antes (HISTÓRICO)                            | Agora (PLANEJADO)          |
| --------------------- | -------------------------------------------- | -------------------------- |
| Hospedagem do banco   | Neon Free (`tecnologias.pdf`)                | Supabase PostgreSQL        |
| Banco QA / Produção   | "Neon QA" / "Neon Produção"                  | bancos Supabase independentes por ambiente (a definir) |
| Driver                | "a definir (por exemplo psycopg)"            | Psycopg 3 (`psycopg[binary]==3.3.6`, GR-33) |

O restante de `tecnologias.pdf` continua coerente com esta decisão: Render, Django, Agents, ORM, Migrations e ambientes separados. O PDF **não deve ser editado**. Ele permanece como registro histórico do plano Neon.

## 7. Justificativa

Motivos registrados pela equipe:

- usar o Supabase como infraestrutura PostgreSQL gerenciada;
- deixar aberta a evolução futura do produto dentro da mesma plataforma.

**Limites da justificativa:** não foram registrados estudo comparativo, medição de desempenho, análise de custos nem testes de conexão entre Supabase e Neon. Qualquer afirmação desse tipo exige evidência nova e deve ser acrescentada a este ADR.

## 8. Consequências técnicas

Quando a decisão for implementada, as seguintes mudanças serão necessárias (lista derivada do código de 24/10/2026). Na GR-33 (branch `feature/gr-33-configurar-supabase`, não integrada) foram feitas a configuração do banco, a dependência e as variáveis de ambiente (`.env.example`); a adaptação dos testes de "sem banco" está em andamento; as demais continuam pendentes:

| Área                       | Arquivo(s) afetado(s)                               | Mudança prevista                                                       |
| -------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| Configuração do banco      | `config/settings.py`                                | substituir `DATABASES = {}` por conexão PostgreSQL lida de variáveis de ambiente |
| Apps Django                | `config/settings.py`                                | incluir o(s) app(s) com os models da Etapa 2                           |
| Dependências               | `requirements.txt`                                  | acrescentar o driver (Psycopg 3, se validado)                          |
| Variáveis de ambiente      | `.env.example` (somente nomes)                      | documentar os nomes das variáveis de conexão; os valores nunca entram no Git |
| Publicação                 | `build.sh` ou comando de pre-deploy do Render       | ~~executar `migrate`~~; substituído em 26/10/2026 pela decisão PT-06: migrations aplicadas manualmente, nunca na publicação (seção 13.2) |
| Testes                     | `config/test_sem_banco.py`, `config/test_producao.py` | substituir as garantias de "sem banco" pelo novo contrato; testes com banco precisarão de `TestCase` e de um PostgreSQL de teste |
| Fluxo da tela              | `documentos/views.py`, templates                    | consultas de existência, criação e confirmação do lançamento           |
| Modelo de domínio          | novo(s) app(s)                                      | `PESSOAS`, `CLASSIFICACAO`, `MOVIMENTOCONTAS`, `PARCELACONTAS` — modelagem ainda **não definida** |

Os testes atuais vão **falhar de propósito** assim que qualquer item de banco for adicionado. Essa falha é esperada e deve ser tratada como parte da implementação, não como regressão.

## 9. Impactos na infraestrutura

| Ambiente        | Aplicação                        | Banco (PLANEJADO)                 | Situação                                    |
| --------------- | -------------------------------- | --------------------------------- | ------------------------------------------- |
| Desenvolvimento | local, branch de tarefa          | projeto Supabase `gestao-rural-homologacao`, compartilhado com a homologação (T-06, aprovada em 26/10/2026) | sem banco de DEV separado por integrante nesta entrega (decisão T-06, seção 13.2). Antes de 26/10/2026: "PostgreSQL local ou projeto Supabase de desenvolvimento (a definir)" |
| Testes automatizados | local, `manage.py test`     | PostgreSQL local de cada desenvolvedor (`DB_TEST_*`), bancos descartáveis `test_*` (T-06) | **implementado** na GR-34 (`config/banco_de_teste.py`); validado em 26/10/2026 no ambiente de Pedro Simon; ambiente de Gustavo Lopes não validado |
| Homologação     | `develop` (homologação local; Render de homologação não definido) | projeto Supabase `gestao-rural-homologacao` (São Paulo) | **projeto criado** (Pedro Simon); conexão configurada na branch da GR-33 e validada localmente. Não há serviço Render de homologação comprovado. Antes de 24/10/2026: "Render QA / `qa`" (HISTÓRICO; `qa` excluída) |
| Produção        | Render / `main`                  | projeto Supabase de produção independente, com credenciais próprias (T-06) | **não existe** (a criar); Render sem as variáveis `DB_*` (GR-20) |

Requisitos para a implementação:

- credenciais independentes por ambiente, cadastradas no painel do Render e no `.env` local, **nunca** no repositório;
- escolher o modo de conexão: conexão direta ou *connection pooler* do Supabase. Verificar se o Render alcança o endereço escolhido. **Escolhido (GR-33):** Session Pooler (Supavisor, modo *session*, porta 5432), compatível com IPv4; o alcance a partir do Render ainda **não foi validado**;
- se for usado o pooler em modo *transaction*, validar o comportamento de *prepared statements* do Psycopg 3 com o Django. **Não se aplica** ao modo *session* escolhido, compatível com *prepared statements*;
- definir a região do banco e verificar a latência com o Render. **Região:** São Paulo; latência com o Render não medida.

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
| Compatibilidade do Psycopg 3 com Python 3.14 e Django 6.1 no Render           | validado localmente (`psycopg[binary]==3.3.6`); build no Render a validar |
| Conectividade Render → Supabase (modo de conexão, rede, TLS)                  | a validar (modo escolhido: Session Pooler com TLS) |
| Publicar a GR-33 sem as variáveis `DB_*` no Render                            | o Django **não inicia** (falha intencional na carga do settings); configurar o Render (GR-20) antes de publicar |
| TLS em `require` criptografa mas não valida o certificado do servidor         | aceito por ora; `verify-ca`/`verify-full` com `DB_SSLROOTCERT` disponíveis |
| Limites e pausa por inatividade do plano gratuito do Supabase, somados à suspensão do Render Free | a confirmar nas regras vigentes do plano |
| Worker único do Gunicorn e chamadas longas ao Gemini mantendo conexões abertas | mitigado: `CONN_MAX_AGE = 0` (conexão por requisição) pelo limite de conexões do Session Pooler |
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

| ID     | Pendência                                                                      | Situação (25/10/2026, branch da GR-33) |
| ------ | ------------------------------------------------------------------------------ | -------------------------------------- |
| ADR1-P1 | Criar os projetos/bancos Supabase por ambiente (quem cria e quem tem acesso: a definir) | **PARCIAL**: só o projeto de homologação existe (Pedro Simon). T-06 aprovada em 26/10/2026 (seção 13.2): DEV usa o projeto de homologação; testes no PostgreSQL local; projeto de produção ainda a criar |
| ADR1-P2 | Validar Psycopg 3 (versão, instalação no Render, Python 3.14)                 | **PARCIAL**: `psycopg[binary]==3.3.6` validado localmente; build no Render não validado |
| ADR1-P3 | Definir os nomes das variáveis de conexão e o formato de configuração em `settings.py` | **RESOLVIDA**: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`, `DB_SSLROOTCERT`, `DB_CONNECT_TIMEOUT` (seção 13.1) |
| ADR1-P4 | Escolher conexão direta ou pooler, com os parâmetros correspondentes          | **RESOLVIDA**: Session Pooler, modo *session*, porta 5432, TLS obrigatório |
| ADR1-P5 | Modelar as entidades da Etapa 2 (fase posterior; não faz parte deste ADR)     | pendente (GR-34/GR-35+) |
| ADR1-P6 | Incluir `migrate` na publicação                                                | **SUBSTITUÍDA** em 26/10/2026 (PT-06, seção 13.2): migrations manuais; `build.sh` e `start.sh` sem `migrate`, verificado por teste |
| ADR1-P7 | Substituir os testes que proíbem banco                                         | em andamento na GR-33 (testes de configuração); testes com banco: pendente |
| ADR1-P8 | Atualizar `.env.example` (somente nomes) e o painel do Render                  | **PARCIAL**: `.env.example` atualizado; Render sem as variáveis `DB_*` (GR-20) |

### 13.1 Andamento — GR-33 (conexão configurada)

Estado da branch `feature/gr-33-configurar-supabase` em 25/10/2026, ainda **não integrada** a `develop`:

- `DATABASES["default"]` usa `django.db.backends.postgresql` com Psycopg 3 (`psycopg[binary]==3.3.6`).
- Supabase usado **somente como PostgreSQL**: Data API desativada; sem Auth e sem Storage; o navegador não acessa o banco.
- Conexão pelo **Session Pooler** (Supavisor, modo *session*, porta 5432): compatível com IPv4 e com *prepared statements*. Projeto `gestao-rural-homologacao`, região São Paulo — o **único** projeto Supabase existente.
- Variáveis (somente nomes; valores fora do Git):

  | Variável             | Uso                                                                 |
  | -------------------- | ------------------------------------------------------------------- |
  | `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | obrigatórias; ausentes ou vazias → `ImproperlyConfigured` na carga do settings, sem banco substituto |
  | `DB_PORT`            | opcional; padrão 5432                                               |
  | `DB_SSLMODE`         | opcional; padrão `require`; aceita só `require`, `verify-ca`, `verify-full` |
  | `DB_SSLROOTCERT`     | opcional; certificado da CA do Supabase, necessário para `verify-ca`/`verify-full` |
  | `DB_CONNECT_TIMEOUT` | opcional; padrão 10 s                                               |

- `CONN_MAX_AGE = 0`: conexão por requisição, pelo limite de conexões do Session Pooler e pelas requisições longas ao Gemini.
- Limitação: `require` criptografa, mas não valida o certificado do servidor.
- Validação da conexão pelo Django ORM: validada em 25/10/2026 na branch `feature/gr-33-configurar-supabase`: `SELECT 1` pelo Django ORM (`connection.cursor()`) no projeto de homologação retornou `1`, PostgreSQL 17, porta 5432, `sslmode=require` e TLS ativo na sessão; somente leitura, nenhum dado ou tabela alterado.
- Fora da GR-33: models e migrations (GR-34/GR-35+), `migrate` na publicação e variáveis no Render (GR-20).

### 13.2 Decisões T-06 e PT-06 (GR-34, aprovadas em 26/10/2026)

Aprovadas em conjunto por Pedro Simon e Gustavo Lopes em 26/10/2026. Na aprovação, PT-06 foi chamada de "P06"; não confundir com o pacote P06 do [plano](../organizacao/Plano_Responsabilidades_N2_Etapa2.md) (interface de conferência).

**T-06 — bancos por ambiente: APROVADA**

| Ambiente | Decisão | Situação em 26/10/2026 |
| -------- | ------- | ---------------------- |
| TEST | Cada desenvolvedor usa o próprio PostgreSQL local. Os testes com banco usam exclusivamente `DB_TEST_*`, pelo executor `config/banco_de_teste.py`, com bancos descartáveis de prefixo `test_`. Nenhum teste automatizado cria, modifica ou exclui bancos de homologação ou produção | **implementado** na GR-34 (branch `feature/gr-34-testes-migrations`, não integrada). Validado no ambiente de Pedro Simon; **não validado** no de Gustavo Lopes |
| DEV + QA | Pedro e Gustavo usam o projeto Supabase `gestao-rural-homologacao` como banco compartilhado de desenvolvimento e homologação manual. Não há banco de DEV separado por integrante nesta entrega. Alterações de esquema são coordenadas: só um integrante aplica migrations por vez, com conhecimento do outro. Só dados fictícios ou próprios para homologação | o projeto existe (GR-33). Nenhuma migration foi aplicada |
| PROD | Projeto Supabase independente, com credenciais próprias, sem reutilizar as de homologação. Nenhuma alteração em produção sem validação e autorização | **não existe** (a criar); Render sem `DB_*` (GR-20) |

**PT-06 — migrations manuais e controladas: APROVADA**

`migrate` **não** entra em `build.sh` nem em `start.sh`; a ausência é verificada por `config/test_producao.py`. Fluxo aprovado:

1. Criar ou modificar os models.
2. Gerar as migrations versionadas com o Django (`makemigrations`).
3. Revisar as migrations.
4. Validar no PostgreSQL local de testes.
5. Aplicar manualmente em homologação, após confirmar o destino e coordenar com a equipe.
6. Homologar a funcionalidade.
7. Aplicar manualmente em produção somente após autorização, preparação do banco e verificação da recuperação.
8. Publicar a aplicação pelo fluxo Git aprovado ([`ContextoFluxoGit.md`](../../ContextoFluxoGit.md)).

Até 26/10/2026 nenhuma migration existe e nenhuma foi aplicada em qualquer banco.

**Validação do ambiente TEST (26/10/2026, ambiente de Pedro Simon):** PostgreSQL local 18.6 via `127.0.0.1`. O banco descartável `test_gestao_rural` foi criado, consultado (`SELECT 1` retornou `1`) e removido, e não existia depois da execução. A consulta usou um `TestCase` temporário, fora da suíte versionada. Resultados: suíte versionada `Ran 312 tests — OK`; combinada com o `TestCase` temporário, `Ran 313 tests — OK`. O Supabase não foi usado pelos testes. Pendente: a mesma validação no ambiente de Gustavo Lopes.

## 14. Critérios futuros de validação

A decisão só passa para **IMPLEMENTADO** quando houver evidência de que:

1. `python manage.py check` passa com a conexão configurada;
2. `python manage.py migrate`, executado manualmente conforme PT-06 (seção 13.2), aplica as migrations no banco Supabase do ambiente;
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
