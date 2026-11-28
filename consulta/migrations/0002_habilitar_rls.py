"""Protege o índice na Data API; Django continua usando o papel dono."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("consulta", "0001_embeddings_movimentos"),
    ]

    operations = [
        migrations.RunSQL(
            'ALTER TABLE "embeddings_movimentos" ENABLE ROW LEVEL SECURITY;',
            reverse_sql='ALTER TABLE "embeddings_movimentos" DISABLE ROW LEVEL SECURITY;',
        ),
    ]
