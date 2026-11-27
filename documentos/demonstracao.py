"""Notas e pessoas inteiramente fictícias para a demonstração acadêmica.

A carga preserva cadastros existentes e usa apenas as classificações iniciais.
Documentos com DV válido não representam consulta ou vínculo com a Receita.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.db import transaction

from cadastros.models import Classificacao, Papel, Pessoa, TipoClassificacao
from comum.documentos_br import digito_verificador
from financeiro.identidade_fiscal import identificar_nota, registrar_identidade_fiscal
from financeiro.itens_nota import registrar_itens_nota
from financeiro.models import MovimentoConta, OrigemMovimento, TipoMovimento
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

MANUTENCAO = "MANUTENCAO_E_OPERACAO"
INFRAESTRUTURA = "INFRAESTRUTURA_E_UTILIDADES"
CPF_FICTICIO = "12345678909"

# Descrição, quantidade, preço unitário, classificação. As duas notas de cada
# fornecedor têm produtos relacionados, mas identidades e datas distintas.
PRODUTOS = (
    ("Ração bovina 25 kg", "20", "89.50", MANUTENCAO),
    ("Sal mineral 30 kg", "10", "112.00", MANUTENCAO),
    ("Vacina contra clostridioses 50 doses", "4", "92.50", MANUTENCAO),
    ("Vermífugo bovino 500 ml", "3", "165.00", MANUTENCAO),
    ("Adubo NPK 04-14-08 50 kg", "30", "148.00", MANUTENCAO),
    ("Calcário agrícola tonelada", "8", "155.00", MANUTENCAO),
    ("Defensivo agrícola herbicida 5 L", "4", "275.00", MANUTENCAO),
    ("Inseticida biológico 1 L", "6", "98.00", MANUTENCAO),
    ("Diesel S10 litro", "180.5", "6.20", MANUTENCAO),
    ("Óleo lubrificante para trator 20 L", "2", "385.00", MANUTENCAO),
    ("Filtro de óleo do trator", "3", "78.00", MANUTENCAO),
    ("Correia do alternador do trator", "2", "125.00", MANUTENCAO),
    ("Sementes de milho saco 20 kg", "10", "420.00", MANUTENCAO),
    ("Sementes de braquiária saco 10 kg", "8", "230.00", MANUTENCAO),
    ("Arame farpado rolo 500 m", "4", "395.00", INFRAESTRUTURA),
    ("Mourão tratado para cerca", "60", "42.00", INFRAESTRUTURA),
    ("Energia elétrica rural kWh", "850", "0.92", INFRAESTRUTURA),
    ("Instalação de padrão elétrico rural", "1", "1250.00", INFRAESTRUTURA),
    ("Tubo PVC de irrigação 50 mm", "25", "64.00", INFRAESTRUTURA),
    ("Aspersor para irrigação", "12", "58.50", INFRAESTRUTURA),
    ("Lona para silagem 8 x 50 m", "2", "690.00", MANUTENCAO),
    ("Inoculante para silagem", "5", "95.00", MANUTENCAO),
    ("Telha galvanizada para galpão", "20", "132.00", INFRAESTRUTURA),
    ("Cimento saco 50 kg", "25", "39.90", INFRAESTRUTURA),
)
FORNECEDORES = (
    "Nutrição Campo Fictícia", "Saúde Animal Fictícia", "Solo Fértil Fictícia",
    "Proteção da Lavoura Fictícia", "Combustíveis Campo Fictícia", "Peças Rural Fictícia",
    "Sementes Horizonte Fictícia", "Cercas da Fazenda Fictícia", "Energia Rural Fictícia",
    "Irrigação Verde Fictícia", "Silagem Boa Fictícia", "Construção Rural Fictícia",
)


def cnpj_ficticio(indice):
    base = f"98765{indice:03d}0001"
    primeiro = digito_verificador(base, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    segundo = digito_verificador(base + primeiro, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    return base + primeiro + segundo


def id_da_nota(indice):
    return uuid5(NAMESPACE_URL, f"gestao-rural:demonstracao:nota:{indice}")


@transaction.atomic
def carregar_demonstracao():
    """Devolve quantas notas foram criadas; repetição não altera o histórico."""
    classificacoes = {
        codigo: Classificacao.objects.get(tipo=TipoClassificacao.DESPESA, codigo=codigo)
        for codigo in (MANUTENCAO, INFRAESTRUTURA)
    }
    criadas = 0
    for indice, (descricao, quantidade, unitario, codigo) in enumerate(PRODUTOS, 1):
        analise_id = id_da_nota(indice)
        if MovimentoConta.objects.filter(analise_origem_id=analise_id).exists():
            continue
        fornecedor_indice = (indice - 1) // 2
        fornecedor, _ = Pessoa.objects.get_or_create(
            documento=cnpj_ficticio(fornecedor_indice + 1),
            defaults={"razao_social": FORNECEDORES[fornecedor_indice]},
        )
        fornecedor.atribuir_papel(Papel.FORNECEDOR)
        faturado, _ = Pessoa.objects.get_or_create(
            documento=CPF_FICTICIO, defaults={"razao_social": "Produtor da Fazenda Demonstração Fictícia"},
        )
        faturado.atribuir_papel(Papel.FATURADO)
        emissao = date(2026, 1, 5) + timedelta(days=(indice - 1) * 12)
        total = (Decimal(quantidade) * Decimal(unitario)).quantize(Decimal("0.01"))
        numero_parcelas = 1 + (indice % 3)
        valor_parcela = (total / numero_parcelas).quantize(Decimal("0.01"))
        parcelas = tuple(
            ItemParcela(
                numero=n,
                data_vencimento=emissao + timedelta(days=30 * n),
                valor=valor_parcela if n < numero_parcelas else total - valor_parcela * (n - 1),
            )
            for n in range(1, numero_parcelas + 1)
        )
        movimento, criado = registrar_movimento(DadosMovimento(
            tipo=TipoMovimento.APAGAR, origem=OrigemMovimento.NOTA_FISCAL,
            contraparte=fornecedor, faturado=faturado, valor_total=total,
            classificacoes=(ItemClassificacao(classificacoes[codigo], principal=True),),
            parcelas=parcelas, analise_origem_id=analise_id,
        ))
        identidade = identificar_nota(
            emitente_cnpj=fornecedor.documento, modelo="55", serie=901, numero=900000 + indice,
        )
        nota, _ = registrar_identidade_fiscal(movimento, identidade, data_emissao=emissao)
        registrar_itens_nota(nota, [{
            "descricao": descricao, "quantidade": quantidade,
            "valor_unitario": unitario, "valor_total": str(total),
        }])
        criadas += int(criado)
    return criadas
