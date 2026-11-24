# Auditoria do projeto — 24/11/2026

Referência: `5f19ce0` (`origin/develop`, PR #57). `origin/main` está em `c3d4239`
(PR #58, 27/10/2026), com **árvore idêntica** à da `develop` (`git diff` vazio).
Branch de trabalho: `docs/auditoria-24-11`, sem alterações de código.

Esta auditoria sucede a [GR-16](../organizacao/GR-16-auditoria-aaa80cc.md)
(27/10/2026, `aaa80cc`). A diferença entre `aaa80cc` e `5f19ce0` é só
documentação; os resultados de código da GR-16 continuam válidos e foram
reconfirmados abaixo.

## 1. Método e limites

- Leitura de `config/`, `usuarios/`, `agents/gemini_client.py`, `documentos/`
  (views, upload, análises), `cadastros/views*.py`, `financeiro/` (serviços,
  lançamento, modelos) e dos documentos em `docs/`.
- Execução local: `manage.py check`, `check --deploy`,
  `makemigrations --check --dry-run`, suíte completa, `pip check`,
  `pip list --outdated`, `git diff --check`, varredura de padrões de segredo.
- Pesquisa pública: avisos de segurança do Django 6.1.2 e 6.1.3.
- **Não** foram lidos `.env` nem `README.txt`. `DB_HOST` foi substituído por
  `host.invalid` no processo, e nenhum banco remoto foi acessado. Os testes
  usaram só o PostgreSQL local de `DB_TEST_*`.
- **Não** foram feitos: teste em navegador, Gemini real, `pip-audit`, medição de
  cobertura, acesso a Supabase, Render, Jira ou Classroom.

## 2. Resultados verificados

| Verificação | Resultado |
| --- | --- |
| `manage.py check` | sem problemas |
| `manage.py test` | **1.153 testes, OK** (24 s); banco descartável criado e destruído pelo runner |
| `makemigrations --check --dry-run` | `No changes detected` (aviso esperado do host fictício) |
| `check --deploy` (`DEBUG=False`) | W004 (HSTS) e W008 (redirecionamento HTTPS); W020 apareceu só porque o ambiente da execução não tinha hosts |
| `pip check` | sem requisitos quebrados |
| `git diff --check` | limpo |
| Varredura de segredos (chaves Gemini, URLs com senha, `password =`) | nenhuma ocorrência fora de testes |
| Arquivos sensíveis versionados (`.env`, `README.txt`, PDFs, logs, SQLite) | nenhum |

Tamanho: ~7,4 mil linhas de código de aplicação e ~14,9 mil de testes.
Por aplicação (código/teste): `agents` 981/2.000, `cadastros` 1.625/2.503,
`config` 403/686, `documentos` 2.311/4.683, `financeiro` 1.889/4.519,
`usuarios` 201/554.

## 3. Pontos fortes confirmados no código

- **Todas as 21 rotas de negócio** têm `@demo_login_required`; as de escrita
  exigem POST e CSRF. Só `/login/` e `/logout/` são públicas.
- `RespostasPrivadasMiddleware` aplica `no-store` a toda resposta dinâmica.
- Upload só em memória, com limite pelos bytes realmente recebidos
  (`documentos/uploads.py`); nada vai a disco.
- Chave Gemini só na requisição, sem fallback para variável de ambiente
  (`api_key` e `vertexai=False` explícitos); `sensitive_variables` e
  `sensitive_post_parameters` nas views que a tocam; logs com texto fixo.
- Comparação de login em tempo constante e sem curto-circuito.
- `settings.py` recusa iniciar sem `DB_*`, exige TLS (`require`+) e não tem
  banco substituto. O runner de testes recusa host remoto, nome sem `test_`
  e igual a `DB_NAME`.
- Dinheiro: `registrar_movimento` em transação única, `select_for_update`,
  idempotência por `analise_origem_id`/`chave_idempotencia` com índice único,
  `CheckConstraint`s e gatilho diferido que confere a soma das parcelas no
  COMMIT. Modelos financeiros recusam `update`/`delete` diretos
  (`on_delete=PROTECT`).
- Duas confirmações simultâneas da mesma nota não duplicam movimento.

## 4. Achados

Severidade: **A** = tratar antes de publicar/entregar; **M** = importante;
**B** = melhoria.

### A-01 — Django 6.1.1 sem as correções de segurança 6.1.2 e 6.1.3 (A)

`requirements.txt` fixa `Django==6.1.1`. Foram publicadas duas versões de
segurança depois dela (6.1.2 em 06/10/2026 e 6.1.3 em 03/11/2026). `pip` já
lista 6.1.3 como disponível. Relevância para este projeto:

| CVE | Gravidade | Atinge o projeto? |
| --- | --- | --- |
| CVE-2026-84429 (DoS por parsing de cabeçalho HTTP) | moderada | **Provável**: o parsing de `Content-Type` ocorre em todo POST, inclusive o de `/login/` sem sessão |
| CVE-2026-108147 (memória em upload multipart `base64`) | baixa | **Provável**: o POST de PDF passa pelo `MultiPartParser` (o CSRF lê o corpo antes do login) |
| CVE-2026-77050 (DoS por códigos de idioma longos) | baixa | Improvável: não há `LocaleMiddleware` |
| CVE-2026-87975 (model formsets com PK editável) | moderada | Não: não há `ModelFormSet` |
| CVE-2026-113593 (cache com `Vary` vazio) | baixa | Não: sem `cache_page`/`UpdateCacheMiddleware` |
| CVE-2026-87890, 111211, 111362, 113373, 114582 (GIS/admin) | baixa/moderada | Não: sem GIS nem admin |

Sem `pip-audit` não há cobertura das demais dependências. `certifi`
(2026.7.22 → 2026.11.20), `cryptography` (50.0.1 → 50.0.2) e `google-auth` também
têm versão nova; o `google-genai` 2.24.0 → 3.6.1 é mudança de versão maior e
precisa de teste dos Agents antes de adotar.
**Ação:** atualizar para `Django==6.1.3`, reexecutar a suíte e republicar.
Não foi alterado nesta tarefa (dependências exigem autorização, e o deploy é
humano).

### M-01 — Login sem limite de tentativas e sessão de 14 dias (M)

`usuarios/views.py` não limita tentativas. `SESSION_COOKIE_AGE` não está
definido, então vale o padrão do Django (14 dias). O cookie é assinado e sem
revogação no servidor, e o login é compartilhado (limites já documentados na
GR-16). Todo o sistema, com CPF/CNPJ e dados financeiros, fica atrás de uma
senha única. **Ação:** reduzir `SESSION_COOKIE_AGE` (por exemplo, 8 h) e adotar
limite por IP/janela; ao menos exigir senha longa em `DEMO_PASSWORD`.

### M-02 — HSTS e redirecionamento HTTPS dependem só do proxy (M)

`SECURE_HSTS_SECONDS` e `SECURE_SSL_REDIRECT` não estão no código (W004/W008).
A decisão de deixá-los com a plataforma está registrada, mas não há evidência de
que o Render os aplique à URL pública. Sem isso, um acesso inicial por HTTP não é
forçado para HTTPS. Os cookies de sessão e CSRF são `Secure`, o que atenua o
vazamento. **Ação:** verificar na URL publicada e registrar a evidência.

### M-03 — Telas de `cadastros` sem tratamento de falha do banco (M)

`financeiro/views_*` e `documentos/views*` convertem `DatabaseError` em
mensagem amigável. `cadastros/views.py` e `cadastros/views_classificacoes.py`
capturam só `ValidationError`/`IntegrityError`. Com o Supabase indisponível
(Session Pooler, timeout de 10 s), listagem, edição e inativação de pessoas e
classificações respondem 500. Também não há `404.html`/`500.html`, então o erro
mostra a página padrão e seca do Django. **Ação:** decorador equivalente ao
`_erros_de_banco` do financeiro e templates de erro em português.

### M-04 — Capacidade: um worker síncrono com chamadas de minutos (M)

`start.sh` usa `WEB_CONCURRENCY` padrão 1 e `GUNICORN_TIMEOUT` 420 s. Cada
processamento de PDF chama o Gemini duas vezes em sequência (até 60 s × 3
tentativas por chamada). Enquanto um PDF processa, o único worker não atende
ninguém, nem o login. Aceitável para demonstração com um usuário; fraco para
uso real. **Ação:** definir `WEB_CONCURRENCY` ≥ 2 no Render (variável, sem
mudar código) ou avaliar workers com threads; documentar o limite.

### M-05 — F-6 e GR-39/49 continuam abertas (M)

Sem mudança desde a GR-16: o serviço `salvar_cadastro_pendente()` não é
idempotente (duas chamadas iguais criam duas pessoas) e a manutenção/histórico
de parcelas não existe. O botão F-6 não está ligado. Ver
[F6](../contratos/F6-idempotencia-alinhamento.md). A GR-49 aparece como
concluída no Jira e continua parcial no código (divergência registrada na GR-16).

### M-06 — Proteção do esquema no Supabase não verificável pelo repositório (M)

As migrations não habilitam Row Level Security. A proteção contra acesso por
fora do Django depende de a **Data API do Supabase estar desativada**, como diz o
`ContextoProjeto.md` (seção 15.1.1). Isso não é verificável no código. Se estiver
ativa, tabelas de `public` com CPF/CNPJ e valores ficam expostas pela chave anon.
**Ação (humana):** conferir no painel de QA e PROD e registrar a evidência. Por
precaução, habilitar RLS sem políticas nas tabelas.

### B-01 — Documentação defasada ou inconsistente (B)

- `docs/INDICE.md`: cabeçalho, estado da documentação e linhas do `ContextoProjeto.md`,
  do ADR e do código estavam defasados (GR-33 "não integrada", Fase 2 "em revisão
  local", referência `f7786e8`). Atualizados nesta tarefa, com a seção 12 nova.
- `docs/arquitetura/ADR-001-supabase.md`: contexto e seção de implementação
  ainda falam em `DATABASES = {}` e branch GR-33 "não integrada".
- `docs/requisitos/matriz-n2-etapa2.md` (linha ~168) mantém a nota de
  25/10 "não integrada".
- `README.md` e GR-16 citam `aaa80cc` e "`origin/main` observado em `f7786e8`";
  hoje `main` = `c3d4239`. O prazo "27/10/2026" já passou.
- `ContextoProjeto.md`: a numeração está fora de ordem (seção 35 antes de
  34.16–34.25; 36 ao final); a seção 15.1 ainda diz que o estado da Etapa 1 "é
  o estado da `main`", e `main` já recebeu a `develop` (PR #58).
- `AGENTS.md` (local) ainda descreve a versão como stateless
  (`DATABASES = {}`).
- `config/test_sem_banco.py` mantém o nome da Etapa 1 embora hoje teste
  garantias estruturais com banco.

### B-02 — Sem CI e sem medição de cobertura (B)

Não há `.github/workflows`. A suíte (1.153 testes) só roda localmente, e exige
PostgreSQL local. Não há `coverage`/lint no repositório (`ruff`/`pyflakes` não
instalados). **Ação:** workflow com serviço PostgreSQL rodando
`check`, `makemigrations --check` e `test`; avaliar `ruff`.

### B-03 — Dados pessoais e envio a terceiro (B)

CPF/CNPJ ficam em texto simples (`Pessoa.documento`, `NotaFiscalLancada.emitente_cnpj`),
coerente com a decisão de 24/10 mas relevante para a LGPD; e o PDF da nota é
enviado ao Gemini com a chave do usuário. Não há aviso de privacidade nem
registro de base legal/retenção no repositório (o consentimento aparece só no
fluxo F-6, ainda desconectado). **Ação:** registrar a decisão de privacidade
(campo `documento` em texto, retenção, terceiro) em ADR ou no README.

### B-04 — Limpeza das análises sem agendamento (B)

Continua como na GR-16: `expirar_analises` existe, mas ninguém o executa
periodicamente. O acesso expira em 30 minutos; os dados de análises abandonadas
ficam no banco até a próxima limpeza oportunista. Ligado à GR-50.

### B-05 — Diversos (B)

- `requirements.txt` fixa versões, mas sem hashes e sem arquivo de
  constraints; `requirements.txt` não termina com quebra de linha.
- Sem `LOGGING` configurado: os `logger.warning` dependem da configuração
  padrão do Django/Gunicorn.
- Sem cabeçalho CSP; as telas usam CSS/JS locais, então é viável adotar um CSP
  restritivo.
- `media/` e `uploads/` existem localmente (ignorados, vazios) embora o
  aplicativo não grave arquivos.
- `AnaliseTemporaria.md` na raiz está ignorado pelo Git (rascunho local).
- O comentário de `settings.py` ("MVP da N2 - Etapa 1 sem banco de dados…")
  contradiz o próprio arquivo.

## 5. Pendências herdadas da GR-16 (sem evidência nova)

Estado das migrations em QA/PROD (inclusive `financeiro/0004`), SHA publicado
versus rodapé, URL/HTTPS, teste em navegador, canal restrito do `Readme.txt` e
envio ao Classroom. Nenhuma foi verificada. **Implementado, integrado, validado
localmente, homologado e publicado continuam sendo estados distintos.**

## 6. Ações recomendadas, em ordem

1. Atualizar para Django 6.1.3, rodar a suíte e liberar pelo fluxo
   `feature/fix` → `develop` → `main` (A-01).
2. Definir `SESSION_COOKIE_AGE` e limitar tentativas de login (M-01).
3. Conferir Data API/RLS no Supabase e HSTS/HTTPS no Render, com evidência
   (M-06, M-02).
4. Tratar `DatabaseError` e criar `404.html`/`500.html` em `cadastros` (M-03).
5. Subir `WEB_CONCURRENCY` no Render (M-04).
6. Fechar F-6 e GR-39 com Simon; agendar `expirar_analises` (M-05, B-04).
7. Corrigir a documentação defasada (B-01) e criar CI (B-02).
