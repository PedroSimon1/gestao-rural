"""Categorias iniciais de despesa (GR-36).

Os códigos são os valores do Enum TipoDespesa do Agent Classificador; as
descrições seguem o exemplo do professor (MANUTENÇÃO E OPERAÇÃO). Os valores
ficam congelados aqui: a migration não importa código da aplicação.

Idempotente: uma categoria que já existe (mesmo tipo e código) é mantida como
está, sem reativar nem sobrescrever a descrição. A reversão não apaga nada,
porque classificações nunca são excluídas (RN-01). Aplicada manualmente em
cada ambiente, como as demais migrations (PT-06).
"""

from django.db import migrations

CATEGORIAS_INICIAIS = (
    ("DESPESA", "MANUTENCAO_E_OPERACAO", "MANUTENÇÃO E OPERAÇÃO"),
    ("DESPESA", "INFRAESTRUTURA_E_UTILIDADES", "INFRAESTRUTURA E UTILIDADES"),
)


def criar_categorias_iniciais(apps, schema_editor):
    Classificacao = apps.get_model("cadastros", "Classificacao")
    for tipo, codigo, descricao in CATEGORIAS_INICIAIS:
        Classificacao.objects.get_or_create(
            tipo=tipo, codigo=codigo, defaults={"descricao": descricao}
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0002_classificacao'),
    ]

    operations = [
        migrations.RunPython(criar_categorias_iniciais, migrations.RunPython.noop),
    ]
