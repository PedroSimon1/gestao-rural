# F-6 — Bloqueio de integração e contrato a alinhar com Simon

Estado em `aaa80cc`, 27/10/2026. **Proposta técnica; não é contrato aprovado
nem implementação nova.** T-05 já está aprovada: manter análise PENDENTE,
sem renovar o prazo original de 30 minutos.

## Evidência do bloqueio

Em `cadastros/pendentes.py` existe:

```python
salvar_cadastro_pendente(razao_social, papel, *, consentimento, documento_extraido=None)
```

Cada chamada válida cria uma Pessoa INCOMPLETA e seu papel na transação
oficial. Não recebe chave de idempotência, sessão, análise ou versão.
Uma reprodução diagnóstica na cópia exata desta base chamou o serviço duas
vezes com nome fictício/papel/ausência de documento iguais: **duas pessoas,
zero movimentos**. O teste é diagnóstico externo, não parte da suíte versionada.

Isso não autoriza deduplicar por nome, inventar CPF/CNPJ, usar `.get_or_create()`
pela razão social ou criar outro serviço de persistência na interface.
Desabilitar o botão só reduz duplo clique; não cobre reenvio/rede/concorrência.

## O que a interface precisa do backend oficial

Simon deve definir/estender a operação oficial, com contrato claro para:

1. Identificar a solicitação por UUID e vincular à sessão/análise/parte da nota.
2. Validar dono, prazo, estado e versão das correções antes de persistir.
3. Receber papel e consentimento explícitos, nome corrigido e documento da
   fonte autorizada; documento válido segue F-4, inválido não é armazenado.
4. Repetição com a mesma chave/dados devolver o mesmo cadastro, sem duplicar,
   inclusive em solicitações simultâneas. Conteúdo diferente deve ser recusado.
5. Não criar movimento nem renovar/cancelar a análise; preservar a T-05.
6. Definir erros estáveis e a resposta que identifica o cadastro criado/reusado.
7. Definir reenvio após expiração/cancelamento/conflito: pode recusar com erro
   de estado, mas nunca criar outro cadastro como efeito da repetição.

Assinatura de referência para discussão, **não definida como API existente**:

```python
salvar_pendente_da_analise(
    session, analise_id, *, papel, razao_social,
    versao_correcoes, consentimento, chave_idempotencia,
)
```

Nome/arquivo, model de controle, migrations e transação ficam com Simon;
pode adaptar a fachada atual em vez de criar essa assinatura. O essencial
é o comportamento oficial testado, sem segunda implementação no frontend.

## Divisão e aceite

- **Simon:** operação/contrato, restrição persistente contra duplicação e
  testes de repetição, concorrência, autorização/estado e rollback.
- **Lopes:** botão/formulário, seleção explícita do papel, UUID/prova da
  solicitação preservados, mensagens, integração e testes HTTP após o contrato.
- **Já disponível:** `listar_incompletos()` e regularização no mesmo registro,
  pela GR-46 ou F-4. Não precisam ser reimplementados.

Manter a integração F-6 pendente até evidência. Este documento não muda o
backend, não executa migrations e não representa autorização de publicação.
