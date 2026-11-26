# 12 — Pendências, decisões em aberto e riscos

Consolida o que **falta**, o que **ainda precisa ser decidido** e o que é **risco conhecido**, com base no código integrado, na matriz de requisitos
e nas auditorias (GR-16, de 27/10/2026, e de 24/11/2026 — [`docs/auditoria/Auditoria-2026-11-24.md`](../auditoria/Auditoria-2026-11-24.md)).
**Não decida por conta própria** as dúvidas de escopo listadas na seção 2: elas pertencem à equipe ou ao professor.

## 1. Funcionalidades incompletas

| Item | Situação | Detalhe |
| --- | --- | --- |
| **F-6 — "Salvar cadastro pendente"** | Serviço existe; **botão não ligado** | `cadastros/pendentes.salvar_cadastro_pendente()` **não é idempotente**: duas chamadas iguais criam duas pessoas incompletas. Falta uma operação oficial com chave de idempotência, vínculo a sessão/análise/versão e erros estáveis — [proposta, **não aprovada**](../contratos/F6-idempotencia-alinhamento.md). Não deduplicar por nome nem criar persistência paralela na tela. FLU-05/06 permanecem **parciais** |
| **GR-39 / GR-49 — manutenção financeira** | Não implementado | Sem editar, cancelar ou dar baixa em movimento/parcela; sem histórico de parcelas; `StatusMovimento.CANCELADO` e `StatusParcela.CANCELADA` existem no modelo, mas **não há operação que os use**. RN-02/RN-03 e UI-06/08/09 continuam **parciais** para o domínio financeiro. A GR-49 consta "Feito" no Jira, mas é **parcial** no código (divergência registrada) |
| Mais de uma classificação por nota | Só no fluxo **manual** | O fluxo da nota grava uma única classificação, principal (Q-06) |
| Contas a receber a partir de documento | Fora do fluxo automático | Os Agents só tratam notas de despesa (Q-10); não há carga inicial de classificações de RECEITA (Q-05) |
| Notas fora de NF-e 55 / NFC-e 65, ou com emitente CPF | Bloqueadas no fluxo fiscal | Decisão T-06 / DQ-17 até nova decisão |
| Ordenação por coluna em Contas | Não | UI-04 parcial |
| Ingestão por e-mail, amortização, quitação fracionada, saldo, painel, alertas, conciliação, autenticação real | Fora do escopo atual | Planejado pelo cliente (RF-17) |
| Data de emissão da nota | **Não é gravada** no movimento | O modelo não tem esse campo; só vive na análise enquanto pendente |

## 2. Decisões e dúvidas em aberto

| ID | Dúvida | Quem decide | Situação |
| --- | --- | --- | --- |
| Q-01 | As telas CRUD completas de **todas** as funcionalidades "Manter/Registrar" são obrigatórias? | Professor / interpretação da equipe | Equipe priorizou o fluxo da nota e implementou os cadastros; **sem resposta do professor** |
| Q-05 | Quais categorias valem? Como o Enum do Classificador corresponde ao cadastro? O cliente usa Insumos/Operacionais (DESPESA) e Venda produção (RECEITA); o código só tem 2 categorias de DESPESA | Equipe | Lista de categorias **não aprovada**; `codigo` espelha o Enum |
| Q-06 | O Classificador deve devolver mais de uma classificação por nota? | Equipe | Sem decisão |
| Q-07 / Q-08 | Canal e chave de LLM do `Readme.txt` de entrega | Equipe/professor | Humano |
| Q-09 | O "código da última atualização" é o hash completo, curto, tag? | Equipe/professor | Hoje: SHA completo de `RENDER_GIT_COMMIT` |
| Q-10 | Contas a receber entram no fluxo automático? | Equipe | Não, hoje |
| PT-05 | DEV/QA compartilhado ou DEV local obrigatório? | Equipe | O ADR admite compartilhado coordenado; não alterar silenciosamente |
| — | Uso de pessoa **incompleta** em movimentos financeiros (DQ-05) | Equipe | Hoje: **bloqueado** até regularizar |
| — | Retenção/LGPD: CPF/CNPJ em texto simples, envio do PDF ao Gemini | Equipe | Sem ADR/aviso (B-03) |
| — | Cancelamento de movimento e baixa de parcela | Equipe | Sem contrato aprovado |

## 3. Achados da auditoria de 24/11/2026

Severidade: **A** = tratar antes de publicar/entregar; **M** = importante; **B** = melhoria.

| ID | Sev. | Achado | Ação recomendada | Estado |
| --- | --- | --- | --- | --- |
| A-01 | A | `Django==6.1.1` sem as correções de segurança 6.1.2 e 6.1.3 | Atualizar para 6.1.3, rodar a suíte, publicar | **`requirements.txt` já está em 6.1.3** e a suíte passou localmente; **falta publicar** (`develop` → `main`) e confirmar a versão instalada no Render |
| M-01 | M | Login sem limite de tentativas; sessão de 14 dias; login compartilhado | Definir `SESSION_COOKIE_AGE` (ex.: 8 h) e limitar tentativas por IP/janela; exigir senha longa | **Corrigido no código** (`ContextoProjeto.md` 39.2): sessão de 8 h, limite por origem/global, aviso de senha curta; falta publicar e conferir o IP real no Render |
| M-02 | M | HSTS e redirecionamento HTTPS não estão no código | Verificar na URL publicada e registrar a evidência | Aberto (humano) |
| M-03 | M | `cadastros/views*.py` só tratam `ValidationError`/`IntegrityError`; sem `404.html`/`500.html` | Decorador equivalente ao `_erros_de_banco` do financeiro + templates de erro em português | **Corrigido no código** (`ContextoProjeto.md` 39.1); falta publicar |
| M-04 | M | Um worker síncrono com chamadas de minutos | `WEB_CONCURRENCY` ≥ 2 no Render ou workers com threads; documentar o limite | Aberto |
| M-05 | M | F-6 e GR-39/49 abertas | Fechar com o responsável pelos serviços; agendar `expirar_analises` | Aberto |
| M-06 | M | Sem RLS nas migrations; depende de a Data API do Supabase estar desativada | Conferir QA/PROD e registrar evidência; por precaução, habilitar RLS sem políticas | **Migration criada** (`financeiro/0005_habilitar_rls`, 39.6), **não aplicada** em nenhum banco remoto; conferir a Data API e aplicar a migration é ação humana |
| B-01 | B | Documentação defasada (ver seção 5) | Corrigir | Parcial |
| B-02 | B | Sem CI e sem cobertura | Workflow com serviço PostgreSQL rodando `check`, `makemigrations --check` e `test`; avaliar `ruff` | **Workflow criado** (39.3), ainda não executado no GitHub; sem cobertura nem `ruff` |
| B-03 | B | Dados pessoais e envio a terceiro sem aviso/registro | ADR ou README com a decisão de privacidade | **Rascunho** em [ADR-002](../arquitetura/ADR-002-privacidade-dados-pessoais.md) (proposta; decisões abertas para a equipe) |
| B-04 | B | Limpeza das análises sem agendamento | Executar `expirar_analises` periodicamente (proposta: a cada 5 min) | Aberto (GR-50): o comando já existe; falta agendar no Render (humano) |
| B-05 | B | `requirements.txt` sem hashes; sem `LOGGING`; sem CSP; `media/` e `uploads/` locais vazios; comentário obsoleto em `settings.py` ("MVP da N2 - Etapa 1 sem banco…") | Limpeza e endurecimento | **Parcial** (39.4): `LOGGING`, comentário e quebra de linha final corrigidos; faltam hashes e CSP |

## 4. Pendências de entrega e operação (humanas)

Nenhuma destas foi verificada pelas auditorias:

- Estado das migrations em QA/PROD (inclusive `financeiro/0004`).
- SHA publicado × rodapé; URL pública e HTTPS.
- Teste em navegador; teste com **Gemini real** e PDFs reais.
- Canal restrito do `Readme.txt` e envio ao Classroom.
- Configuração de proteção das branches `main` e `develop` no GitHub.

> **Implementado, integrado, validado localmente, homologado e publicado continuam sendo estados distintos.**

## 5. Documentação defasada (a corrigir na fonte, não aqui)

| Onde | Problema |
| --- | --- |
| `ContextoProjeto.md`, seções 5 a 7 e 28 | Ainda marcam RF-08 a RF-14 e RN-01 a RN-07 como "não implementado" e listam "implementar toda a Etapa 2" como crítico; esta pasta ([03](03-requisitos.md), [04](04-regras-de-negocio.md)) traz a situação atual |
| `ContextoProjeto.md`, seção 15.1 | Dizem que o estado da Etapa 1 "é o estado da `main`"; `main` já recebeu a `develop` (PR #58) |
| `ContextoProjeto.md`, seção 17.3 | O JSON de exemplo é o **v1 antigo** (sem `faturado.cnpj` e com 2 validações); o v1 atual tem 3 validações e o v2 tem `documento_fiscal` ([07](07-agents-e-contratos.md)) |
| `ContextoProjeto.md`, seção 18.5 | Diz que classificação inconclusiva "vira erro na tela, sem JSON"; **hoje preserva a extração** |
| `ContextoProjeto.md` | Numeração fora de ordem (seção 35 antes de 34.16–34.25; 36 e 37 ao final) |
| `docs/arquitetura/ADR-001-supabase.md` | Contexto e implementação ainda falam em `DATABASES = {}` e em GR-33 "não integrada" |
| `docs/requisitos/matriz-n2-etapa2.md` | Nota de 25/10 "não integrada" e referências a `f7786e8`/`aaa80cc` |
| `README.md` e GR-16 | Citam `aaa80cc` e dizem que `origin/main` está em `f7786e8`; o prazo "27/10/2026" já passou |
| `config/test_sem_banco.py` | Nome da Etapa 1; hoje testa garantias estruturais com banco |
| `settings.py` (comentário de `INSTALLED_APPS`) | Fala em "sem banco de dados, sem admin, auth…" |
| `VERSAO_SCHEMA` (Agents) | Constantes sem uso e comentário "ver 34.7" |

## 6. Riscos técnicos para quem implementa

| Risco | Por quê | Como evitar |
| --- | --- | --- |
| Quebrar a idempotência | `analise_origem_id` e `chave_idempotencia` são únicos; a comparação do "mesmo lançamento" inclui valores, classificações e parcelas | Não altere `_mesmo_lancamento` nem os campos únicos sem teste de reenvio e de concorrência |
| Gravar financeiro fora de `registrar_movimento` | Perde bloqueios, validações e o gatilho de soma | Use sempre o serviço; nunca `MovimentoConta.objects.create` direto |
| Alterar campo imutável | `AlteracaoNaoPermitida` | Cancelamento/edição exigem **operação própria** com contrato aprovado, não um `update()` |
| Mexer em `CONFIRMADO` | Não é "ativo" nem "quitado" | Defina estados novos explicitamente (ex.: baixa) e atualize filtros "TODOS" |
| Misturar versões de JSON | v1 e v2 coexistem; reconhecimento pelo conjunto exato de chaves | Não converta análises existentes; adicione versão nova com decisão |
| Confiar na tela | A tela pode ser adulterada | Revalide no serviço (como `conferir_nota` e `registrar_movimento` fazem) |
| Vazar dado sensível em erro/log | Mensagens com valores/documentos | Código estável + mensagem fixa |
| Duas rotas de processamento | `documento_inicio` (legado) e `analise_criar` | Ao mudar o processamento, confira as duas, ou remova a legada com decisão |
| Banco compartilhado | QA é compartilhado e coordenado | Nunca rode testes destrutivos, migrations ou SQL contra QA/PROD sem autorização |
| 1 worker | PDF de minutos bloqueia o serviço | Considere o impacto antes de adicionar trabalho síncrono pesado |
