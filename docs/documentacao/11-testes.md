# 11 — Testes

Framework: `unittest` do Django (`SimpleTestCase`, `TestCase`, `TransactionTestCase`). **Sem pytest e sem medição de cobertura** no repositório; o CI (`.github/workflows/ci.yml`) roda a suíte em PR e push para `develop` e `main`.

## 1. Números de referência

Auditoria de 24/11/2026: **1.153 testes, todos aprovados** (≈ 24 s) no PostgreSQL local de `DB_TEST_*`. Isso é **referência histórica**, não garantia atual:
rode a suíte antes de afirmar qualquer coisa.

| App | Funções `def test…` (contagem por leitura do código) |
| --- | ---: |
| `documentos` | 344 |
| `financeiro` | 342 |
| `cadastros` | 205 |
| `agents` | 159 |
| `config` | 52 |
| `usuarios` | 51 |
| **Total** | **1.153** |

Tamanho aproximado (auditoria): ~7,4 mil linhas de código de aplicação e ~14,9 mil de testes.

## 2. Executor de testes (`config/banco_de_teste.py`)

Os testes com banco **nunca** usam `DB_*` (que podem apontar para o Supabase). O `ExecutorDeTestes`:

- exige `DB_TEST_HOST`, `DB_TEST_NAME` e `DB_TEST_USER`;
- aceita **somente host local** (`localhost`, `127.0.0.1`, `::1` ou o diretório do socket Unix; vírgula e espaço recusados);
- exige que o nome comece com **`test_`** e seja **diferente de `DB_NAME`**;
- recusa variáveis do libpq que redirecionariam a conexão (`PGHOSTADDR`, `PGSERVICE`, `PGSERVICEFILE`);
- troca a conexão **antes** de qualquer chamada de preparação de banco, inclusive quando `setup_databases()` é chamado sem aliases (cenário que já criou um banco de teste no servidor de `DB_*` num script auxiliar);
- usa `sslmode=prefer` no loopback; o banco descartável é **criado e apagado** a cada execução;
- **não há SQLite nem banco substituto**: sem configuração válida, a execução para antes de abrir qualquer conexão.

O papel PostgreSQL local precisa de `LOGIN` e `CREATEDB` (sem superusuário).

## 3. Como rodar

```bash
DJANGO_DEBUG=True python manage.py test                          # tudo
DJANGO_DEBUG=True python manage.py test financeiro               # um app
DJANGO_DEBUG=True python manage.py test financeiro.test_manual   # um módulo
python manage.py check
DB_HOST=db-teste.invalid python manage.py makemigrations --check --dry-run
git diff --check
```

> **`DJANGO_DEBUG=True` é necessário** para a suíte. Com `DEBUG=False` o `settings.py` usa o storage de estáticos com manifesto, e as telas falham
> com "Missing staticfiles manifest entry" (já ocorreu como falso alarme numa auditoria, por um `DJANGO_DEBUG=False` esquecido no *shell*).

Rode os testes dos componentes alterados; rode a **suíte completa** quando a mudança afetar integração ou contratos compartilhados
(serviços financeiros, análises, Agents, modelos).

## 4. Organização

Os testes ficam **ao lado do código**, em `test_*.py` (e `usuarios/tests.py`).

| Área | Arquivos principais | O que cobrem |
| --- | --- | --- |
| Agents | `agents/test_gemini_client.py`, `extrator/test_*.py`, `classificador/test_*.py` | Cliente (chave, timeout, erros), schemas v1/v2, CPF/CNPJ/DV, prompts, erros seguros. **SDK simulado** |
| Processamento e contratos | `documentos/test_processamento.py`, `test_contrato_agents.py`, `test_fiscal_v2.py`, `test_integracao_final.py` | `processar_pdf`, `montar_resultado`, composição Extrator + Classificador, inconclusiva |
| Análises | `documentos/test_analises.py`, `test_correcoes.py`, `test_privacidade.py` | Ciclo de vida, dono por sessão, expiração, correções, versão otimista, apagamento de dados |
| Conferência/confirmação | `test_conferencia.py`, `test_interface_conferencia.py`, `test_fluxo_conferencia.py`, `test_classificacao_na_conferencia.py`, `test_classificacao_pendente.py`, `test_campos_fiscais.py`, `test_interface_consultas.py` | F-3, telas, FLU-07, campos fiscais |
| Telas de documentos | `test_interface.py`, `test_versao_publicada.py` | Upload, mensagens, SHA no rodapé |
| Cadastros | `cadastros/test_models.py`, `test_classificacao.py`, `test_consultas.py`, `test_resolucao.py`, `test_pendentes.py`, `test_interface_pessoas.py`, `test_interface_classificacoes.py` | Constraints, imutabilidade, consultas, F-4, F-6, telas |
| Financeiro | `financeiro/test_models.py`, `test_servicos.py`, `test_parcelas.py`, `test_identidade_fiscal.py`, `test_lancamento_nota.py`, `test_lancamento_fiscal.py`, `test_manual.py`, `test_interface_manuais.py`, `test_interface_consultas.py` | Movimento, parcelas, gatilho no COMMIT, identidade fiscal, F-5, contas manuais, concorrência |
| Login | `usuarios/tests.py` | Credenciais, sessão, `demo_login_required`, ciclo das análises |
| Configuração | `config/test_producao.py`, `config/test_sem_banco.py` | Produção (hosts, CSRF, HTTPS, cookies, static) em **subprocessos** com ambiente controlado; garantias estruturais do banco (não guarda PDF, documentos nem chave; testes sem banco não conectam; testes com banco nunca alcançam `DB_*`; sem migrations faltando) |

Apoios: `documentos/testing.py` (`nova_sessao`, `resultado_da_nota` — dados **fictícios** com DV calculado) e `usuarios/testing.py` (`autenticar_demo`, credenciais de teste usadas só com `override_settings`).

Observação: `config/test_sem_banco.py` mantém o nome da Etapa 1, mas hoje testa garantias estruturais **com** banco.

## 5. Convenções para novos testes

- Dados **fictícios**; CPF/CNPJ com DV calculado (`documentos/testing.py` tem exemplos). Nunca dados reais.
- Gemini **sempre simulado**: injete `extrator`/`classificador` em `processar_pdf`, ou simule o SDK. Nenhum teste chama a API real.
- Deterministas e isolados: sem dependência de ordem, relógio real ou rede. Para prazos, passe `agora` explícito quando a função aceitar.
- Teste **comportamento observável** (resultado, erro com `code`, estado no banco), não "fiação".
- Regra nova ⇒ teste que **quebra** se a regra for removida. Inclua os casos de borda (zero, teto, duplicidade, concorrência, repetição, estado inativo).
- Concorrência/transação: use `TransactionTestCase` quando precisar de commits reais (ex.: gatilho diferido no COMMIT, bloqueios de linha).
- Mudou um contrato (mensagem, código, formato)? Atualize os testes **de contrato**; nunca enfraqueça ou apague um teste só para "passar".
- Resultado de teste que você **não** rodou não é resultado: relate o que executou, o que falhou e o que não executou.

## 6. Limites da suíte

- **Não comprova** a precisão da extração/classificação com **PDFs reais** (SDK simulado).
- **Não comprova** deploy, URL pública, HTTPS, migrations remotas nem o estado do Supabase/Render.
- **Sem teste em navegador** (JavaScript de parcelas e travamento de botão não são exercitados por navegador).
- **CI** (`.github/workflows/ci.yml`): `pip check`, **lint** (`ruff check .`, só as regras `F` do pyflakes: import sem uso e nome indefinido; configuração em `ruff.toml`), **`pip-audit`** nas dependências de `requirements.txt`, `check`, `makemigrations --check` e `test` com PostgreSQL do próprio job. `ruff` e `pip-audit` são instalados só no CI, não em `requirements.txt`. Localmente: `pip install ruff pip-audit` (de preferência fora do `.venv` do projeto) e `ruff check .`.
- **Sem cobertura medida.** Um `pip-audit` que passa a falhar costuma ser CVE novo numa dependência: atualize a versão (como foi feito com `certifi` e `pyasn1` em 27/11/2026) e rode a suíte.
