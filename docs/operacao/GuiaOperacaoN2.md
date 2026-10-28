# Operação e entrega — N2 Etapa 2

Referência auditada: `aaa80cc`, 27/10/2026. Este roteiro não autoriza operações
remotas nem comprova que tenham ocorrido. Execução de Git de publicação,
migrations remotas e deploy continua humana, coordenada com Simon.

## Ambientes e credenciais

| Ambiente | Destino e controle |
| --- | --- |
| TEST | PostgreSQL exclusivamente local; variáveis `DB_TEST_*`, banco descartável `test_*`, separado de `DB_NAME`. Criação/remoção pelo runner oficial |
| DEV | Execução do aplicativo com `DB_*`. Para DEV local, preparar banco próprio com TLS; não reutilizar TEST. A PT-05 histórica admite DEV/QA compartilhado e continua exigindo coordenação |
| QA | Supabase de homologação, dados fictícios e credenciais próprias. Testes automatizados não o utilizam |
| PROD | Projeto/banco e credenciais separados de QA. Preparação e aplicação do esquema dependem de autorização e evidência do responsável |

Não copiar credenciais de um integrante nem presumir que rodar no notebook
torna `DB_*` local. A conexão normal aceita TLS `require`/`verify-ca`/`verify-full`;
o runner de TEST usa `prefer` somente no loopback. Configuração validada de
TEST não comprova DEV com TLS nem estado remoto de QA/PROD.

O [README](../../README.md) descreve instalação e variáveis, sem valores reais.
A política aprovada permanece no [ADR](../arquitetura/ADR-001-supabase.md).
Uma eventual substituição de DEV/QA compartilhado por DEV local obrigatório
precisa ser registrada como decisão, não introduzida por esta auditoria.

## Esquema e publicação coordenada

1. Integrar/revisar PRs e conferir a referência que será publicada.
2. Validar suíte com PostgreSQL TEST, `check` e ausência de migrations novas
   não versionadas; leitura do histórico padrão deve usar host fictício se
   QA/PROD não puderem ser acessados.
3. Responsável confere host, banco, papel, ambiente e plano de migrations.
   Registro de evidência não deve conter segredos ou strings de conexão.
4. Aplicar migrations em QA somente após autorização/coordenação. Nessa base:
   `cadastros` 0001–0003, `documentos` 0001–0002, `financeiro` 0001–0004.
5. Homologar fluxos e registrar versão, ambiente, resultado e pendências.
6. Preparar recuperação; aplicar esquema em PROD e publicar pelo fluxo
   `develop` → `main`, conforme autorização humana e plano da equipe.
7. Conferir URL, login, HTTPS, banco do ambiente, estáticos e SHA do rodapé.

`build.sh` instala dependências e coleta estáticos; `start.sh` executa Gunicorn.
Nenhum aplica migrations. Não adicionar `migrate` automaticamente no build/start.
A migration `financeiro/0004` é necessária à idempotência manual; sua aplicação
remota continua sem comprovação nesta auditoria. Não testar contas manuais em
QA antes da confirmação de Simon sobre seu esquema.

## Validação funcional conjunta

Usar exclusivamente dados fictícios e registrar resultados observados:

- Pessoas PF/PJ com múltiplos papéis; edição e status independentes;
  classificação RECEITA/DESPESA criada e inativada/reativada explicitamente.
- Conta manual APAGAR com faturado e ARECEBER com faturado opcional;
  múltiplas classificações/principal, parcelas e soma, confirmação e reenvio.
- PDF fictício → Agents → JSON v2 → consulta → correções → decisões → F-5
  → movimento/parcelas. Testar inconclusiva, erros de API, documento ambíguo,
  identidade fiscal insuficiente/divergente e duplicidade.
- FLU-07: criar classificação na conferência, preservar rascunho, salvar
  correções e confirmar separadamente; original continua intacto.
- Sessão alheia, expiração/cancelamento, CSRF, logout por POST e ausência
  de PDF/chave em persistência/logs. Cookie demo copiado ainda é limitação.
- Não demonstrar F-6 ou histórico/manutenção financeira como prontos:
  [bloqueio F-6](../contratos/F6-idempotencia-alinhamento.md) e GR-39/49 pendentes.

Suíte com SDK simulado não comprova precisão com PDF real nem operação no Render.
Não mudar modelos/categorias dos Agents para contornar falhas de integração.

## Limpeza e proteção da versão publicada

O comando oficial é `python manage.py expirar_analises`, no ambiente explicitamente
autorizado. O bloqueio por prazo ocorre em 30 minutos; limpeza de abandonadas
sem atividade exige executar o comando. Proposta registrada: execução a cada
cinco minutos por executor autorizado. Agendamento/monitoramento não foram
instalados; ficam na GR-50. Não há promessa de expurgo de backups/WAL.

Conferir `DEBUG=False`, credenciais próprias, hosts/CSRF, HTTPS e cookies seguros.
O `check --deploy` local apontou W004 e W008: HSTS/redirecionamento HTTPS precisam
ter sua cobertura efetiva verificada na aplicação/proxy. Não foram verificados
na URL pública. Logs de tráfego/payload de SDK não devem ser habilitados.

## Evidências e entrega restrita

Registrar commit implantado, SHA completo do rodapé (`RENDER_GIT_COMMIT`),
ambiente, data, resultado dos cenários e responsáveis. Não registrar valores de
credenciais, conteúdo de PDFs reais, JSON pessoal ou dados de conexão.

O repositório é público. `Readme.txt` da entrega é ignorado e deve ser montado
pelos integrantes com URL, login, senha e chave LLM apenas no canal restrito
combinado com o professor. Não colocá-lo no PR/Jira. Confirmar destino/canal,
postar links do GitHub/site no Classroom e comprovar envio antes do prazo.

Esta auditoria não leu o arquivo restrito, não confirmou seu conteúdo, não
postou no Classroom e não acessou QA/PROD.
