# GR-18 — Proteção e limpeza de análises temporárias

27/10/2026. Implementação de Lopes sobre `develop` `962140c` (PR #50).
Validada localmente; PR, integração, homologação e publicação pendentes.
Os PRs da GR-47/GR-15 não compõem esta base de validação.

## Controles implementados nesta entrega

1. Falha inesperada no processamento registra apenas etapa/código fixos,
   sem traceback, mensagem da exceção, cadeia de causas ou payload.
   `ProcessamentoError` mantém o contrato seguro existente.
2. O Django recebe arquivos apenas em memória, com limite pelos bytes reais
   recebidos somados no pedido (`MAX_PDF_UPLOAD_SIZE`). Interrompe upload acima
   do limite sem fallback para arquivos temporários. O validador do formulário
   continua verificando assinatura PDF, extensão, MIME e tamanho. As duas
   rotas de upload informam o limite quando a recepção é interrompida.
3. Respostas dinâmicas, inclusive páginas autenticadas, login, redirects e
   erros, recebem `Cache-Control: private, no-store, no-cache, max-age=0` e
   `Expires`. WhiteNoise continua atendendo estáticos fora deste middleware.
4. GET `/logout/` só mostra confirmação; POST com CSRF efetua saída e descarte.
   Um link externo ou prefetch não pode mais cancelar análises por GET.

Nenhum model, serviço de lançamento, regra de autorização, prazo ou migration
foi alterado. Os testes antigos de logout agora usam POST para exercer a mesma
operação; um novo teste exige que GET e POST sem token não alterem a análise.
A expectativa antiga de traceback foi substituída por verificações contra
vazamento, preservando etapa/código da falha e demais regressões.

## Proteções existentes conferidas

- Chave Gemini vem da requisição, não do banco/cookie; PDF não é campo de model.
  A extração final fica no servidor, vinculada ao hash do dono da sessão.
- UUID conhecido sem a sessão dona não libera leitura. A expiração de 30
  minutos bloqueia uso pelo backend; corrigir não renova o prazo.
- Confirmar, cancelar, expirar e descartar no logout limpam `dados` e
  `correcoes`; nomes dos campos corrigidos e metadados podem permanecer.
- Gravações passam por CSRF. A confirmação financeira continua exclusiva
  do serviço transacional existente. Testes dessa confirmação permanecem
  na suíte completa.

## Limpeza efetiva e operação

O serviço oficial `expirar_analises()` já apaga valores de análises vencidas
ao acessar a própria análise ou criar outra. Também existe o comando:

```text
python manage.py expirar_analises
```

O comando trata abandonadas sem depender de nova navegação e é idempotente.
Definição operacional proposta: executá-lo a cada cinco minutos em executor
autorizado da equipe. Instalação/agendamento e ambiente de execução devem ser
fechados na publicação (GR-50), por Simon/Gustavo; nenhum agendamento remoto
foi configurado nem comando remoto executado nesta tarefa.

Enquanto não houver execução periódica, o acesso vence em 30 minutos, mas o
apagamento físico dos valores pode esperar próxima operação ou comando.
O prazo não representa promessa de eliminação de backups/WAL, logs da
plataforma, buffers do proxy ou memória/cache do dispositivo do usuário.

## Login demo, ambientes e limites

O login é compartilhado, sem usuários individuais, RBAC ou revogação central
de cookies assinados. Um cookie copiado antes do logout pode autenticar até
expirar e criar novas análises; as existentes canceladas não são recuperadas.
Não há garantia de revogação completa quando o banco falha no descarte.

QA deve receber somente PDFs/documentos financeiros fictícios e credenciais
próprias desse ambiente. QA e PROD continuam separados; nada foi enviado a
eles. Publicação deve manter `DEBUG=False`, HTTPS/cookies seguros e evitar
logs de tráfego/payload do SDK. A aplicação evita escrita do PDF pelo Django;
não controla buffers ou retenção externos da infraestrutura.

## Evidências

11 testes novos e 164 dirigidos OK: logs com causa contendo segredos fictícios,
upload em memória mesmo acima do limiar padrão, interrupção por tamanho,
cache, sessão alheia, expiração, limpeza por comando, CSRF e logout seguro.
Suíte completa: **1.078 testes, OK** no PostgreSQL local isolado;
banco descartável ausente antes/depois. Check OK; sem alterações de migrations.
Após reunir PRs, repetir a validação conjunta. A implantação do agendamento
de limpeza e a conferência das configurações publicadas permanecem para GR-50.
