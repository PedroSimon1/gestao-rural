# GR-48 / P08 — Interface de contas manuais

27/10/2026. Lopes. Base `4631196`, commit publicado da consulta GR-49,
construído sobre `develop` `962140c` (backend manual PR #50).
Implementação e validação locais; PR, integração, homologação e publicação pendentes.

## Fluxo e regras

- Pela listagem Contas, abrir “Registrar conta manual”. Escolher A PAGAR ou
  A RECEBER; trocar o tipo inicia outro formulário e outra solicitação.
- APAGAR oferece fornecedor e faturado obrigatório; ARECEBER oferece cliente
  e faturado opcional. Só cadastros completos, pessoas e papéis ativos são
  selecionáveis. CPF/CNPJ não determinam o papel.
- Classificações ativas do tipo DESPESA/RECEITA compatível com a conta;
  selecionar uma ou mais e exatamente uma principal dentre elas.
- Valores aceitam vírgula ou ponto para centavos, sem separador de milhar,
  expoentes, NaN ou arredondamento silencioso. Nenhum total ou parcela é
  calculado para preencher dados ausentes.
- Adicionar linhas de parcela pela interface; remover marca apenas uma
  linha do rascunho, nunca um registro financeiro. O serviço numera as
  parcelas restantes. Formset limitado a 120 linhas, inclusive em POST hostil.
- Checkbox explícito e botão Confirmar registro antes de qualquer gravação.
  CSRF obrigatório. Erros permanecem no formulário; sucesso redireciona ao
  detalhe existente da GR-49 somente depois do retorno do serviço.

## Integração oficial e idempotência

A view monta `ContaManual`, `ClassificacaoManual` e `ParcelaManual` e chama
apenas `registrar_conta_manual()`. Não grava models diretamente, não cria
outro serviço ou transação financeira e não regulariza/reativa automaticamente.
Backend revalida referências, estados, classificações e soma das parcelas.

Um UUID novo nasce somente no GET de novo formulário. POST inválido ou
reenvio mantém UUID e prova assinada, vinculada ao tipo e à sessão autenticada.
A assinatura protege a origem do formulário; a garantia de idempotência
financeira continua exclusivamente no serviço/índice oficial.

Reenvio idêntico retorna o mesmo movimento. Mesma chave com conteúdo diferente
é recusada. Nova conta pode repetir os dados com outro UUID. Foi testada a
falha de resposta após a gravação: reenvio não duplica o movimento.
O cookie guarda apenas os metadados aleatórios da sessão; não recebe o
conteúdo financeiro do formulário. A prova não expõe o código bruto da análise.

## Dependências e publicação

Este patch deve ser aplicado em branch criada de `origin/develop` **depois
do merge da GR-49**. Acrescenta formulário à listagem/rotas existentes, sem
republicar o código de consulta. Não criar branch de publicação na branch antiga.

Para cadastrar classificações RECEITA pela interface, integrar também a
GR-47. Não são criadas categorias fictícias. A manutenção de parcelas/histórico
GR-39, FLU-07 e cadastro pendente F-6 continuam tarefas separadas.

Migration `financeiro/0004` no ambiente de homologação permanece responsabilidade
do Simon. Nenhum teste remoto ou migration remota foi executado.

## Evidências

23 testes novos; 80 dirigidos de interface manual, consulta e backend oficial
passaram. Suíte completa na base `4631196`: **1.102 testes, OK**,
PostgreSQL local isolado, banco descartável ausente antes/depois.
Check OK; sem alterações de migrations. Nenhum model, serviço, Agent ou
dependência alterado. A interface dinâmica de parcelas usa JS local, sem CDN.

A validação HTTP/formset cobre regras e reenvios; homologação de navegação
em navegador e publicação real permanecem etapas dos integrantes.

Validação conjunta local dos patches GR-47/15/18/49 + GR-48: **1.139 testes, OK**. Essa composição de fontes não representa merge Git, homologação ou publicação.
