# JSON fiscal v2 — proposta exata para revisão Simon/Lopes

Base: develop `369b041`, após PR #39 (integração GR-45/GR-43).
Diretrizes de evolução, G-01 e política P-09 aprovadas por Simon e encaminhadas
por Gustavo nesta conversa. **Simon aprovou a estrutura, nomes e compatibilidade, com total e valor de parcela anuláveis. Ajustes incorporados; ativação ainda depende do backend.**
Este incremento implementa emissão v2 somente por opção explícita; as rotas continuam emitindo v1 até compatibilidade do backend.

## Estrutura proposta

O arquivo JSONFiscalV2.schema.json é o schema completo da saída JSON de
montar_resultado/armazenamento. Não é o response_schema do Gemini: dinheiro e
quantidades no JSON final são strings; validacoes é calculado pelo servidor.
JSONFiscalV2.exemplo.json contém apenas dados fictícios de teste e não é uma nota.

- Preservar as dez chaves atuais, seus nomes e tipos, acrescentando documento_fiscal.
- documento_fiscal contém chave_acesso, modelo e serie (strings ou null).
- **Número canônico:** numero_nota existente. Não duplicar em documento_fiscal.numero.
- **Emitente canônico:** fornecedor.cnpj existente. Não duplicar emitente_cnpj no bloco.
- Acrescentar fornecedor.cpf; preservar fornecedor.cnpj e faturado.cpf/cnpj.
- validacoes mantém as três entradas atuais e acrescenta fornecedor_cpf e chave_acesso.
- Todos os campos da saída existem; ausência é null, listas vazias continuam listas.
- Valores financeiros preservam strings decimais; datas ISO, categoria atual ou null.
- Quantidade_parcelas continua derivada do tamanho de parcelas.
- documento_e_nota_fiscal continua exclusivo da extração; justificativa continua fora
  do JSON armazenado. Retê-la exigiria outra extensão expressamente combinada.

## Extração, validação e correção

Não preencher modelo 55 por padrão, nem derivar documentos de papéis. Preservar
os dados efetivamente lidos e não copiar CNPJ entre as partes. Se CPF e CNPJ
forem possíveis para a mesma parte, exigir escolha explícita na conferência.

Modelo/série/número são preservados como texto lido. Chave ausente é null; chave
presente mas inválida permanece disponível para correção, sem completar/corrigir
DV. O limite estrutural de chave é 200 caracteres para permitir mostrar uma leitura
malformada. A chave válida deve atender ao serviço oficial (44 posições, inclusive
o suporte alfanumérico já implementado); não restringir erroneamente a 44 dígitos.

validacoes.chave_acesso informa apenas formato/DV pelo validador oficial do backend;
não comprova existência da nota nem consistência com campos separados. Divergência,
modelos não suportados, insuficiência e duplicidade são avaliados pela GR-22/F-3 e
devem bloquear confirmação. Não implementar outro algoritmo fiscal nos Agents.

O schema valida transporte/estrutura: não comprova soma, positividade financeira,
sequência de parcelas, DV documental, permissões ou possibilidade de lançamento.
Essas regras continuam nos validadores oficiais, reexecutados na confirmação.

**G-01 aprovada:** chave_acesso, modelo, serie e numero_nota editáveis na conferência,
em correcoes separadas de dados. Proposta de nomes planos: chave_acesso e modelo
(novos), serie e numero_nota (já existentes). Para v1 ou v2, nenhuma correção
modifica os extraídos. A F-3 combina as correções e chama identificar_nota.
Chave inválida ou divergente bloqueia; sem chave, CNPJ + modelo + série + número
são obrigatórios. Preservar constraints e confirmação transacional explícita.

## Compatibilidade P-09 aprovada

Análises v1 já armazenadas continuam acessíveis até expirar em 30 minutos.
Não rejeitar por serem v1, não reiniciar o prazo e não converter o JSON original
silenciosamente. Informações fiscais faltantes são preenchidas como correções.
As regras oficiais ainda impedem confirmar identidade insuficiente.

Proposta de implementação para revisão: novos processamentos emitem v2 somente
quando os consumidores estiverem integrados. versao_dados distingue 1/2 no model,
fora do corpo JSON, que preserva as dez chaves atuais + documento_fiscal na v2.
criar_analise aceita exatamente o conjunto de chaves v1 ou v2 na transição e
atribui sua versão; obter_analise/F-3 entendem ambas. Não aceitar versões futuras
desconhecidas. Nenhuma análise v1 é rotulada como v2 sem reprocessamento.
VERSAO_SCHEMA do Extrator (atualmente 2) evolui separadamente, proposto para 3;
VERSAO_DADOS é 1/2. Não confundir essas duas versões.

Compatibilidade é trabalho coordenado, não consequência de manter nomes: consumidores
que conferem chaves exatas precisam ser atualizados antes de ativar a emissão v2.

## Divisão e ordem dos PRs

1. Os dois conferem este schema, especialmente a localização canônica de número e
   emitente, motivos das validações e identificação de versão fora do corpo.
2. Simon: G-01 nos validadores de correções/F-3, leitura v1/v2 e versionamento na
   GR-43, consultas oficiais e serviços da GR-22. Testar v1 até expirar, correções
   fiscais v1, v2, chave alfanumérica, divergência, duplicidade e rollback.
3. Gustavo: Extrator/prompt, montar_resultado, avisos, escolhas e campos da
   conferência; substituir a seleção automática do fornecedor ainda presente na
   antiga consulta GR-44 quando CPF e CNPJ coexistirem. Testar ambos os formatos.
4. Ativar v2 somente com os dois lados compatíveis e suíte de integração local.
5. Conectar confirmação aos serviços oficiais F-4/F-5 após disponíveis. Nenhum
   movimento antes da confirmação. Um PR por incremento revisável.

Este pacote registra as diretrizes; não aprova o schema automaticamente, não aplica
migrations, não acessa QA/PROD e não executa commit, push, PR, merge ou deploy.


## Alinhamento final encaminhado por Gustavo

Simon confirmou a estrutura e os nomes. valor_total e parcelas[].valor aceitam null quando não identificados, para corrigir na conferência. Isso não permite confirmação sem valores consistentes nem elimina revalidação financeira. As análises v1 seguem até expirar sem conversão ou extensão. Simon implementa GR-43/correções/F-3; Gustavo implementa Agents/processamento/interface. O contrato de dados está alinhado com estes ajustes, sem declarar serviços implementados ou ativação autorizada antes dos testes de integração. As etapas de revisão acima ficam como histórico da proposta.
