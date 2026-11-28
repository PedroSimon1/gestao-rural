"""Notas e pessoas inteiramente fictícias para a demonstração acadêmica.

A carga preserva cadastros existentes e usa apenas as classificações iniciais.
Documentos com DV válido não representam consulta ou vínculo com a Receita.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.db import transaction
from django.utils import timezone

from cadastros.models import Classificacao, Papel, Pessoa, TipoClassificacao
from comum.documentos_br import digito_verificador
from financeiro.identidade_fiscal import identificar_nota, registrar_identidade_fiscal
from financeiro.itens_nota import registrar_itens_nota
from financeiro.models import MovimentoConta, OrigemMovimento, TipoMovimento
from financeiro.pagamentos import registrar_pagamento
from financeiro.servicos import DadosMovimento, ItemClassificacao, ItemParcela, registrar_movimento

MANUTENCAO = "MANUTENCAO_E_OPERACAO"
INFRAESTRUTURA = "INFRAESTRUTURA_E_UTILIDADES"
CPF_FICTICIO = "12345678909"
TOTAL_PADRAO = 200
LIMITE_PAGAMENTOS = date(2026, 11, 15)

# Os primeiros 24 produtos e as primeiras 24 notas são o catálogo original.
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
    ("Suplemento proteico bovino 30 kg", "12", "138.00", MANUTENCAO),
    ("Farelo de soja saco 50 kg", "15", "158.00", MANUTENCAO),
    ("Carrapaticida bovino 1 L", "4", "145.00", MANUTENCAO),
    ("Brinco inseticida bovino par", "40", "18.50", MANUTENCAO),
    ("Ureia agrícola saco 50 kg", "20", "182.00", MANUTENCAO),
    ("Superfosfato simples saco 50 kg", "18", "126.00", MANUTENCAO),
    ("Fungicida agrícola 1 L", "5", "189.00", MANUTENCAO),
    ("Adjuvante para pulverização 5 L", "3", "115.00", MANUTENCAO),
    ("Gasolina comum litro", "80", "6.35", MANUTENCAO),
    ("Graxa agrícola balde 10 kg", "2", "245.00", MANUTENCAO),
    ("Pneu dianteiro de trator", "2", "1380.00", MANUTENCAO),
    ("Rolamento de eixo do trator", "4", "185.00", MANUTENCAO),
    ("Sementes de sorgo saco 20 kg", "6", "295.00", MANUTENCAO),
    ("Sementes de capim mombaça 10 kg", "8", "268.00", MANUTENCAO),
    ("Grampo galvanizado para cerca kg", "10", "22.00", INFRAESTRUTURA),
    ("Porteira de madeira 3 m", "2", "680.00", INFRAESTRUTURA),
    ("Disjuntor trifásico 63 A", "2", "135.00", INFRAESTRUTURA),
    ("Cabo elétrico de cobre 10 mm metro", "80", "12.50", INFRAESTRUTURA),
    ("Mangueira de irrigação 1 polegada metro", "100", "7.80", INFRAESTRUTURA),
    ("Bomba de irrigação 2 cv", "1", "1680.00", INFRAESTRUTURA),
    ("Filme para fardos de silagem rolo", "4", "420.00", MANUTENCAO),
    ("Serviço de ensilagem hora", "8", "285.00", MANUTENCAO),
    ("Areia lavada metro cúbico", "6", "145.00", INFRAESTRUTURA),
    ("Brita para piso metro cúbico", "5", "165.00", INFRAESTRUTURA),
    ("Teteira de silicone para ordenha jogo", "4", "195.00", MANUTENCAO),
    ("Detergente alcalino para ordenha 5 L", "6", "86.00", MANUTENCAO),
    ("Filtro de leite pacote 100 unidades", "5", "62.00", MANUTENCAO),
    ("Sanitizante para tanque de leite 5 L", "4", "98.00", MANUTENCAO),
    ("Mangueira de leite metro", "12", "38.00", MANUTENCAO),
    ("Óleo para bomba de vácuo 1 L", "8", "42.00", MANUTENCAO),
    ("Enxada com cabo", "5", "78.00", MANUTENCAO),
    ("Pá de bico com cabo", "4", "89.00", MANUTENCAO),
    ("Alicate para cerca", "3", "95.00", MANUTENCAO),
    ("Chave combinada 19 mm", "4", "32.00", MANUTENCAO),
    ("Disco de corte 4 polegadas", "20", "8.50", MANUTENCAO),
    ("Foice roçadeira com cabo", "4", "92.00", MANUTENCAO),
    ("Bota de segurança par", "8", "125.00", MANUTENCAO),
    ("Luva de proteção nitrílica par", "20", "18.00", MANUTENCAO),
    ("Óculos de proteção", "12", "22.00", MANUTENCAO),
    ("Respirador para aplicação agrícola", "6", "145.00", MANUTENCAO),
    ("Avental impermeável", "8", "65.00", MANUTENCAO),
    ("Protetor auricular tipo concha", "6", "58.00", MANUTENCAO),
    ("Consulta veterinária bovina", "2", "280.00", MANUTENCAO),
    ("Exame de brucelose bovina", "25", "32.00", MANUTENCAO),
    ("Diagnóstico de gestação bovina", "20", "45.00", MANUTENCAO),
    ("Atendimento de casco bovino", "10", "85.00", MANUTENCAO),
    ("Inseminação artificial bovina serviço", "12", "95.00", MANUTENCAO),
    ("Exame de mastite do rebanho", "15", "28.00", MANUTENCAO),
    ("Frete de insumos agrícolas km", "120", "5.50", MANUTENCAO),
    ("Transporte de bovinos por cabeça", "12", "95.00", MANUTENCAO),
    ("Frete de leite viagem", "8", "180.00", MANUTENCAO),
    ("Transporte de máquinas km", "90", "8.50", MANUTENCAO),
    ("Frete de grãos tonelada", "15", "68.00", MANUTENCAO),
    ("Frete de fardos de feno viagem", "3", "320.00", MANUTENCAO),
    ("Muda de eucalipto", "300", "3.80", INFRAESTRUTURA),
    ("Muda de ipê para recuperação de nascente", "80", "12.00", INFRAESTRUTURA),
    ("Protetor de muda unidade", "100", "4.50", INFRAESTRUTURA),
    ("Tutor de bambu para muda", "150", "2.80", INFRAESTRUTURA),
    ("Substrato para viveiro saco 25 kg", "12", "38.00", INFRAESTRUTURA),
    ("Serviço de plantio de mudas diária", "4", "190.00", INFRAESTRUTURA),
)
FORNECEDORES = (
    "Nutrição Campo Fictícia", "Saúde Animal Fictícia", "Solo Fértil Fictícia",
    "Proteção da Lavoura Fictícia", "Combustíveis Campo Fictícia", "Peças Rural Fictícia",
    "Sementes Horizonte Fictícia", "Cercas da Fazenda Fictícia", "Energia Rural Fictícia",
    "Irrigação Verde Fictícia", "Silagem Boa Fictícia", "Construção Rural Fictícia",
    "Ordenha Limpa Fictícia", "Ferramentas do Campo Fictícia", "Proteção Rural Fictícia",
    "Veterinária Pasto Verde Fictícia", "Fretes da Serra Fictícia", "Viveiro Nascente Fictícia",
    "Nutrição Pastagens Fictícia", "Sanidade do Rebanho Fictícia", "Adubos Colheita Fictícia",
    "Defensivos Vale Verde Fictícia", "Abastecimento Rural Fictícia", "Pneus e Peças Fictícia",
    "Sementes Boa Safra Fictícia", "Materiais de Cercamento Fictícia", "Elétrica da Fazenda Fictícia",
    "Água no Campo Fictícia", "Silagem Silo Forte Fictícia", "Materiais Galpão Fictícia",
    "Laticínio Equipamentos Fictícia", "Ferramentas Boa Lida Fictícia", "EPI Colheita Segura Fictícia",
    "Veterinária Horizonte Fictícia", "Transportes Caminho Rural Fictícia", "Viveiro Mata Viva Fictícia",
)

# Cada fornecedor tem um ramo; cada ramo reúne somente produtos relacionados.
RAMOS_PRODUTOS = tuple(
    (2 * n, 2 * n + 1, 24 + 2 * n, 25 + 2 * n) for n in range(12)
) + tuple(tuple(range(48 + 6 * n, 54 + 6 * n)) for n in range(6))
RAMOS_FORNECEDORES = tuple(range(18)) * 2
CENTAVO = Decimal("0.01")


def cnpj_ficticio(indice):
    base = f"98765{indice:03d}0001"
    primeiro = digito_verificador(base, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    segundo = digito_verificador(base + primeiro, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    return base + primeiro + segundo


def id_da_nota(indice):
    return uuid5(NAMESPACE_URL, f"gestao-rural:demonstracao:nota:{indice}")


def _validar_total(total):
    if isinstance(total, bool) or not isinstance(total, int) or not 1 <= total <= 500:
        raise ValueError("A quantidade deve ser um inteiro entre 1 e 500.")


def _ids_existentes(total):
    return set(MovimentoConta.objects.filter(
        analise_origem_id__in=[id_da_nota(n) for n in range(1, total + 1)],
        nota_fiscal__isnull=False,
    ).values_list("analise_origem_id", flat=True))


def contar_faltantes(total=TOTAL_PADRAO) -> int:
    """Conta as notas ausentes do catálogo solicitado, sem alterar o banco."""
    _validar_total(total)
    return total - len(_ids_existentes(total))


def _dados_da_nota(indice):
    if indice <= 24:
        fornecedor = (indice - 1) // 2
        produtos = (PRODUTOS[indice - 1],)
        emissao = date(2026, 1, 5) + timedelta(days=(indice - 1) * 12)
        numero_parcelas = 1 + indice % 3
    else:
        fornecedor = (indice - 25) % len(FORNECEDORES)
        ramo = RAMOS_PRODUTOS[RAMOS_FORNECEDORES[fornecedor]]
        inicio = (indice - 25) // len(FORNECEDORES)
        produtos = tuple(PRODUTOS[ramo[(inicio + n) % len(ramo)]] for n in range(1 + (indice - 25) % 4))
        emissao = date(2026, 1, 5) + timedelta(days=((indice - 25) * 37) % 325)
        numero_parcelas = 1 + indice % 6
    itens = []
    for descricao, quantidade, unitario, codigo in produtos:
        if indice > 24:
            quantidade = str((Decimal(quantidade) * Decimal(4 + indice * 7 % 9) / 10).quantize(CENTAVO))
        itens.append({
            "descricao": descricao, "quantidade": quantidade, "valor_unitario": unitario,
            "valor_total": str((Decimal(quantidade) * Decimal(unitario)).quantize(CENTAVO)),
        })
    return fornecedor, emissao, numero_parcelas, codigo, itens


def carregar_demonstracao(total=TOTAL_PADRAO):
    """Cria somente as notas ausentes; confirma cada nota em transação própria."""
    _validar_total(total)
    existentes = _ids_existentes(total)
    if len(existentes) == total:
        return 0
    classificacoes = {
        codigo: Classificacao.objects.get(tipo=TipoClassificacao.DESPESA, codigo=codigo)
        for codigo in (MANUTENCAO, INFRAESTRUTURA)
    }
    pessoas = {}

    def pessoa(documento, nome, papel):
        if documento not in pessoas:
            cadastro, _ = Pessoa.objects.get_or_create(
                documento=documento, defaults={"razao_social": nome},
            )
            cadastro.atribuir_papel(papel)
            pessoas[documento] = cadastro
        return pessoas[documento]

    limite_pagamentos = min(LIMITE_PAGAMENTOS, timezone.localdate())
    criadas = 0
    for indice in range(1, total + 1):
        analise_id = id_da_nota(indice)
        if analise_id in existentes:
            continue
        fornecedor_indice, emissao, numero_parcelas, codigo, itens = _dados_da_nota(indice)
        valor_total = sum(Decimal(item["valor_total"]) for item in itens)
        valor_parcela = (valor_total / numero_parcelas).quantize(CENTAVO)
        parcelas = tuple(
            ItemParcela(
                numero=n, data_vencimento=emissao + timedelta(days=30 * n),
                valor=valor_parcela if n < numero_parcelas else valor_total - valor_parcela * (n - 1),
            )
            for n in range(1, numero_parcelas + 1)
        )
        with transaction.atomic():
            fornecedor = pessoa(
                cnpj_ficticio(fornecedor_indice + 1), FORNECEDORES[fornecedor_indice], Papel.FORNECEDOR,
            )
            faturado = pessoa(CPF_FICTICIO, "Produtor da Fazenda Demonstração Fictícia", Papel.FATURADO)
            movimento, criado = registrar_movimento(DadosMovimento(
                tipo=TipoMovimento.APAGAR, origem=OrigemMovimento.NOTA_FISCAL,
                contraparte=fornecedor, faturado=faturado, valor_total=valor_total,
                classificacoes=(ItemClassificacao(classificacoes[codigo], principal=True),),
                parcelas=parcelas, analise_origem_id=analise_id,
            ))
            identidade = identificar_nota(
                emitente_cnpj=fornecedor.documento, modelo="55", serie=901, numero=900000 + indice,
            )
            nota, _ = registrar_identidade_fiscal(movimento, identidade, data_emissao=emissao)
            registrar_itens_nota(nota, itens)
            if criado and indice > 24:
                for parcela in movimento.parcelas.filter(data_vencimento__lte=limite_pagamentos):
                    if (indice * 3 + parcela.numero * 7) % 10 < 7:
                        registrar_pagamento(parcela.pk, parcela.data_vencimento)
        criadas += int(criado)
    return criadas
