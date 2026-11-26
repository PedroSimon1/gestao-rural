# 09 — Segurança e privacidade

O repositório é **público**. O sistema trata **CPF/CNPJ, nomes e valores financeiros** e envia o PDF da nota a um terceiro (Google Gemini).
Esta seção descreve os controles que existem no código, os limites conhecidos e as regras para quem altera o sistema.

## 1. Regras absolutas para quem mexe no projeto

- **Nunca** exibir, copiar, registrar, versionar ou enviar a ferramentas externas: senhas, tokens, chaves de API, strings de conexão,
  credenciais PostgreSQL/Supabase, valores do `.env` ou dados pessoais e financeiros reais.
- Na documentação e no código de exemplo, use só **nomes** de variáveis e **dados fictícios**.
- Arquivos que **não** podem ir ao Git: `.env`; o `Readme.txt` da entrega acadêmica (login, senha, chave de LLM; ignorado em qualquer combinação de maiúsculas); `staticfiles/`, `media/`, `uploads/`.
- Não use dados reais do cliente em testes.
- Não ponha credenciais de produção em `.env.example`.
- Antes de concluir uma tarefa, revise os arquivos alterados à procura de segredos expostos por acidente.

## 2. Controles implementados

### 2.1 Autenticação e sessão

| Controle | Detalhe | Onde |
| --- | --- | --- |
| Login de demonstração | Um par `DEMO_LOGIN`/`DEMO_PASSWORD` do ambiente; sem configuração, **todo acesso é recusado**, mesmo com sessão antiga | `usuarios/demo.py` |
| Comparação em tempo constante | `constant_time_compare` para login e senha, combinados com `&` (as duas comparações sempre ocorrem) | `usuarios/demo.py` |
| Todas as rotas de negócio exigem login | `@demo_login_required` nas 21 rotas; só `/login/` e `/logout/` são públicas | `*/views*.py` |
| Logout só por POST | GET apenas mostra a confirmação (não cancela análises por link externo ou *prefetch*) | `usuarios/views.py` |
| Sessão em **cookie assinado** | `signed_cookies`; guarda `demo_autenticado` e um código aleatório de análises; assinado com `DJANGO_SECRET_KEY` (**não criptografado**); `HttpOnly`; `Secure` com `DEBUG=False`; `SameSite=Lax` | `config/settings.py` |
| Login/logout descartam análises | O login troca o código e cancela as pendentes do anterior; o logout cancela as da sessão antes do `flush` | `usuarios/demo.py` |

### 2.2 Requisições

| Controle | Detalhe |
| --- | --- |
| **CSRF** | Middleware + `{% csrf_token %}`; `CSRF_TRUSTED_ORIGINS` por ambiente |
| **Hosts** | `ALLOWED_HOSTS` por ambiente; `RENDER_EXTERNAL_HOSTNAME` entra sozinho (e a origem `https://` em CSRF) |
| **HTTPS atrás do proxy** | `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`; cookies de sessão e CSRF `Secure` quando `DEBUG=False` |
| **Clickjacking** | `XFrameOptionsMiddleware` |
| **XSS** | Autoescape do Django; sem `|safe` nas telas |
| **Sem cache de respostas dinâmicas** | `RespostasPrivadasMiddleware` aplica `no-store`/`no-cache` a **toda** resposta dinâmica (inclusive redirects e erros); o WhiteNoise atende os estáticos antes |
| **Métodos** | `@require_http_methods`/`@require_POST` em todas as views; escrita só por POST |
| **Campos inesperados** | As views de escrita recusam campos fora do formulário e campos repetidos |

### 2.3 Chave Gemini e processamento

| Controle | Detalhe | Onde |
| --- | --- | --- |
| A chave vive só na requisição | Digitada a cada processamento; `PasswordInput` sem `render_value` (nunca volta no HTML); `autocomplete="off"`; ≤ 256 caracteres; **não** vai a sessão, banco, contexto de template, JSON nem log | `documentos/forms.py`, `processamento.py` |
| Sem fallback de ambiente | `api_key` e `vertexai=False` explícitos | `agents/gemini_client.py` |
| Relatórios de erro | `@sensitive_post_parameters` e `@sensitive_variables` nas views/funções que tocam senha ou chave | `documentos/views*.py`, `processamento.py`, `gemini_client.py` |
| Logs com texto fixo | Só código de erro, nome do campo, tipo de exceção, modelo e status HTTP; **nunca** a exceção original, o texto do PDF, o JSON ou a chave | `processamento._erro`, Agents |
| Mensagens ao usuário | Fixas por código; sem etapa, traceback, status da API ou resposta bruta | `ProcessamentoError` |
| Prompt injection | O Extrator manda ignorar instruções escritas no PDF; saídas restritas por schema/Enum | `agents/extrator/agent.py` |
| Minimização de dados enviados | O Classificador **não recebe** CPF/CNPJ nem dados do faturado | `agents/classificador/agent.py` |

### 2.4 Upload

- **Só em memória**: `PDFEmMemoriaUploadHandler` conta os **bytes realmente recebidos** (não o `Content-Length`) e interrompe acima de `MAX_PDF_UPLOAD_SIZE_MB` (padrão 10); **nada é gravado em disco** (sem `TemporaryFileUploadHandler`).
- Validação em ordem: extensão → tamanho → `content_type` → assinatura `%PDF-` → nome sanitizado (só exibição).

### 2.5 Dados da nota (análise pendente)

- O JSON fica no servidor, em `AnalisePendente`, por **30 minutos**; o banco guarda só o **hash SHA-256** do código da sessão.
- Outra sessão recebe "análise não encontrada", sem revelar se a análise existe.
- Ao confirmar, cancelar ou expirar, `dados` e `correcoes` são **apagados**; ficam só estado, datas e **nomes** dos campos corrigidos. Constraints do banco impedem estado final com dados.
- Tamanho máximo dos dados/correções: **256 KiB**.
- Erros de correção citam o **nome do campo**, nunca o valor.

### 2.6 Banco e integridade

| Controle | Detalhe |
| --- | --- |
| Credenciais só do ambiente | `settings.py` **recusa iniciar** sem `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`; sem banco substituto |
| **TLS obrigatório** | `DB_SSLMODE` ∈ `require`, `verify-ca`, `verify-full` (padrão `require`); modos sem criptografia são recusados |
| Testes isolados | O executor de testes só aceita PostgreSQL **local** (`DB_TEST_*`), banco com prefixo `test_` e diferente de `DB_NAME`; recusa variáveis do libpq que redirecionariam a conexão |
| Escrita financeira protegida | Sem exclusão/alteração direta de campos essenciais; transação única; `select_for_update`; índices únicos; gatilho diferido (ver [06](06-modelo-de-dados.md)) |
| Mascaramento | CPF aparece como `*******` + 4 últimos dígitos em `__str__`, logs e erros |

### 2.7 Proteções contra falhas de repetição

Reenvio, duplo clique ou duas abas **não duplicam** lançamentos (idempotência por `analise_origem_id` e `chave_idempotencia`); o JavaScript só reduz o duplo clique visualmente, a garantia é do servidor.

## 3. Dados pessoais (LGPD)

| Dado | Onde fica | Observação |
| --- | --- | --- |
| CPF/CNPJ de pessoas | `pessoas.documento` em **texto simples** | Decisão da equipe (24/10/2026); relevante para a LGPD |
| CNPJ do emitente de notas | `notas_fiscais_lancadas.emitente_cnpj` em texto simples | idem |
| JSON da nota (temporário) | `analises_pendentes.dados` por até 30 min | Apagado ao finalizar; **backups/WAL do provedor não são controlados** por esses mecanismos |
| PDF da nota | **Enviado ao Gemini** com a chave do usuário | Terceiro; **não há aviso de privacidade** nem registro de base legal/retenção no repositório |
| Chave Gemini | Em memória, só na requisição | Nunca persistida |

Não há ADR/README com a decisão de privacidade (campo `documento` em texto, retenção, terceiro) — pendência B-03 da auditoria.

## 4. Limites e riscos conhecidos

Ver também [12](12-pendencias-e-riscos.md). Itens de segurança abertos:

| Nível | Risco | Detalhe |
| --- | --- | --- |
| Alto | **1 worker síncrono** | Um processamento de até ≈ 7 min bloqueia o serviço (inclusive o login) |
| Médio | **Login compartilhado**: o sistema inteiro fica atrás de uma senha única. Mitigado: 5 falhas por origem e 30 no total em 15 minutos bloqueiam o login (cache em memória por worker, ver `usuarios/limite.py`); sessão de 8 horas (`SESSION_COOKIE_AGE`); `check --deploy` avisa senha com menos de 12 caracteres | Limites por worker; o teto global permite bloquear o login legítimo na janela |
| Médio | **Cookie assinado sem revogação**: uma cópia feita antes do logout autentica até expirar e pode criar análises novas com o mesmo código | O logout só cancela as análises pendentes existentes |
| Médio | **HSTS e redirecionamento HTTPS não estão no código** (`check --deploy` W004/W008) | Dependem do Render; **sem evidência** de que a URL pública os aplica |
| Médio | **Row Level Security não habilitada** nas migrations | A proteção contra acesso por fora do Django depende de a **Data API do Supabase estar desativada** (não verificável pelo repositório) |
| Médio | **Limpeza das análises sem agendamento** | `expirar_analises` existe, mas ninguém o executa periodicamente |
| Baixo | `LOGGING` configurado (5xx no console, sem a mensagem da exceção); sem cabeçalho CSP (as telas usam CSS/JS locais, então um CSP restritivo é viável); validação de PDF superficial (assinatura `%PDF-`) | |
| Baixo | Dependências: `google-genai` 2.24.0 → 3.x é mudança de versão **maior** e precisa de teste dos Agents antes de adotar; sem `pip-audit` nem hashes em `requirements.txt` | |

## 5. Checklist de segurança para uma mudança

- [ ] Nova rota: tem `@demo_login_required`? Escrita só por POST + CSRF? Recusa campos extras/repetidos?
- [ ] Nova entrada de formulário com dado sensível: `@sensitive_post_parameters`? Sem `render_value`?
- [ ] Novo log ou mensagem de erro: só texto fixo e códigos? Sem valores, documentos, chave, texto do PDF?
- [ ] Novo dado pessoal persistido: precisa ser guardado? Por quanto tempo? Está mascarado onde é exibido?
- [ ] Nova chamada externa: que dados saem? (minimizar)
- [ ] Nova resposta dinâmica: o middleware de privacidade a cobre? (cobre toda resposta dinâmica)
- [ ] Nova variável de ambiente: documentada só pelo **nome**; sem valor no repositório?
- [ ] Teste com dado real? **Não.** Use dados fictícios.
