# GR-49 — Listagens e detalhes financeiros (entrega parcial)

27/10/2026. Lopes, base `develop` `962140c` (PR #50).
Implementação validada localmente; integração, homologação e publicação pendentes.
**A GR-49 completa permanece pendente** dos serviços de manutenção/histórico.

## Parte implementada

- Menu Contas e rotas autenticadas GET em `/financeiro/contas/` e
  `/financeiro/contas/<id>/`. Lista inicialmente vazia, pesquisa e TODOS
  (confirmados). Um lançamento CONFIRMADO não significa pagamento/quitação.
- Filtros combináveis: a pagar/a receber, origem manual/nota fiscal, estado
  do lançamento, contraparte e classificação. Seletores incluem cadastros
  inativos para permitir consultar relações históricas.
- Listagem paginada de 10/30/100 contas, mais recentes primeiro conforme
  serviço oficial. Exibe contraparte, valor, estado, número de parcelas
  ativas e próximo vencimento ativo.
- Detalhe com origem, contraparte, faturado, classificações e principal,
  parcelas com vencimento, valor e estado atual (inclusive canceladas).
- Chamadas exclusivamente a `listar_movimentos()`/`consultar_movimento()`
  de `financeiro.manual`. Não repete consultas de movimentos na view,
  cria serviço financeiro paralelo ou altera registros.
- Filtros inválidos não chegam ao serviço; indisponibilidade vira mensagem
  fixa/503 sem SQL. Respostas têm no-store, inclusive erro 404 de detalhe.
  POST, PUT e DELETE não são permitidos nas rotas de consulta.

## Bloqueios e critérios restantes

O Jira liga a GR-49 às GR-37/38 (feitas), GR-39 (pendente) e GR-48 (pendente).
O PR #50 fornece serviços manuais e consultas; o estado do ticket GR-48
não foi alterado nem equiparado à conclusão de sua interface.

Restam contratos/serviços de Simon para:

1. Edição controlada de parcelas e `HistoricoParcela` (GR-39).
2. Consulta do histórico de mudanças — a lista de parcelas atuais não é
   esse histórico e não é apresentada como tal.
3. Ações financeiras de inativação/reativação/cancelamento, com regras
   aprovadas para seus efeitos. Não confundir status administrativo com
   quitação. Os models atuais impedem alteração direta dos registros.

Após os serviços integrarem, Lopes conecta as telas aos contratos oficiais.
Não há botões de edição, baixa, inativação ou reativação simulados nesta entrega;
nenhuma escrita foi feita por `.update()`/SQL fora das fixtures de teste.

## Evidências e integração

12 testes novos; 57 dirigidos com as regressões oficiais de `financeiro.manual`
passaram. Suíte completa: **1.079 testes, OK** na base citada,
PostgreSQL local isolado, banco descartável ausente antes/depois.
Check OK; sem alterações de migrations. Testes de leitura verificam ausência
de INSERT/UPDATE/DELETE. Cancelamentos são fixtures controladas de TEST.

Nenhum model, serviço, Agent ou migration alterado; sem QA/PROD ou API real.
A base ainda não reúne GR-47/GR-15/GR-18. Conferir aplicação do patch na base
atualizada e executar a suíte conjunta após os merges. O link de menu é
independente do link de Classificações adicionado pela GR-47.

O PR deve dizer **consulta/detalhe, GR-49 parcial**. Não marcar o ticket
inteiro como Feito antes de validar os critérios restantes e integrar a entrega.
