"""Protege os itens da nota na Data API, sem políticas e sem FORCE RLS.

Como nas demais tabelas financeiras, o Django continua usando o papel dono.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0007_itens_notas_fiscais"),
    ]

    operations = [
        migrations.RunSQL(
            'ALTER TABLE "itens_notas_fiscais" ENABLE ROW LEVEL SECURITY;',
            reverse_sql='ALTER TABLE "itens_notas_fiscais" DISABLE ROW LEVEL SECURITY;',
        ),
    ]
