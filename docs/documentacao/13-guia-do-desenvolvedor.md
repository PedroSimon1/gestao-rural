# 13 — Guia para quem vai alterar o sistema

Leia antes de começar uma funcionalidade nova ou uma correção. É um mapa de **onde mexer**, **o que não pode quebrar** e **o que conferir**.

## 1. Antes de começar

1. **Branch certa.** Nunca desenvolva em `main` nem em `develop`. Crie `feature/*`, `fix/*`, `docs/*`, `refactor/*`, `test/*` ou `chore/*` a partir de `develop` atualizada ([`ContextoFluxoGit.md`](../../ContextoFluxoGit.md)).
2. **Estado local.** `git status --short --branch`: identifique alterações preexistentes (podem ser de outro integrante). Não reverta nem "limpe" o que você não entende.
3. **Linha de base.** Rode `DJANGO_DEBUG=True python manage.py test` (ou o app que vai tocar) **antes** de mudar, para saber o que já falhava.
4. **Leia a regra.** [04](04-regras-de-negocio.md) (regras), [06](06-modelo-de-dados.md) (dados) e [05](05-fluxos.md) (fluxo) do que vai tocar. Se a mudança conflita com uma decisão registrada (`DQ-xx`, `D-xx`, `T-xx`), **pare e consulte a equipe**: não reabra decisão como se estivesse indefinida.
5. **Escopo.** Faça o que foi pedido. Sem refatoração extensa, sem mudar arquitetura por preferência, sem atualizar dependências sem justificativa, sem criar camadas "por formalidade".
6. **Fontes de verdade** (em ordem): código e testes → `ContextoProjeto.md` → matriz de requisitos → ADRs → README. Em divergência entre fontes, **registre o conflito**; não invente a resolução.

## 2. Onde mexer

| Quero… | Mexa em | Cuidados |
| --- | --- | --- |
| Mudar o **prompt**, o modelo ou o schema de extração | `agents/extrator/agent.py`, `schemas.py`, `schemas_v2.py` | O schema é também o `response_schema` do Gemini; mexer em versão mexe no contrato JSON (ver [07](07-agents-e-contratos.md)) e em `documentos/test_contrato_agents.py` |
| Mudar categorias do Classificador | `agents/classificador/schemas.py` (`TipoDespesa`), prompt e `cadastros` | O `codigo` do cadastro espelha o Enum; exige decisão (Q-05) e carga/migration de dados |
| Mudar o **upload** do PDF | `documentos/validators.py`, `uploads.py`, `forms.py` | O limite vale pelos bytes recebidos; nada pode ir a disco |
| Mudar o que a **conferência** mostra/permite corrigir | `documentos/interface_conferencia.py`, `forms_conferencia.py`, `forms_fiscais.py`, `correcoes.py`, `conferencia.py`, templates | **Campo corrigível novo** precisa de: validador em `CAMPOS_CORRIGIVEIS`, tratamento em `conferencia._extraidos/_combinar`, campo no form e no template, e testes (F-2 e F-3) |
| Mudar regras da **nota** (problemas, identidade) | `documentos/conferencia.py`, `financeiro/identidade_fiscal.py` | Devolva **código + campo**, nunca valores; atualize `MENSAGENS` em `views_confirmacao.py` |
| Mudar o **lançamento** | `documentos/lancamento_nota.py`, `financeiro/servicos.py`, `documentos/analises.confirmar_analise` | Transação única; ordem F-3 → F-4 → movimento → identidade; teste de rollback e de concorrência |
| Mudar **pessoas/papéis** | `cadastros/models.py`, `resolucao.py`, `consultas.py`, `pendentes.py`, `views.py` | Identificação **só por documento**; nada reativa sozinho; `PROTECT` e sem exclusão |
| Mudar **classificações** | `cadastros/models.py`, `forms_classificacoes.py`, `views_classificacoes.py` | `tipo` e `codigo` imutáveis |
| Mudar **contas manuais** | `financeiro/manual.py`, `forms_manuais.py`, `views_manuais.py`, `conta_manual.js` | Idempotência por UUID + token assinado; a validação final é do serviço |
| Mudar **consulta de contas** | `financeiro/manual.listar_movimentos`, `views_consultas.py`, `forms_consultas.py` | Só leitura; 2 consultas para qualquer tamanho de página; `CONFIRMADO` ≠ `ATIVO` |
| Mudar **login/sessão** | `usuarios/demo.py`, `views.py`, `config/settings.py` | Login e logout nunca podem falhar por causa do banco; `session.flush()` só depois de descartar as análises |
| Mudar **configuração** | `config/settings.py`, `build.sh`, `start.sh` | Mudança de produção exige autorização específica; teste em subprocesso (`config/test_producao.py`) |
| Adicionar **rota** | `*/urls.py` + view | `@demo_login_required`, método permitido, CSRF, recusar campos extras; atualize [08](08-interface-e-rotas.md) |
| Adicionar **modelo/campo** | `*/models.py` + migration | Constraints no banco, imutabilidade se financeiro; migration **manual** em QA/PROD (ver [10](10-configuracao-e-operacao.md)) |

## 3. Invariantes que não podem quebrar

1. **Nada financeiro é gravado antes do "Confirmar" explícito**, e o sucesso só aparece depois do COMMIT.
2. **Toda gravação de movimento passa por `registrar_movimento()`** (validações, bloqueios, idempotência, gatilho).
3. **Tudo é revalidado no servidor** no momento de gravar: não confie na tela, nem no JSON dos Agents, nem em `validacoes` do JSON.
4. **Nada é excluído fisicamente**; "excluir" é inativar. Registros financeiros também não mudam campos essenciais.
5. **Uma pessoa = um documento** (CPF/CNPJ normalizado, único). Nunca identificar, deduplicar ou associar por nome.
6. **Nenhum cadastro é criado, reativado ou tem papel atribuído sem decisão explícita** (autorização do usuário). Decisão é autorização, não ordem.
7. **Pessoa incompleta não entra em lançamento**; documento fictício ou inválido nunca é guardado.
8. **Valores monetários são `Decimal`** (nunca `float`), com 2 casas, positivos e menores que R$ 10 bilhões; soma das parcelas = total.
9. **A mesma nota não é lançada duas vezes** (identidade fiscal e `analise_origem_id`); reenvio não duplica.
10. **A chave Gemini e o PDF nunca são persistidos nem logados**; mensagens e logs são fixos, sem valores nem documentos.
11. **Dados da análise só existem enquanto `PENDENTE`**; estado final nunca guarda dados.
12. **Pessoa/papel/classificação inativos não são usados em novos lançamentos** (e nada os reativa sozinho).
13. **Concorrência**: `select_for_update` em ordem de `pk`, índices únicos como árbitro, `transaction.atomic`.

## 4. Padrões de código do projeto

- **Idioma:** português do Brasil em nomes de domínio, comentários, docstrings e mensagens ao usuário.
- **Estilo local:** siga o código ao redor (nomes, densidade de comentário, convenções). Não crie um segundo padrão.
- **Comentários e docstrings** só para regra não óbvia; citam a decisão de origem (`DQ-xx`, `GR-xx`, `F-x`) quando existe.
- **Serviços:** dados de entrada/saída em `@dataclass(frozen=True)`; erros de negócio como `ValidationError(mensagem, code="codigo_estavel")`; uso indevido como `TypeError`/`ValueError`.
- **Views:** finas. Só HTTP, autenticação, método, montagem de contexto e tradução de erros. Sem regra de negócio.
- **Forms e Pydantic:** validação de entrada, cada um na sua camada; não reimplemente regra de domínio na view.
- **Preserve contratos existentes:** o JSON final, `ProcessamentoError`, os códigos de erro e os schemas dos Agents. Mudou? Atualize testes de contrato e [07](07-agents-e-contratos.md).
- **Mensagens ao usuário:** claras, curtas, em português, **sem detalhes internos**.
- **Não remova** código ou testes sem entender o propósito.

## 5. Receitas

### 5.1 Novo código de erro de regra
1. Levante `ValidationError(..., code="meu_codigo")` no serviço.
2. Adicione a mensagem fixa à tabela da view (`MENSAGENS` em `views_confirmacao.py`, ou o dicionário equivalente).
3. Teste o caso: o `code` e a mensagem (sem valores).
4. Atualize [04](04-regras-de-negocio.md).

### 5.2 Nova regra financeira (ex.: cancelar movimento, baixar parcela)
1. **Há contrato aprovado?** Cancelamento e baixa **não têm**. Pare e consulte a equipe; registre a decisão.
2. Operação **própria** (não `update()` direto), em `financeiro/` (serviço), com transação, bloqueio e idempotência.
3. Ajuste a imutabilidade (`campos_imutaveis`) só se o contrato exigir; mantenha o gatilho de soma coerente.
4. Migration (se houver), com plano de aplicação manual por ambiente.
5. Tela por último; só consulta/aciona o serviço.

### 5.3 Novo campo no cadastro (Pessoa/Classificação)
1. Campo + constraint (inclusive `IS NOT NULL` explícito se usar `CHECK`).
2. `clean_fields`/`save` se normaliza ou valida; mantenha `inativar/reativar` sem revalidar documento.
3. Forms, template, listagem/busca se aplicável.
4. Migration + carga de dados, se for o caso.
5. Revise `cadastros/resolucao.py` (F-4) e `consultas.py` se afeta identificação.

### 5.4 Nova rota de escrita
`@demo_login_required` → `@require_http_methods(["POST"])`/`["GET","POST"]` → `@sensitive_post_parameters()` se houver dado sensível → recusar campos extras/repetidos → serviço → redirecionar após sucesso (POST/Redirect/GET) → mensagem fixa em erro → botão com `data-submit-lock`.

### 5.5 Nova migration
Gere → revise o SQL → rode a suíte → `makemigrations --check` (com host fictício) → **aplicação manual** coordenada em QA e depois PROD ([10](10-configuracao-e-operacao.md)). Nunca no `build.sh`/`start.sh`.

### 5.6 Mudança no Agent
Mudou prompt, schema, modelo ou categorias? Rode `agents/` e `documentos/test_contrato_agents.py`; verifique `montar_resultado` e a versão do JSON; **teste com PDF fictício real e uma chave sua** (a suíte simula o SDK). Não altere modelos/categorias dos Agents para contornar falhas de integração.

## 6. Verificação (o que rodar e o que informar)

```bash
DJANGO_DEBUG=True python manage.py test <app ou módulo>     # componentes alterados
DJANGO_DEBUG=True python manage.py test                     # se tocou integração/contratos compartilhados
python manage.py check
DB_HOST=db-teste.invalid python manage.py makemigrations --check --dry-run
git diff --check
```

- Relate **o que foi executado e passou**, **o que falhou** e **o que não foi executado**. Não afirme que algo funciona sem evidência.
- Se mexeu em UI, **abra a tela** no navegador (a suíte não cobre navegador).
- Nunca rode testes destrutivos ou SQL contra bancos compartilhados ou de produção.

## 7. Ao terminar

- **Registre** o que foi feito no `ContextoProjeto.md`, na mesma branch, seguindo a estrutura das seções existentes (identificação, objetivo, implementação, arquivos, decisões, banco, testes, integração, pendências, Git). Não apague nem sobrescreva o histórico.
- **Atualize esta documentação** (`docs/documentacao/`) se mudou comportamento, regra, modelo, contrato, rota ou configuração.
- Matriz de requisitos, ADRs, README e `ContextoFluxoGit.md`: só quando houver mudança **consolidada**; edições pontuais.
- Revise os arquivos alterados à procura de **segredos** acidentais.
- Commit, push, PR para `develop`, merge e deploy são do responsável. Não os faça sem combinar.
- Não comece outra tarefa automaticamente.
