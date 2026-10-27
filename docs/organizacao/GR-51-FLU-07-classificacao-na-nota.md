# GR-51 / FLU-07 — Criar classificação durante a conferência

27/10/2026. Lopes. Base `develop` `1ac4dd6` (PR #55, interfaces anteriores
integradas). Implementação validada localmente; PR, integração, homologação
de navegação e publicação desta entrega pendentes.

## Compatibilidade conferida

O Enum do Classificador permanece com suas duas categorias, sem mudanças.
A correção humana `tipo_despesa` usa o validador oficial de código do backend,
que aceita o formato de `Classificacao` além desse Enum. F-3 consulta pelo
código/tipo e F-5 usa o cadastro real revalidado.

Um teste integrado cria código fora do Enum, salva correções e confirma a
nota pelo serviço oficial, verificando o vínculo financeiro com esse cadastro.
Não há lacuna de domínio impedindo esse caminho. Nenhum Agent, prompt,
schema fiscal, serviço, model ou migration foi alterado.

## Comportamento

- A conferência apresenta o formulário de nova classificação de DESPESA.
  Sugere apenas o código existente nos dados/correções, se houver; código
  ausente e descrição não são inventados.
- Reutiliza `NovaClassificacaoForm` da GR-47 e validações de `Classificacao`.
  Tipo limitado a DESPESA; código/descrição explícitos e consentimento exigido.
- Cadastro é ação própria, com CSRF, autorização da sessão, prazo vigente
  e conferência da versão lida. Campos externos e repetidos são recusados.
- Após cadastrar, seleciona o cadastro no formulário e preserva todos os
  campos em edição, inclusive quando ainda incompletos. Não redireciona para
  outra tela descartando o rascunho.
- Não grava correções implicitamente, não modifica JSON original ou prazo
  e não cria movimento. Usuário salva correções e confirma financeiramente
  em etapas explícitas; todas as validações oficiais continuam obrigatórias.
- Unicidade considera registros ativos/inativos. Reenvio não cria duplicata;
  conflito no índice vira erro seguro. Nunca reativa automaticamente.

## Limite transacional explícito

A criação é cadastro administrativo independente, como na GR-47, usando
savepoint próprio. Não é a transação de lançamento financeiro. Uma análise
encerrada posteriormente não exclui o cadastro do catálogo; a tela informa
isso. Não há promessa de atomicidade conjunta entre criação de classificação
e ciclo de vida da análise. O backend continua bloqueando confirmação fora
do prazo, de outra sessão ou com versão/estado inválidos.

## Evidências

14 testes novos e 56 dirigidos de conferência, cadastro e integração passaram.
Cobrem criação explícita, preservação do rascunho, v1/v2, prazo, sessão, CSRF,
versão, unicidade em qualquer status, erro do índice e confirmação financeira
com código fora do Enum. O teste de disputa injeta a recusa do índice;
não representa prova de concorrência de dois processos nesta interface.

Suíte completa: **1.153 testes, OK** no PostgreSQL local isolado;
banco descartável ausente antes/depois. Check OK; sem alterações de migrations.
Sem chamadas reais de API, QA/PROD, deploy ou migrations remotas.

Após revisão/merge, homologar a navegação no navegador. F-6/cadastro pendente
e manutenção/histórico financeiro GR-39/49 continuam frentes separadas.
