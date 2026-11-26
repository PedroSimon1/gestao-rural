# ADR-002 — Privacidade e dados pessoais (RASCUNHO)

> **Estado: PROPOSTA — NÃO APROVADA.** Este arquivo registra o que o código
> faz hoje com dados pessoais e as decisões que a equipe ainda precisa tomar
> (achado B-03 da [auditoria de 24/11/2026](../auditoria/Auditoria-2026-11-24.md)).
> Nada aqui é decisão da equipe até que Pedro Simon e Gustavo Lopes aprovem.
> A seção 2 descreve fatos verificados no código; a seção 3, perguntas abertas.

## 1. Identificação

| Item | Valor |
| --- | --- |
| Identificador | ADR-002 |
| Título | Privacidade e dados pessoais |
| Data do rascunho | 26/11/2026 |
| Decisores | Equipe do projeto (Pedro Simon e Gustavo Lopes) |
| Relaciona-se a | [ADR-001](ADR-001-supabase.md), [segurança e privacidade](../documentacao/09-seguranca-e-privacidade.md) |

## 2. Situação atual (fatos do código)

| Tema | Situação |
| --- | --- |
| CPF/CNPJ | Guardados em **texto simples** (`Pessoa.documento`, `NotaFiscalLancada.emitente_cnpj`), normalizados, únicos em `Pessoa`. Coerente com a decisão de 24/10/2026 |
| Nome/razão social | Texto simples em `Pessoa.razao_social` |
| Exclusão | Pessoas só são inativadas e reativadas; movimentos financeiros recusam `update`/`delete` diretos. Não existe fluxo de exclusão ou anonimização |
| PDF da nota | Lido só em memória, sem gravar em disco ou banco (`documentos/uploads.py`) |
| Envio a terceiro | O conteúdo do PDF é enviado ao Google Gemini com a chave informada pelo usuário na tela; a chave não é guardada nem lida do ambiente |
| Dados extraídos | Ficam em `AnalisePendente` até a confirmação, o cancelamento ou a expiração (30 minutos); na expiração os dados são apagados, mas a limpeza só roda ao criar nova análise ou com `manage.py expirar_analises` (sem agendamento) |
| Respostas HTTP | `no-store` em toda resposta dinâmica (`config/privacidade.py`) |
| Logs | Texto fixo nas falhas de processamento; o formatador de produção omite a mensagem das exceções (`config/logs.py`) |
| Aviso ao usuário | Não há aviso de privacidade, registro de base legal nem de prazo de retenção no repositório |
| Consentimento | Só no fluxo F-6 (cadastro pendente), que não está ligado à tela |

## 3. Decisões em aberto (a equipe)

| ID | Pergunta | Opções conhecidas |
| --- | --- | --- |
| PRIV-01 | Manter CPF/CNPJ em texto simples? | (a) manter, documentando o motivo; (b) criptografia de campo com chave fora do banco, o que impede busca parcial e a unicidade direta, a menos que se guarde também um hash determinístico |
| PRIV-02 | Qual a base legal e o prazo de retenção dos cadastros e movimentos? | Depende do uso real (a demonstração acadêmica usa dados fictícios) |
| PRIV-03 | O envio do PDF ao Gemini precisa de aviso na tela? | Texto curto na tela de envio informando que o arquivo vai a um serviço de terceiro |
| PRIV-04 | Como atender pedido de exclusão/anonimização de uma pessoa? | Hoje só há inativação; anonimizar exigiria exceção às regras de integridade dos movimentos |
| PRIV-05 | O ambiente de homologação pode receber dados reais? | Hoje o ADR-001 (T-06) diz: só dados fictícios ou próprios para homologação |

## 4. Consequências da aprovação

Cada decisão aprovada vira tarefa própria (aviso na tela, política de retenção, migration de criptografia ou anonimização) e atualiza este ADR, o
[`ContextoProjeto.md`](../../ContextoProjeto.md) e o README. Até lá, o projeto
continua operando como descrito na seção 2.
