# GR-16 — Auditoria integrada da N2 Etapa 2

27/10/2026. Referência Git: **`origin/develop` `aaa80cc`**, após PR #56.
O checkout do usuário foi preservado; análise/validação em exportação isolada.
Esta atualização documental ainda precisa de PR/revisão/integração.

## Método e significado dos estados

Foram confrontados rotas, formulários, modelos, serviços, migrations, testes,
scripts e documentos da base integrada com os critérios da matriz existente.
Não foram acessados `.env`/`Readme.txt` para exibir valores, QA/PROD, Render
ou Classroom. Helpers de teste usam apenas as credenciais locais em runtime,
sem copiá-las para a exportação nem registrá-las.

- **Implementado:** comportamento existe no código indicado.
- **Integrado:** está no commit `aaa80cc`, não apenas em pacote/branch de tarefa.
- **Validado localmente:** execução/teste observado no ambiente indicado.
- **Homologado/publicado/entregue:** exige evidência específica, ainda não fornecida.

Uma leitura do Jira em 27/10 mostrou GR-49 como Feito e GR-48 como pendente,
enquanto o código tem GR-49 parcial e interface GR-48 integrada. A divergência
foi registrada, sem mudar o Jira. Status do ticket não substitui evidência.

## O que está integrado

| Frente | Evidência e cobertura |
| --- | --- |
| Pessoas/Papéis | GR-46, PR #49: PF/PJ, múltiplos papéis, edição, status independente e regularização |
| Classificações | GR-47, PR #51: receita/despesa, descrição editável, identidade imutável, status e unicidade |
| Agents/JSON | GR-41/42 e GR-15, PR #52: PF/PJ, inconclusiva preservada, v1/v2, SDK simulado |
| Nota fiscal | PRs #45/46/48: análise por sessão, correções fiscais/principais preservadas, decisões e F-5 oficial |
| Segurança | GR-18, PR #53: log de erro fixo, upload limitado em memória, no-store, logout POST/CSRF e descarte |
| Consultas | GR-49 parcial, PR #54: filtros, detalhes, classificações e parcelas em leitura |
| Contas manuais | Backend PR #50 e interface PR #55: APAGAR/ARECEBER, principal, parcelas, confirmação e idempotência |
| FLU-07 | PR #56: criação explícita na conferência, preservação do rascunho e código fora do Enum aceito na correção até o lançamento |
| SHA publicado | Rodapé implementado; correspondência com deploy real não verificada |

As sete funcionalidades listadas pelo professor possuem interfaces básicas
de cadastro/registro no código. Isso não dispensa F-6, manutenção financeira,
limitações fiscais, homologação ou os demais critérios específicos.

## Lacunas reais e responsáveis

1. **F-6:** backend salva incompletos, mas não é idempotente nem ligado ao
   estado/versão da análise. Reprodução local: duas chamadas iguais criam
   duas pessoas, sem movimento. Simon define a operação oficial; Lopes integra.
   T-05 aprovada mantém prazo original, sem cancelamento/renovação.
2. **GR-39/49:** faltam serviço/HistóricoParcela e contratos de manutenção
   financeira. A tela mostra parcelas atuais, não histórico de alterações.
   Não existem botões ou gravações diretas fingindo edição/baixa/reativação.
3. **GR-20/50:** estado de migrations/QA/PROD não reverificado; migration
   financeiro/0004 precisa da confirmação de Simon no ambiente remoto.
4. **Limpeza:** comando existente é idempotente; agendamento ainda não instalado.
   Prazo de acesso de 30 minutos não garante apagamento físico naquele instante.
5. **Publicação/entrega:** URL atual, HTTPS, SHA implantado, testes em navegador,
   canal restrito e envio de links ao Classroom aguardam evidências humanas.

`origin/main` observado em `f7786e8`; não se inferiu a versão do Render a
partir disso. A publicação ainda precisa seguir o fluxo humano autorizado.

## Limites confirmados

NF-e 55/NFC-e 65 com emitente CNPJ no fluxo fiscal; outros casos são recusados.
Pessoas PF/PJ e papéis são independentes. Nota extraída não é corrigida
silenciosamente: dados/correções separados, sem valores/datas inventados.
O Classificador mantém duas categorias; correção humana pode usar código válido
do catálogo. Conta manual aceita múltiplas classificações e parcelas.

Modelos financeiros são protegidos contra alteração/exclusão direta. Status
CONFIRMADO/CANCELADO e ATIVA/CANCELADA não são estados de quitação.
Login demo compartilhado e cookies assinados não têm revogação central completa.

## Evidências novas desta auditoria

- **1.153 testes OK** sobre `aaa80cc`; PostgreSQL 18.6 local `127.0.0.1:55432`.
  Papel LOGIN/CREATEDB, sem SUPERUSER/CREATEROLE; banco descartável `test_*`
  ausente antes/depois; DB_HOST fictício no processo. Nenhum banco remoto acessado.
- `manage.py check`: OK. `makemigrations --check --dry-run`: sem alterações,
  histórico remoto bloqueado por host fictício.
- `check --deploy` local com DEBUG=False/host fictício: **W004 e W008**;
  saída 0 não é certificação de configuração do proxy/publicação.
- Diagnóstico F-6 separado: 1 teste OK comprovando dois cadastros em duas
  chamadas. Não integra nem aumenta a contagem da suíte versionada.
- Nenhuma instalação limpa, navegação em navegador, Gemini real, migração
  remota ou publicação foi executada por esta auditoria.

## Documentos corrigidos e sequência

README agora descreve instalação com PostgreSQL/TLS e migrations necessárias,
interfaces reais e pendências. Matriz registra a base atual sem equiparar
implementação à publicação. Contexto recebe auditoria completa; adendos antigos
permanecem datados como histórico. Contrato registra T-05/P-09 e o bloqueio F-6,
sem aprovar automaticamente a assinatura proposta. ADR mantém as decisões
arquiteturais e recebe apenas o estado de implementação verificado.

Revisar/integração desta GR-16 → Simon libera contrato F-6 e GR-39 → Lopes
integra as ações restantes → validação conjunta dos fluxos → publicação e
evidência de entrega. A documentação terá novo fechamento quando houver essas
evidências; não marcar todas as dependências como resolvidas por este PR.
