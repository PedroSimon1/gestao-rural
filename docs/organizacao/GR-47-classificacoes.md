# GR-47 — Classificações de receita e despesa

27/10/2026. Implementação de Lopes sobre `develop` `962140c`, que contém
GR-46 (PR #49) e o backend financeiro manual P08 (PR #50).
Validada localmente; ainda sem integração, homologação ou publicação desta tarefa.

## Comportamento e regras

- Menu Classificações; rotas autenticadas em `/cadastros/classificacoes/`.
- Lista inicialmente vazia, pesquisa por código/descrição, tipo e situação;
  múltiplos termos podem combinar código e descrição. TODOS carrega somente
  ativos. Ordenação por coluna com lista permitida e páginas de 30 registros.
- Criação de RECEITA ou DESPESA com código normalizado em maiúsculas,
  descrição e status ATIVO padrão. O formulário não aceita status fornecido
  externamente, tipos inválidos nem códigos fora da regra oficial.
- Unicidade por tipo/código, incluindo registros inativos. Um registro
  inativo não é duplicado nem reativado automaticamente.
- Tipo e código são imutáveis; edição altera somente a descrição.
  A atualização restringe os campos para não desfazer inativação intercalada.
- Inativação e reativação usam os métodos existentes do model, com
  confirmação explícita em POST e CSRF. GET não altera dados. Sem exclusão física.
- ModelForm/model validam no servidor; a constraint única decide disputas
  de criação. Um savepoint permite tratar a recusa como erro do formulário.
  Não há serviço paralelo nem transação financeira nesta interface.
- Models, migrations, Agents e serviços financeiros permanecem intactos.

## Validação e limites

14 testes direcionados passaram: autenticação, CSRF, busca/TODOS, paginação,
normalização, unicidade em qualquer status, proteção de identidade, escape
HTML e preservação de vínculos financeiros e parcelas. Um teste intercala
leitura/edição e inativação; não é uma prova geral de concorrência.

Suíte completa: **1.081 testes, OK** no PostgreSQL local isolado;
banco descartável ausente antes/depois. Check OK; migrations sem alterações.
Patch conferido com `git apply --check --whitespace=error` na base limpa.
Nenhum acesso a QA/PROD, chamada Gemini, deploy ou migration remota.

Cobertura desta entrega: FUN-04/FUN-05, ENT-02 e recomendações UI-01 a UI-09
no cadastro de classificações. A auditoria geral da matriz permanece separada.
Esta tarefa não adiciona categorias ao Enum do Classificador nem implementa
a criação automática de classificação inédita no fluxo da nota (FLU-07).
Criar um cadastro administrativo não cria um movimento financeiro.

Após o merge: conferir navegação de homologação e atualizar o Jira com a
evidência correspondente, distinguindo implementação, integração e publicação.
