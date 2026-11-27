# 03 — Requisitos

Os identificadores **RF-01 a RF-17** e **RNF-01 a RNF-09** são os das seções 5 e 6 do
`ContextoProjeto.md`; aqui a **situação foi atualizada com o código integrado**
(as seções 5 e 6 do `ContextoProjeto.md` ainda mostram RF-08 a RF-14 como "não implementado",
o que já não vale). Os identificadores **RF-18 a RF-22** e **RNF-10 a RNF-13** foram
**acrescentados nesta documentação** para cobrir comportamentos que existem no código e não tinham ID.

A rastreabilidade acadêmica completa (FUN, FLU, RN, ENT, UI, DEL, PT) está em
[`docs/requisitos/matriz-n2-etapa2.md`](../requisitos/matriz-n2-etapa2.md).

Legenda de situação: **Atendido** (implementado e testado localmente), **Parcial**, **Não atendido**, **Fora do escopo atual**.

## 1. Requisitos funcionais

| ID | Requisito | Matriz | Situação | Onde está |
| --- | --- | --- | --- | --- |
| RF-01 | Receber o PDF de uma nota fiscal pela Web | BASE-01 | Atendido | `documentos/forms.py`, `validators.py`, `uploads.py`, `views_analises.analise_criar` |
| RF-02 | Extrair fornecedor, faturado, número, data, itens, parcelas e valor total | BASE-01 | Atendido (testes com Gemini simulado; precisão com PDF real não homologada) | `agents/extrator/` |
| RF-03 | Classificar o tipo de despesa por IA a partir dos itens | BASE-01 | Atendido (2 categorias); inconclusiva preserva a extração | `agents/classificador/`, `documentos/processamento.py` |
| RF-04 | Exibir o resultado (JSON, resumo, justificativa) | BASE-01 | Atendido (tela de conferência mostra "Dados extraídos originalmente") | `documentos/templates/documentos/conferencia.html` |
| RF-05 | Consultar no banco se o **fornecedor** existe | FLU-01 | Atendido | `cadastros/consultas.consultar_pessoa` |
| RF-06 | Consultar no banco se o **faturado** existe | FLU-02 | Atendido | idem |
| RF-07 | Consultar no banco se a **classificação de despesa** existe | FLU-03 | Atendido | `cadastros/consultas.consultar_classificacao` |
| RF-08 | Exibir o resultado das consultas ("EXISTE – ID n" / "NÃO EXISTE") | FLU-04 | Atendido | `documentos/views.py::_linhas_consultas`, tela de conferência e de confirmação |
| RF-09 | Criar fornecedor, faturado e classificação inexistentes | FLU-05, 06, 07 | **Parcial**: pessoas completas e classificação são criadas com decisão explícita; **cadastro incompleto pelo botão da tela (F-6) não** | `cadastros/resolucao.py`, `documentos/views_analises.py` (criar classificação) |
| RF-10 | Criar o movimento (APAGAR) e suas parcelas | FLU-08, 09 | Atendido | `financeiro/lancamento_nota.py`, `financeiro/servicos.py` |
| RF-11 | Informar ao usuário que o lançamento foi concluído | FLU-10 | Atendido (só depois do COMMIT) | `documentos/views_confirmacao.py`, `lancamento_sucesso.html` |
| RF-12 | Manter Fornecedor / Cliente / Faturado (`PESSOAS`) | FUN-01, 02, 03 | Atendido (incluir, consultar, editar, inativar, reativar; vários papéis) | `cadastros/views.py` |
| RF-13 | Manter Tipo de Receita / Tipo de Despesa (`CLASSIFICACAO`) | FUN-04, 05 | Atendido (tipo e código imutáveis; descrição e status editáveis) | `cadastros/views_classificacoes.py` |
| RF-14 | Registrar Contas a Pagar e a Receber | FUN-06, 07 | Atendido pelo fluxo manual (uma ou mais classificações, uma principal; várias parcelas) | `financeiro/views_manuais.py`, `manual.py` |
| RF-15 | Mostrar o código do último commit publicado na tela principal | DEL-05 | **Parcial**: o rodapé mostra o `RENDER_GIT_COMMIT` quando existe; falta comparar com o deploy real | `documentos/templatetags/versao_publicada.py`, `base.html` |
| RF-16 | Login para acessar o sistema hospedado | — | Atendido (login de demonstração único) | `usuarios/` |
| RF-17 | Ingestão de PDF por e-mail, amortizações, painel, alertas, conciliação | — | **Fora do escopo atual** (planejado pelo cliente) | — |
| RF-18 | Conferir e **corrigir** os dados extraídos antes de confirmar, com revalidação no servidor | DQ-11 | Atendido (campos fechados em `CAMPOS_CORRIGIVEIS`) | `documentos/correcoes.py`, `conferencia.py`, `interface_conferencia.py` |
| RF-19 | **Cancelar** uma análise (apaga os dados da nota) | DQ-09 | Atendido | `views_analises.analise_cancelar`, `analises.cancelar_analise` |
| RF-20 | **Impedir lançar a mesma nota duas vezes** (identidade fiscal e idempotência da análise) | DQ-10, 15 a 18 | Atendido | `financeiro/identidade_fiscal.py`, `NotaFiscalLancada`, `analise_origem_id` único |
| RF-21 | **Consultar contas** (lista com filtros e detalhe com classificações, parcelas, valor em aberto e nota fiscal) e **dar baixa** em parcela (paga/recebida, com desfazer) | GR-49, D1 | **Parcial**: consulta e baixa simples; sem editar, cancelar movimento/parcela, pagamento parcial ou histórico | `financeiro/views_consultas.py`, `financeiro/views_pagamentos.py`, `financeiro/pagamentos.py` |
| RF-22 | Criar uma **classificação de despesa** durante a conferência, sem perder o rascunho | FLU-07 | Atendido | `views_analises.analise_conferencia` (ação `criar_classificacao`) |

### 1.1 Pendente de confirmação (dúvidas de escopo)

| ID | Dúvida | Decisão atual |
| --- | --- | --- |
| Q-01 | As telas CRUD completas de **todas** as funcionalidades "Manter/Registrar" são obrigatórias? | A equipe priorizou o fluxo da nota e **também** implementou os cadastros; o professor não respondeu |
| Q-05 | Quais categorias valem, e como o Enum do Classificador corresponde ao cadastro? | O `codigo` espelha o Enum; só 2 categorias de DESPESA existem na carga inicial; categorias do cliente e de RECEITA sem lista aprovada |
| Q-06 | O Classificador deve devolver mais de uma classificação por nota? | Sem decisão; hoje devolve uma |
| Q-10 | Contas a receber entram no fluxo automático? | Não; só pelo fluxo manual |

## 2. Requisitos não funcionais

| ID | Requisito | Situação | Evidência |
| --- | --- | --- | --- |
| RNF-01 | Simplicidade visual e linguagem direta (usuários de baixa escolaridade) | Atendido na interface atual (telas em português, mensagens por código) | Templates, `MENSAGENS` em `views_confirmacao.py`, `SUGESTOES_ERRO` em `views.py` |
| RNF-02 | Mínima intervenção manual | **Parcial**: extração e classificação são automáticas; a confirmação é manual por decisão (DQ-02); sem e-mail | Fluxo em [05](05-fluxos.md) |
| RNF-03 | Mensagens claras, sem códigos técnicos nem dados internos | Atendido (mensagens fixas por código de erro; sem traceback, sem valores, sem documentos) | `ProcessamentoError`, `mensagem_validacao` |
| RNF-04 | Consistência aritmética dos valores monetários | Atendido: `Decimal`, 2 casas, positivo, teto < R$ 10 bi; soma das parcelas = total, conferida também no banco | `financeiro/servicos.py`, gatilho `0002` |
| RNF-05 | Sistema hospedado e acessível | **Não reverificado** (Render, registrado em 29/09/2026) | [10](10-configuracao-e-operacao.md) |
| RNF-06 | Segurança de credenciais e da chave de IA | Atendido no código (ver [09](09-seguranca-e-privacidade.md)); HSTS/HTTPS e Data API do Supabase dependem de verificação humana | `config/settings.py`, `usuarios/demo.py` |
| RNF-07 | Cadastros e registros financeiros nunca excluídos fisicamente | Atendido no código (ORM recusa `delete`; FKs `PROTECT`) | `SemExclusaoQuerySet`, `RegistroFinanceiro` |
| RNF-08 | Tempo de processamento | **Sem métrica definida**; pior caso técnico ≈ 7 minutos com 1 worker | `start.sh`, `GEMINI_*` |
| RNF-09 | Custo zero de infraestrutura | **Pendente de confirmação** (Render Free; plano do Supabase a definir) | ADR-001 |
| RNF-10 | **Integridade e concorrência**: duas confirmações simultâneas ou um reenvio não duplicam; inativação concorrente não passa entre validação e gravação | Atendido: `select_for_update`, índices únicos, transação única | `financeiro/servicos.py`, `documentos/analises.py` |
| RNF-11 | **Privacidade**: nenhum PDF ou chave em disco/log; respostas dinâmicas sem cache; dados da nota apagados ao encerrar a análise | Atendido; limites conhecidos em [09](09-seguranca-e-privacidade.md) | `config/privacidade.py`, `documentos/uploads.py` |
| RNF-12 | **Testabilidade**: suíte com banco real isolado, sem tocar bancos compartilhados | Atendido: 1.153 testes (auditoria de 24/11/2026) | [11](11-testes.md) |
| RNF-13 | **Rastreabilidade**: decisões e histórico documentados por tarefa | Atendido por `ContextoProjeto.md` e `docs/`; seções antigas defasadas | [12](12-pendencias-e-riscos.md) |

## 3. Critérios de aceite resumidos do fluxo principal (FLU-01 a FLU-10)

1. Após a extração, consulta-se o banco: fornecedor, faturado e classificação existem?
2. A tela mostra o nome, o documento quando houver e "EXISTE – ID n" ou "NÃO EXISTE".
3. O usuário confere/corrige e confirma explicitamente.
4. Cadastros inexistentes são criados **só com a autorização correspondente**.
5. Cria-se o movimento a pagar, ligado ao fornecedor, ao faturado e à classificação.
6. Criam-se as parcelas, cuja soma é o valor total.
7. Se qualquer passo falhar, **nada** é gravado e a análise continua pendente.
8. O sucesso só aparece depois do COMMIT.
