# Gestão Rural — N2 Etapa 2

Projeto acadêmico de Pedro Simon e Gustavo Lopes, ESW424 / UniRV.
Prazo registrado na matriz: **27/10/2026, 23h59**.

Estado auditado: **`develop` `aaa80cc`, após PR #56**, com 1.153 testes OK
no PostgreSQL local de Gustavo. Código integrado não equivale a homologação,
deploy ou entrega no Classroom. O histórico da Etapa 1 permanece na tag
`n2-etapa1-final` e nas revisões anteriores.

## O que funciona no código integrado

| Fluxo | Implementação e limite |
| --- | --- |
| Pessoas e papéis | Cadastro PF/PJ, múltiplos papéis, edição, pesquisa e inativação/reativação independentes; sem exclusão física |
| Classificações | Receita/despesa, pesquisa, criação, edição da descrição e status; tipo/código imutáveis |
| Nota fiscal | PDF → Extrator → Classificador → JSON fiscal v2 → análise por sessão → conferência → correções → confirmação transacional |
| Classificação inconclusiva | Mantém extração para revisão; falhas de API/rede continuam sendo erros |
| FLU-07 | Cadastro explícito de classificação na conferência, preservando rascunho; salvar correções e confirmar continuam separados |
| Contas manuais | Pagar/receber, classificações com uma principal e parcelas; confirmação explícita e UUID idempotente |
| Consultas financeiras | Filtros e detalhes de classificações/parcelas; estados não significam quitação |
| Privacidade | Upload limitado em memória, respostas dinâmicas no-store, logs fixos no erro de processamento e logout por POST/CSRF |

**Pendências reais:** botão de cadastro pendente F-6 aguarda contrato oficial
idempotente; edição/histórico de parcelas e demais ações financeiras dependem
da GR-39 e das regras de manutenção. A GR-49 é parcial. Homologação/publicação,
agendamento da limpeza e entrega no Classroom ainda exigem evidências humanas.

## Arquitetura e contratos

Monólito Django com templates, CSS/JS locais e PostgreSQL. Dois Agents
síncronos usam o SDK Gemini; Pydantic valida suas respostas. A chave Gemini
é informada na tela a cada processamento, sem fallback para chave de ambiente.

O JSON original e as correções ficam separados em `AnalisePendente`, por
30 minutos sem renovação. A sessão assinada guarda apenas metadados aleatórios;
o banco guarda o hash do dono. F-5 revalida e confirma a nota em sua transação.
O formulário manual chama `financeiro.manual.registrar_conta_manual()`.

Identidade fiscal suportada: NF-e 55 e NFC-e 65 com emitente CNPJ; outros
modelos e emitente CPF não são lançados pelo fluxo fiscal atual. Isso não
impede Pessoa PF/PJ em qualquer papel permitido nem contas manuais compatíveis.
V1 armazenada continua válida até o prazo original; não é convertida silenciosamente.

## Instalar e iniciar

Use Python da versão indicada em `.python-version` (3.14.7 nesta base),
PostgreSQL e um banco da aplicação autorizado. Não copie credenciais de outro
integrante. Em um clone novo, no PowerShell:

```powershell
git clone https://github.com/PedroSimon1/gestao-rural.git
cd gestao-rural
git switch develop
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

No Linux/macOS, use `python3 -m venv .venv` e `source .venv/bin/activate`;
copie `.env.example` apenas se ainda não houver `.env`.

Preencha localmente os nomes abaixo. Não publique valores reais.

| Grupo | Variáveis |
| --- | --- |
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Login demo | `DEMO_LOGIN`, `DEMO_PASSWORD` |
| Aplicação / PostgreSQL | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`, `DB_SSLROOTCERT`, `DB_CONNECT_TIMEOUT` |
| TEST local separado | `DB_TEST_HOST`, `DB_TEST_PORT`, `DB_TEST_NAME`, `DB_TEST_USER`, `DB_TEST_PASSWORD`, `DB_TEST_CONNECT_TIMEOUT` |
| Gemini | `GEMINI_MODEL`, `GEMINI_TIMEOUT_SEGUNDOS`, `GEMINI_MAX_TENTATIVAS`; a API Key vem do formulário |
| Limites e publicação | `MAX_PDF_UPLOAD_SIZE_MB`, `GUNICORN_TIMEOUT`, `WEB_CONCURRENCY`, `PORT`, `RENDER_EXTERNAL_HOSTNAME`, `RENDER_GIT_COMMIT` |

`DB_HOST`, `DB_NAME`, `DB_USER` e `DB_PASSWORD` são obrigatórias para iniciar.
A conexão normal exige TLS: `require`, `verify-ca` ou `verify-full`.
O PostgreSQL local validado para TEST não é automaticamente um DEV com TLS.
Para DEV local, prepare um banco próprio e TLS compatível; para DEV/QA
compartilhado, siga o ADR e a coordenação da equipe. Nunca use o banco descartável
dos testes como banco da aplicação.

Após configurar o banco da aplicação e conferir explicitamente o destino:

```powershell
python manage.py check
python manage.py migrate --plan
```

**As migrations existem e são necessárias.** A aplicação local só deve ser
iniciada com seu esquema preparado. Em banco local próprio autorizado, aplicar
`python manage.py migrate`; em QA/PROD, a execução é manual do responsável,
após revisão e autorização. Não execute comandos de aplicação remota como
parte automática deste tutorial.

```powershell
python manage.py runserver 127.0.0.1:8000
```

Abra `http://127.0.0.1:8000/` e use as credenciais demo do seu ambiente.
Em HTTP local, `DJANGO_DEBUG=True` permite cookies locais; publicação usa False.

## Testes e conferência de migrations

```powershell
python manage.py test
```

O executor `config.banco_de_teste.ExecutorDeTestes` exige `DB_TEST_*` local,
banco com prefixo `test_`, distinto de `DB_NAME`, e papel com LOGIN/CREATEDB.
Os testes criam/removem esse banco e aplicam migrations nele. Não use
`--keepdb`/`--noinput` para reutilizar ou excluir um banco sem conferir seu destino.
Não há SQLite ou fallback remoto. SDK Gemini é simulado na suíte.

A auditoria desta base executou **1.153 testes, OK**, com banco descartável
ausente antes/depois. Isso não comprova OCR/IA com PDFs reais ou deploy.

`makemigrations --check` pode consultar o histórico do banco padrão. Para
conferir arquivos sem acessar QA/PROD, em PowerShell:

```powershell
$hostAnterior = $env:DB_HOST
try {
    $env:DB_HOST = "db-teste.invalid"
    python manage.py makemigrations --check --dry-run
} finally {
    $env:DB_HOST = $hostAnterior
}
```

Um aviso de conexão ao host fictício é esperado; a conferência de arquivos
deve informar `No changes detected`. Para validar aplicação e constraints,
use a suíte no PostgreSQL TEST. [Evidências da auditoria](docs/organizacao/GR-16-auditoria-aaa80cc.md).

## Operar e demonstrar

1. Cadastre pessoas/papéis e classificações pelos menus; receita precisa de
   classificação RECEITA válida, sem categorias fictícias automáticas.
2. Em Contas, registre APAGAR/ARECEBER, selecione principal e parcelas e confirme.
   Erros/reenvios preservam o UUID; nova conta intencional usa outro formulário.
3. Envie PDF fictício com sua chave Gemini. Revise o JSON v2 e as consultas.
4. Na conferência, crie classificação se necessário, salve correções e revise
   os dados salvos. Confirme explicitamente as decisões antes de lançar.
5. Consulte movimento e parcelas. Cancelar/expirar análise não é cancelar conta.

O botão de F-6 ainda não está conectado. Regularização de pessoa incompleta
existente já está na GR-46, sem documento fictício; nenhuma incompleta pode
ser lançada antes da regularização. T-05 aprovada mantém análise pendente até
o prazo original; falta idempotência oficial antes da ação de salvar pendente.

## Git, migrations e publicação

Fluxo: branch de tarefa → PR para `develop` → revisão → homologação → publicação
autorizada de `main`. Veja [ContextoFluxoGit.md](ContextoFluxoGit.md).
Commit, push, PR, merge, deploy e migrations remotas são ações humanas;
agentes não as executam neste trabalho.

`build.sh` instala dependências/coleta estáticos; `start.sh` inicia Gunicorn.
**Nenhum deles aplica migrations.** O responsável confere plano e destino,
valida localmente, aplica coordenadamente em QA e depois em PROD autorizado,
com recuperação preparada. O estado remoto não foi verificado nesta auditoria.

O rodapé lê o SHA completo de `RENDER_GIT_COMMIT`; conferir a correspondência
com a versão realmente publicada. `check --deploy` local com DEBUG=False apontou
W004 (HSTS) e W008 (redirecionamento HTTPS); a cobertura no proxy/publicação
deve ser demonstrada, não presumida.

## Privacidade, limpeza e entrega

Upload em memória com limite, sem fallback do Django para arquivo temporário.
Isso não controla retenção/buffers externos. JSON/correções são apagados ao
confirmar, cancelar ou expirar; metadados sem valores corrigidos permanecem.
O prazo bloqueia acesso em 30 minutos; apagamento de abandonadas depende de
evento posterior ou execução do comando oficial `expirar_analises`.

O agendamento desse comando é pendência operacional da GR-50. O login demo
é compartilhado, sem usuários/RBAC ou revogação central: cookie copiado pode
autenticar até expirar, e indisponibilidade do banco pode impedir o descarte.
QA usa apenas dados fictícios e credenciais próprias, separadas de PROD.

Não versione `.env`, PDFs reais, chaves, senhas ou o `Readme.txt` da entrega.
Esse arquivo deve conter link da versão publicada, login, senha e chave LLM
exclusivamente no canal restrito combinado com professor/equipe. Nunca em PR,
Jira, repositório público ou chat compartilhado. A entrega dos links no Classroom
e a confirmação do canal restrito são ações humanas ainda não comprovadas.

## Documentação

- [Contexto do projeto — auditoria integrada](ContextoProjeto.md#auditoria-gr16)
- [Matriz de requisitos](docs/requisitos/matriz-n2-etapa2.md)
- [Operação, ambientes e publicação](docs/operacao/GuiaOperacaoN2.md)
- [Contrato GR-51](docs/contratos/ContratoIntegracaoGR51.md)
- [Bloqueio F-6 para alinhar com Simon](docs/contratos/F6-idempotencia-alinhamento.md)
- [ADR Supabase](docs/arquitetura/ADR-001-supabase.md) e [índice documental](docs/INDICE.md)
