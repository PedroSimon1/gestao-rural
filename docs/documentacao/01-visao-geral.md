# 01 — Visão geral

## 1. Problema

Um produtor rural (o pai) e dois filhos precisam controlar as **contas a pagar e a
receber** da propriedade. Despesas e receitas podem ser faturadas no nome de qualquer
um dos três. A documentação chega **por e-mail, em PDF** (notas fiscais, contratos de
venda da produção, comprovantes). Compras, vendas e pagamentos são **parcelados**, e
uma parcela pode ser quitada por vários depósitos parciais.

Os usuários têm pouca escolaridade e **exigem a menor intervenção humana possível**
(Documento de Requisitos do Cliente, DR 0001/2026).

## 2. Propósito

Sistema de gestão financeira rural que **processa PDFs com IA**, identifica pessoas e
classificações, **registra movimentos financeiros e suas parcelas** e permite **manter
os cadastros com inativação lógica** (nada é excluído).

Projeto acadêmico (ESW424, UniRV) de **Pedro Simon** e **Gustavo Lopes**.

## 3. Escopo

| Escopo | Conteúdo | Situação |
| --- | --- | --- |
| Etapa 1 | PDF → Extrator → Classificador → JSON na tela, login de demonstração, hospedagem | Entregue |
| Etapa 2 | Banco de dados, consultas de existência, criação de pessoas/classificação/movimento/parcelas, cadastros com inativação, versão do GitHub na tela | Implementada e integrada em `develop`; ver [12](12-pendencias-e-riscos.md) para o que falta |
| Sistema completo (visão do cliente) | Ingestão por e-mail, quitação fracionada e amortizações, painel, alertas, conciliação, autenticação real | **Planejado; fora do código atual** |

## 4. O que o sistema faz hoje

1. Exige um **login de demonstração** (um único par de credenciais do ambiente).
2. Recebe o **PDF de uma nota fiscal** e uma **Gemini API Key** digitada na tela a cada
   processamento (a chave nunca é guardada).
3. **Extrai** os dados da nota (Agent Extrator) e **classifica** a despesa (Agent Classificador),
   ambos via Google Gemini.
4. Guarda o resultado como **análise pendente** no servidor (30 minutos) e abre a **conferência**:
   mostra o que já existe no banco ("EXISTE – ID n" / "NÃO EXISTE"), aponta pendências e permite **corrigir** campos.
5. Na **confirmação**, o usuário autoriza explicitamente criar/reativar/atribuir cadastros;
   o sistema **revalida tudo** e grava, em **uma única transação**, pessoas, movimento a pagar,
   classificação, parcelas e identidade fiscal da nota. Só então exibe o sucesso.
6. Permite **registrar contas manuais** (a pagar ou a receber), sem nota, com várias
   classificações (uma principal) e várias parcelas.
7. Permite **consultar contas** (filtros, lista, detalhe com classificações e parcelas).
8. Permite **manter pessoas, papéis e classificações**, com inativar/reativar, sem exclusão física.
9. Mostra no rodapé o **SHA do commit publicado** (quando a plataforma o informa).

## 5. O que o sistema ainda não faz

- **Cadastro pendente pelo botão da tela** (F-6): o serviço existe, mas não é idempotente e não está ligado à tela.
- **Manutenção financeira**: editar, cancelar ou dar baixa em movimentos/parcelas; histórico de parcelas (GR-39/49).
- **Quitação, amortização, saldo**, painel, alertas, conciliação e ingestão por e-mail.
- **Classificação de RECEITA pelo Agent**: o Agent só trata despesas; contas a receber nascem só pelo fluxo manual.
- **Mais de uma classificação por nota**: o fluxo da nota usa a classificação sugerida (ou escolhida) como única e principal; várias classificações só existem no fluxo manual.
- **Notas que não sejam NF-e (55) ou NFC-e (65)** com emitente CNPJ no fluxo fiscal.
- **Usuários reais**, perfis e permissões: só existe o login compartilhado de demonstração.

## 5.1 Estados de entrega

Implementado, integrado, validado localmente, homologado e publicado são coisas diferentes.
Em 24/11/2026 (auditoria), constam: código integrado em `develop` e `main` (árvores idênticas na
referência da auditoria), 1.153 testes aprovados no PostgreSQL local, **sem** verificação de
homologação, URL pública, migrations em QA/PROD nem entrega no Classroom.

## 6. Tecnologias

| Tecnologia | Versão (arquivo) | Uso |
| --- | --- | --- |
| Python | 3.14 (`.python-version`) | Linguagem |
| Django | 6.1.3 (`requirements.txt`) | Framework web, ORM, migrations, templates |
| PostgreSQL | 18.6 no ambiente de testes local; Supabase em homologação/produção | Persistência (ADR-001) |
| Psycopg | 3.3.6 (`psycopg[binary]`) | Driver PostgreSQL |
| Google Gemini (`google-genai` 2.24.0) | Modelo definido por `GEMINI_MODEL` | Extração e classificação |
| Pydantic | 2.13.5 | Schemas e validação das respostas dos Agents |
| Gunicorn | 26.2.0 | Servidor de produção |
| WhiteNoise | 6.12.0 | Arquivos estáticos em produção |
| python-dotenv | 1.2.3 | Leitura do `.env` |
| Render | — | Hospedagem do Web Service |
| HTML, CSS e JS locais | — | Interface (Django Templates, sem framework front-end) |

**Não use** React, Next.js, Django REST Framework, outro banco, Docker ou outro framework sem uma
decisão de arquitetura aprovada pela equipe.

## 7. Glossário

| Termo | Significado |
| --- | --- |
| **Pessoa** | Cadastro de alguém identificado por CPF ou CNPJ (fornecedor, cliente, faturado) |
| **Papel** | Função de uma pessoa: `FORNECEDOR`, `CLIENTE` ou `FATURADO`. Uma pessoa pode ter vários |
| **Fornecedor** | Emitente da nota (quem vende); contraparte de uma conta a pagar |
| **Faturado** | Destinatário da nota (em nome de quem a despesa é faturada) |
| **Cliente** | Contraparte de uma conta a receber |
| **Classificação** | Tipo de despesa ou de receita (`tipo` + `codigo`), ex.: `MANUTENCAO_E_OPERACAO` |
| **Movimento** (`MovimentoConta`) | Uma conta a pagar (`APAGAR`) ou a receber (`ARECEBER`) |
| **Parcela** (`ParcelaConta`) | Parte do movimento, com número, vencimento e valor |
| **Análise pendente** (`AnalisePendente`) | Resultado do processamento da nota guardado no servidor entre o processamento e a confirmação |
| **Conferência** | Tela onde o usuário revisa e corrige os dados da análise |
| **Confirmação** | Ato explícito que dispara o lançamento financeiro |
| **Identidade fiscal** | Chave de acesso, ou CNPJ do emitente + modelo + série + número, que identifica uma nota e impede lançamento duplicado |
| **Cadastro incompleto / pendente** | Pessoa sem CPF/CNPJ válido; não pode ser usada em lançamento até ser regularizada |
| **Regularizar** | Completar um cadastro incompleto com um documento válido, no mesmo registro |
| **Inativar / reativar** | "Excluir" e "desfazer a exclusão" lógicas, mudando `status` |
| **Idempotência** | Repetir a mesma solicitação não duplica o resultado |
| **JSON final** | Dicionário devolvido por `montar_resultado()` (v1: 10 chaves; v2: 11 chaves) |
| **Demo / login de demonstração** | Autenticação por um par `DEMO_LOGIN`/`DEMO_PASSWORD`, sem tabela de usuários |
