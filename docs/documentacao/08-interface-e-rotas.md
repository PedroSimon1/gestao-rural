# 08 — Interface e rotas

Interface em **Django Templates** com CSS e JavaScript locais (sem framework front-end). Todas as mensagens são em português do Brasil.
Fluxos completos em [05](05-fluxos.md).

## 1. Rotas

Montagem em `config/urls.py`: `/` → redireciona para `documento_inicio`; `usuarios.urls` na raiz; `documentos/`, `cadastros/`, `financeiro/` e `consulta/` com `include`.
**Só `/login/`, `/logout/` e `/saude/` são públicas.** As rotas de negócio têm `@demo_login_required`; as de escrita exigem POST e CSRF.
`/saude/` (GET/HEAD) responde `{"status": "ok"}` com o banco no ar e `{"status": "indisponivel"}` com 503 sem ele, sem expor o erro; serve ao health check do Render.

### 1.1 Autenticação (`usuarios`)

| URL | Nome | Métodos | Descrição |
| --- | --- | --- | --- |
| `/login/` | `login` | GET, POST | Formulário `login` + `senha`; autenticado vai para `/documentos/` |
| `/logout/` | `logout` | GET, POST | GET mostra a confirmação; **POST** encerra a sessão |

### 1.2 Documentos (`documentos`, prefixo `/documentos/`)

| URL | Nome | Métodos | Descrição |
| --- | --- | --- | --- |
| `/documentos/` | `documento_inicio` | GET | Tela de envio; o formulário envia para `analise_criar` |
| `analises/nova/` | `analise_criar` | POST | Valida chave + PDF, processa, cria a análise → redireciona para a conferência |
| `analises/<uuid>/` | `analise_conferencia` | GET, POST | Conferência; POST com `acao=salvar` ou `criar_classificacao` |
| `analises/<uuid>/salva/` | `analise_conferencia_salva` | GET, POST | Mesma view; GET exibe "correções salvas" |
| `analises/<uuid>/cancelar/` | `analise_cancelar` | POST | Cancela a análise e apaga os dados |
| `analises/<uuid>/confirmar/` | `analise_confirmar` | GET, POST | Resumo + autorizações; POST lança a nota |
| `analises/<uuid>/json/` | `analise_json` | GET | Baixa os dados extraídos originalmente (`.json`, nome com número, fornecedor e emissão); só a sessão dona, só enquanto PENDENTE |

### 1.3 Cadastros (`cadastros`, prefixo `/cadastros/`)

| URL | Nome | Métodos | Descrição |
| --- | --- | --- | --- |
| `pessoas/` | `pessoas` | GET | Lista/pesquisa (`modo=buscar` ou `todos`; `ordem`, `pagina`) |
| `pessoas/nova/` | `pessoa_nova` | GET, POST | Nome + documento + papéis |
| `pessoas/<id>/` | `pessoa_detalhe` | GET | Dados, papéis e ações |
| `pessoas/<id>/editar/` | `pessoa_editar` | GET, POST | Nome e (se completo) documento |
| `pessoas/<id>/papeis/` | `pessoa_atribuir_papel` | POST | Atribui um papel |
| `pessoas/<id>/regularizar/` | `pessoa_regularizar` | GET, POST | Completa o documento de um cadastro incompleto |
| `pessoas/<id>/status/<acao>/` | `pessoa_status` | GET, POST | `acao` ∈ `inativar`, `reativar` (outra → 404) |
| `pessoas/<id>/papeis/<papel_id>/<acao>/` | `papel_status` | GET, POST | Inativar/reativar **um papel** |
| `classificacoes/` | `classificacoes` | GET | Lista/pesquisa |
| `classificacoes/nova/` | `classificacao_nova` | GET, POST | Tipo + código + descrição |
| `classificacoes/<id>/editar/` | `classificacao_editar` | GET, POST | Só a descrição |
| `classificacoes/<id>/status/<acao>/` | `classificacao_status` | GET, POST | `inativar` / `reativar` |

### 1.4 Financeiro (`financeiro`, prefixo `/financeiro/`)

| URL | Nome | Métodos | Descrição |
| --- | --- | --- | --- |
| `contas/nova/` | `conta_manual_nova` | GET, POST | `?tipo=APAGAR` (padrão) ou `ARECEBER`; trocar o tipo abre novo formulário |
| `contas/` | `contas` | GET | Lista/pesquisa (`modo=buscar` ou `todos`) |
| `contas/<id>/` | `conta_detalhe` | GET | Detalhe do movimento: valor em aberto, nota fiscal (se houver) e baixa de cada parcela |
| `contas/parcelas/<id>/pagamento/` | `parcela_pagamento` | POST | `acao=registrar` + `data_pagamento` (não futura) ou `acao=desfazer`; volta ao detalhe |

### 1.5 Consulta (`consulta`, prefixo `/consulta/`)

| URL | Nome | Métodos | Descrição |
| --- | --- | --- | --- |
| `/consulta/` | `consulta` | GET, POST | Pergunta + modo Simples/Semântica + chave Gemini; resposta textual e fontes com links para as contas |
| `/consulta/indice/` | `consulta_indice` | POST | Atualiza um lote do índice com chave informada; reapresenta a tela com situação e mensagem |

**Navegação** (cabeçalho comum, `documentos/templates/documentos/base.html`): Contas · Consultar · Enviar nota · Pessoas · Classificações · Sair.
**Rodapé:** "Versão publicada: `<SHA>`" com link para o commit no GitHub, ou "não informada neste ambiente".

## 2. Templates e arquivos estáticos

| Template | Papel |
| --- | --- |
| `documentos/base.html` | Layout geral: topo com menu (página atual marcada por `aria-current`), link "Pular para o conteúdo", `<main id="conteudo">` e rodapé com o SHA; os demais apps estendem este |
| `cadastros/base.html` | Só estende o layout geral (o CSS é único) |
| `documentos/_cabecalho_pagina.html`, `_aviso.html`, `_campo.html` | **Componentes gerais**: cabeçalho de página (frase de apoio, trilha, ação principal); aviso (info, atenção, erro, ok); campo de formulário (rótulo, asterisco, dica e erro ligados ao campo; `pendencia` opcional marca o campo e mostra o motivo em texto) |
| `documentos/_topo_fluxo.html`, `_etapas.html`, `_ficha_nota.html` | **Padrão do fluxo "Enviar nota"** (envio, conferência, confirmação, concluído e mensagem de análise): topo com trilha, título e apoio à esquerda e as 4 etapas à direita (nomes longos, estado em texto: "Concluída", "N pendências", "Aguardando"); ficha da nota em uma linha (nota, fornecedor, faturado, total, parcelas) nas etapas 2 a 4. Toda tela do fluxo termina com a **barra de ações do rodapé** (`.acoes-rodape`): voltar ou cancelar à esquerda, estado no meio, ação principal à direita |
| `documentos/_situacao_secao.html`, `_consulta_cadastro.html`, `_parcelas_conferencia.html` | Peças da conferência: selo de situação ("N pendências" ou "Sem pendências"), situação de um cadastro consultado (em texto) e as parcelas em linhas |
| `documentos/inicio.html` | Envio da chave Gemini e do PDF (posta para `analise_criar`); mostra erro de processamento e limite de upload. "Processar" fica na barra do rodapé, dentro do formulário |
| `documentos/conferencia.html` | Conferência no padrão do fluxo, **por exceção**: o cartão **"Precisa da sua atenção"** traz só os campos pendentes (cada um com o motivo em texto) e o cartão **"Já conferido"** resume as 4 seções, cada uma com **Editar** (`<details>`, sem JavaScript) para os campos restantes. Cada campo aparece em um só lugar. Sem pendências, mostra "Tudo conferido". Consulta aos cadastros na linha de cada parte; JSON original sempre visível, em bloco escuro de altura limitada. A barra do rodapé tem Cancelar análise, o estado, Salvar correções e Revisar (bloqueado, com o motivo em `aria-describedby`, enquanto houver pendência). O Salvar vem antes do botão de cadastrar classificação, então o Enter salva |
| `documentos/pendencias_conferencia.py` | Só apresentação: junta os problemas da nota (F-3, por código) e os erros do formulário enviado e decide, por campo, se ele vai para "Precisa da sua atenção" ou para "Já conferido" (`resumir_pendencias`) |
| `documentos/resumo_nota.py` | Só apresentação: `ficha_da_nota` (linha de contexto) e `resumo_do_lancamento` (valor, parcelas e primeiro vencimento), a partir da nota já conferida, sem consulta nem escrita |
| `documentos/confirmacao.html` | Confirmação no padrão: dados da nota e parcelas lado a lado, cadastros, pendências (com a etapa em alerta), autorizações e a barra do rodapé (Voltar e corrigir / Confirmar lançamento financeiro) |
| `documentos/lancamento_sucesso.html` | Concluído: **resumo do lançamento** (conta a pagar, registro fiscal, valor, parcelas e primeiro vencimento) e a barra do rodapé (Enviar outra nota / Ver a conta lançada) |
| `documentos/analise_mensagem.html` | Mensagem de erro/estado de análise (cancelada, expirada, não encontrada…), como alerta, com o topo do fluxo sem etapas |
| `cadastros/pessoas.html`, `pessoa_form.html`, `pessoa_detalhe.html` | Telas de pessoas |
| `cadastros/classificacoes.html`, `classificacao_form.html` | Telas de classificações |
| `financeiro/contas.html`, `conta_manual.html`, `conta_detalhe.html` | Telas de contas (a de detalhe também exibe mensagens de erro de consulta) |
| `consulta/consulta.html` | Organizada em passos, cada um com texto curto de explicação: "1. Sua pergunta", "2. Como buscar as contas" (cada forma de busca com a sua descrição), "3. Chave do Gemini e envio", resposta e fontes (com legenda da pontuação ou do cosseno) e "Índice semântico": para que serve, um resumo do estado ("Índice em dia" ou "Índice incompleto", com quantas contas faltam entrar ou mudaram), as quatro contagens (contas no sistema, no índice, faltam entrar, mudaram; as duas últimas destacadas quando maiores que zero) e a seção "Atualizar o índice" (quando usar e o formulário separado). Estende `documentos/base.html` |
| `usuarios/login.html`, `logout.html` | Entrada e saída |

| Estático | Função |
| --- | --- |
| `documentos/documentos.css` | **Folha de estilo única** (visual formal e minimalista, ≈ 350 linhas): tokens, componentes, tabelas que viram lista de registros no celular |
| `documentos/documentos.js` | **Proteção visual contra clique duplo**: todo formulário POST tem `data-submit-lock`. No primeiro envio trava **o botão acionado** (`evento.submitter`, mesmo fora do `<form>` por `form="id"`) e troca o texto (`data-submit-texto` no botão ou no formulário); um segundo envio é ignorado. Botão com `name` (ex.: `acao=criar_classificacao`) fica com `aria-disabled` em vez de `disabled`: o navegador deixaria de enviar o valor de um botão desabilitado e a ação cairia em "salvar" (verificado no Chrome). O POST é um envio HTML normal; sem JS tudo funciona |
| `documentos/conferencia.js` | Na conferência: rola a página se a barra do rodapé cobrir o campo em foco (WCAG 2.4.11); abre o "Editar" de um campo que receba foco; mostra a soma das parcelas e o resumo **ao vivo** (ficha, linha das parcelas e aviso). Não escreve nos campos nem usa rede |
| `financeiro/conta_manual.js` | Adiciona linhas de parcela ao formulário manual (limite de 120) usando o `<template data-nova-parcela>` |

Tags de template: `{% situacao %}` (situação em texto com contorno), `{% secao_atual %}` (menu), filtro `moeda` (`R$ 1.234,56`).

Em produção os estáticos são servidos pelo WhiteNoise com manifesto (`CompressedManifestStaticFilesStorage`), o que **exige `collectstatic`**
(feito no `build.sh`). Em desenvolvimento e nos testes usa-se o storage simples. Por isso, rodar a suíte com `DJANGO_DEBUG=False`
dá erros "Missing staticfiles manifest entry".

## 3. Formulários

| Form | Arquivo | Campos principais | Observações |
| --- | --- | --- | --- |
| `LoginDemoForm` | `usuarios/forms.py` | `login` (≤ 150), `senha` (≤ 256, sem *strip*) | |
| `DocumentoUploadForm` | `documentos/forms.py` | `gemini_api_key` (≤ 256), `arquivo` | Chave em `PasswordInput` sem `render_value`; PDF por `validar_pdf` |
| `ConferenciaForm`, `ParcelaConferenciaForm` | `documentos/forms_conferencia.py` | campos da nota e parcelas | Só valida; não grava nem autoriza lançamento |
| `CamposFiscaisForm` | `documentos/forms_fiscais.py` | chave, modelo, série | Mensagens fixas (nunca refletem valores) |
| `ClassificacaoNaNotaForm` | `documentos/forms_classificacao_nota.py` | tipo, código, descrição | Reaproveita o cadastro administrativo, restrito a DESPESA |
| `ConfirmacaoLancamentoForm` | `documentos/forms_confirmacao.py` | `versao_correcoes`, decisões e cadastro incompleto de cada parte, `confirmar` | `solicitacao()` devolve a `SolicitacaoLancamento` |
| `NovaPessoaForm` / `PessoaForm` / `PapelForm` / `ConfirmacaoForm` / `RegularizacaoForm` / `PesquisaPessoaForm` | `cadastros/forms.py` | nome, documento, papéis, confirmação, busca | |
| `NovaClassificacaoForm` / `DescricaoClassificacaoForm` / `PesquisaClassificacaoForm` | `cadastros/forms_classificacoes.py` | tipo, código, descrição, busca | |
| `ContaManualForm` + `ParcelasManuaisFormSet` | `financeiro/forms_manuais.py` | tipo, UUID, token, contraparte, faturado, valor total, classificações, principal, parcelas, `confirmar`, `ciente_duplicidade` | Formset: mínimo 1, máximo 120, com remoção. `ciente_duplicidade` só aparece quando há conta parecida (409 até ser marcado) |
| `FiltroContasForm` | `financeiro/forms_consultas.py` | tipo, origem, situação, contraparte, classificação, pagamento (em aberto / quitado), por página, página | Inclui cadastros inativos |
| `PagamentoParcelaForm` | `financeiro/forms_pagamentos.py` | `acao` (registrar/desfazer), `data_pagamento` | Recusa data futura no serviço |
| `ConsultaForm` | `consulta/forms.py` | `pergunta` (≤ 500), `modo` (`simples`/`semantico`, widget `RadioComDescricao`: cada opção leva a descrição de `servico.Modo.descricao`), `gemini_api_key` | Simples é o padrão; chave em `PasswordInput`, retirada dos dados do formulário antes do template |
| `IndiceForm` | `consulta/forms.py` | `gemini_api_key` | Chave só para o lote; IDs próprios para não duplicar os campos da consulta |

Padrões comuns nas views de escrita: **recusar campos fora do formulário e campos escalares repetidos** ("Pedido inválido…"),
`@sensitive_post_parameters`, e traduzir códigos de erro em mensagens fixas.

## 4. Mensagens e estados da tela

| Situação | Comportamento |
| --- | --- |
| Tabela de pessoas/classificações/contas | **Abre vazia**; **Pesquisar** ou **TODOS** carregam |
| TODOS em cadastros | Só **ATIVOS** |
| TODOS em contas | Só **CONFIRMADOS** (estado financeiro, não "ativo") |
| Novo cadastro | Nasce ATIVO, **sem campo de status** |
| Edição | **Sem campo de status**; inativar/reativar é ação separada e confirmada |
| Inativar/reativar | Página de confirmação com o aviso de que vínculos e movimentos são preservados |
| Erro de banco em financeiro/documentos | Mensagem amigável (503) |
| Erro de banco em **cadastros** | Mensagem amigável (503), como em financeiro/documentos; erros inesperados mostram `500.html` e URL inexistente, `404.html` (M-03 corrigido) |
| Análise inexistente/de outra sessão | 404 "Análise não encontrada…" |
| Análise expirada/cancelada/confirmada | 409 com a mensagem do estado |
| Upload acima do limite | "O arquivo excede o limite de N MB." |

## 5. Ordenação, filtros e paginação

- **Pessoas**: ordem por nome, documento ou situação (clique no cabeçalho alterna ascendente/descendente); paginação de 30; busca `AND` por termo no nome ou no documento.
- **Classificações**: ordem por tipo, código, descrição ou situação; paginação de 30.
- **Contas**: ordem fixa do mais recente ao mais antigo (**não** ordena por coluna — UI-04 parcial); filtros combinados; 10/30/100 por página.
