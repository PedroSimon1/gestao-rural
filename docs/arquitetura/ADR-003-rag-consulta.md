# ADR-003 — Consulta ao banco com RAG (N3, Etapa 3)

> **Estado: PROPOSTA — decisões tomadas por Pedro Simon em 27/11/2026 para a entrega da N3; ainda sem aprovação formal da equipe (Gustavo Lopes).** Não substitui o ADR-001 (Supabase) nem decide o ADR-002 (privacidade).

## 1. Identificação

| Item | Valor |
| --- | --- |
| Identificador | ADR-003 |
| Título | Consulta ao banco com RAG (busca simples e busca semântica) |
| Data | 27/11/2026 |
| Origem | `PROJETO ADMINISTRATIVO - N3 - Etapa 3` (entrega 02/12/2026) e aula "RAG" |
| Relaciona-se a | [ADR-001](ADR-001-supabase.md), [ADR-002](ADR-002-privacidade-dados-pessoais.md) |

## 2. Contexto

A N3 pede uma tela para perguntas sobre o banco de dados, com resposta elaborada por um LLM: **RAG simples** (recuperação literal) e **RAG com embeddings** (recuperação semântica). O RAG tem três passos: recuperar registros relevantes, injetá-los no prompt e gerar a resposta com o Gemini.

## 3. Decisões

| ID | Decisão | Alternativas descartadas |
| --- | --- | --- |
| D-1 | Vetores em `JSONField` no próprio PostgreSQL; cosseno calculado em Python puro | pgvector (extensão e dependência novas), FAISS/Chroma (disco efêmero no Render) |
| D-2 | A Gemini API Key continua informada na tela a cada uso e nunca armazenada (D6 do projeto) | variável de ambiente no servidor; guardar na sessão |
| D-3 | Indexação por ação explícita ("Atualizar índice"), em lotes limitados (`RAG_LOTE_INDEXACAO`); a consulta semântica avisa quantos movimentos ainda não têm índice | indexar dentro da consulta (risco de estourar o timeout do worker único e a cota do Gemini) |
| D-4 | Itens da nota persistidos em `itens_notas_fiscais` (`ItemNotaFiscal`); notas lançadas antes da mudança não têm itens e não há como recuperá-los (o PDF não é guardado) | `JSONField` na nota; não persistir |
| D-5 | Uma tela `/consulta/` com seletor de modo (Simples ou Semântica) | duas telas; comparação lado a lado |
| D-6 | App `consulta/` e `agents/rag/`; `financeiro`, `cadastros` e `documentos` não importam `consulta` | colocar o RAG em `financeiro/` (violaria `config/test_arquitetura.py`) |
| D-7 | Embedding `gemini-embedding-001`, 768 dimensões, `RETRIEVAL_DOCUMENT` na indexação e `RETRIEVAL_QUERY` na pergunta, vetor normalizado L2 pelo cliente | `gemini-embedding-2`: agrega as entradas de uma chamada em **um** vetor, o que inviabiliza o lote; o cliente recusa esse modelo |
| D-8 | Contexto enviado ao Gemini: o mínimo, **sem CPF/CNPJ**; dados do banco e dos itens tratados como não confiáveis no prompt (vêm de PDF e de LLM). O aviso curto na tela, previsto na primeira versão, foi **retirado em 27/11/2026**: não é exigido pela atividade e o ADR-002 (PRIV-03) segue em aberto | enviar documentos completos |

## 4. Consequências

- Mudança de banco: `itens_notas_fiscais` (financeiro 0007 e 0008, com RLS) e, na Etapa 2, `embeddings_movimentos` (consulta, com RLS). As migrations são aplicadas manualmente em cada ambiente (PT-06).
- Configuração nova (só texto, validada no ponto de uso): `GEMINI_MODELO_EMBEDDING`, `GEMINI_DIMENSAO_EMBEDDING`, `RAG_TOP_K`, `RAG_LOTE_INDEXACAO`.
- Limite conhecido do RAG: o top-k traz só alguns registros, então perguntas de agregação ("total gasto no mês") ficam imprecisas.
- Revisitar D-1 se o índice passar de alguns milhares de vetores ou a consulta passar de ~1 s.
- O ADR-002 continua em aberto: o envio de contexto ao Gemini reforça PRIV-03 (aviso ao usuário) e PRIV-05 (só dados fictícios em homologação).
