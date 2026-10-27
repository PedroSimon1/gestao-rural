"""Integração GR-44: JSON dos Agents → serviços oficiais de consulta da GR-40.

Não contém queries ORM nem outra implementação das regras de cadastro.
Usada pela view para apresentação somente leitura; não confirma lançamentos.
"""

from cadastros import consultas as cadastros
from cadastros.models import Papel

from .adaptador_financeiro import adaptar_resultado, documento_faturado


def consultar_resultado(resultado):
    """Valida o contrato financeiro e delega a consulta somente leitura.

    Usa os retornos oficiais (ResultadoConsultas/Situacao/PAPEL_AUSENTE).
    A GR-40 consultar_nota ainda lê somente faturado.cpf; compomos suas
    funções públicas para aceitar também faturado.cnpj, sem alterar a GR-40.
    Nenhum documento inválido é substituído ou considerado ausente.
    """
    nota = adaptar_resultado(resultado)
    fornecedor = resultado["fornecedor"]
    faturado = resultado["faturado"]
    return cadastros.ResultadoConsultas(
        fornecedor=cadastros.consultar_pessoa(
            fornecedor["cnpj"], Papel.FORNECEDOR, nome=nota.fornecedor.nome
        ),
        faturado=cadastros.consultar_pessoa(
            documento_faturado(faturado), Papel.FATURADO, nome=nota.faturado.nome
        ),
        classificacao=cadastros.consultar_classificacao(nota.codigo_despesa),
    )
