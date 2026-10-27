# GR-46 — Manutenção de Pessoas e Papéis

27/10/2026. Entrega de Lopes preparada sobre `develop` `3887b89`.
Implementada e validada localmente; integração, homologação e publicação
dependem das etapas humanas do PR. Nenhuma operação de publicação foi executada.

## Comportamento

- Menu Pessoas e rotas autenticadas em `/cadastros/pessoas/`.
- Lista inicialmente vazia. Pesquisa por nome/documento, papel e situação;
  TODOS carrega somente pessoas ativas. Ordenação controlada e páginas de 30.
  A pesquisa administrativa não identifica automaticamente ninguém pelo nome.
- Cadastro com CPF/CNPJ válido e um ou mais papéis escolhidos explicitamente.
  Um documento normalizado identifica uma única pessoa; nenhum papel é
  deduzido do tipo de documento. A criação usa `resolver_partes()` (F-4),
  incluindo sua transação oficial para pessoa e papéis.
- Edição de nome e documento com ModelForm, validação oficial de DV e
  unicidade. A gravação restringe os campos para não restaurar status antigo.
- Atribuição pelo método `Pessoa.atribuir_papel()`, sem reativar papel existente.
- Inativação e reativação independentes de pessoa e papéis, com confirmação
  explícita em POST e CSRF. GET apenas apresenta o formulário.
- Cadastro incompleto existente pode ter o nome editado; completar o documento
  usa `regularizar_cadastro_pendente()` (F-6), preservando seu ID e os papéis.
- Nenhuma exclusão física, alteração de vínculo financeiro, lançamento ou
  duplicação de serviço de persistência. Models, serviços e migrations intactos.

## Validação

- 19 testes direcionados: autenticação/CSRF, documento normalizado/duplicado,
  escolhas de papéis, status independentes, regularização e preservação de
  movimento financeiro e parcelas pelo serviço oficial.
- Dois testes de leituras intercaladas verificam que editar nome/documento
  não desfaz inativação ou regularização realizada após a leitura do formulário.
  Não representam uma prova geral de concorrência para todos os cadastros.
- Suíte completa: **1.020 testes, OK** no PostgreSQL local isolado; banco
  descartável ausente antes/depois. `manage.py check`: OK;
  `makemigrations --check --dry-run`: sem alterações.
- Sem acesso a QA/PROD, chamadas Gemini ou migrations remotas.

## Limites e sequência

Esta tela não implementa “Salvar cadastro pendente” a partir da análise.
Esse fluxo segue dependente do contrato idempotente da F-6 com Simon e da
T-05 aprovada: manter análise PENDENTE até seu prazo original de 30 minutos.
Também não implementa classificações (GR-47) nem manutenção financeira.
Após o merge, realizar a navegação de homologação e atualizar o Jira com a
evidência real, sem equiparar validação local à publicação.
