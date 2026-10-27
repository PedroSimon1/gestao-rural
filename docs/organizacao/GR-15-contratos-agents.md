# GR-15 — Regressões dos Agents e contratos JSON

27/10/2026. Base `develop` `962140c` (PR #50). Entrega de testes de Lopes,
preparada separadamente da GR-47, que ainda não estava integrada ao iniciar.
Validada localmente; integração via PR, homologação e publicação pendentes.

## Cobertura e critérios do Jira

| Critério | Evidência nova em `documentos/test_contrato_agents.py` |
| --- | --- |
| PF/PJ, conclusiva e inconclusiva | Matriz v1/v2 × faturado PF/PJ × duas categorias; inconclusiva preserva extração e justificativa; emitente PF e documentos ambíguos preservados |
| Compatibilidade com JSON anterior | v1 padrão continua com dez chaves; v2 explícita com onze; serialização JSON, datas e dinheiro; schemas reais selecionados |
| API/rede distintas de inconclusiva | Timeout, conexão e API 503 nas duas etapas geram `ProcessamentoError`; JSON malformado/schema inválido usam os códigos vigentes de cada etapa |
| Mocks sem consumo real | Somente a criação do SDK externo é simulada; cliente Gemini, Agents, parsing e Pydantic são reais; transporte HTTP possui uma segunda barreira |
| Regressões da Etapa 1 | Testes existentes preservados integralmente e executados junto aos novos; nenhuma expectativa anterior foi enfraquecida |

São **12 testes novos**, com matrizes em subtestes. A execução dirigida
`manage.py test agents documentos.test_contrato_agents documentos.test_processamento documentos.test_classificacao_pendente`
passou em **205 testes**. A suíte completa passou em **1.079 testes**.
Check OK; `makemigrations --check --dry-run` sem alterações. Somente banco
descartável PostgreSQL local, ausente antes/depois; sem QA/PROD ou migrations remotas.

## Composição exercitada

Bytes PDF sintéticos → `processar_pdf()` → cliente Gemini real → SDK simulado
→ Extrator real/Pydantic → Classificador real/Pydantic → JSON final.

O teste confere que um só cliente atende as duas etapas, usa a chave fictícia
explícita e transmite ao Classificador apenas o contexto necessário, sem CPF,
CNPJ, identidade fiscal ou chave de API. Verifica também valores financeiros
ausentes em v2, aviso de DV inválido sem correção inventada e documento
ilegível bloqueado antes de qualquer solicitação de conteúdo ao provedor.

## Limites

Nenhum código de produção, schema, prompt, dependência ou migration alterado.
A comparação ao arquivo JSON Schema cobre suas chaves publicadas, não uma
validação genérica de todas as regras JSON Schema; a tipagem usa os schemas
Pydantic reais. A API externa e a qualidade de extração de PDFs reais não
foram homologadas. Não há confirmação financeira nesta bateria isolada;
os testes transacionais existentes continuam na suíte completa.

Os totais referem-se à base citada, sem somar a GR-47 ainda pendente naquela
base. Depois de reunir novos PRs, executar a suíte conjunta e registrar
nova evidência. No Jira, GR-15 apoia GR-19 e GR-50; fechar somente depois
da revisão e integração exigidas pelo Definition of Done.
