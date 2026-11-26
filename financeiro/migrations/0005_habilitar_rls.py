"""Habilita Row Level Security, sem políticas, em todas as tabelas dos apps.

No Supabase, as tabelas do esquema `public` ficam alcançáveis pela Data API
(chave anon) quando ela está ativa. Com RLS ligado e nenhuma política, esses
papéis não leem nem gravam nada. O Django conecta como dono das tabelas, que
não é filtrado pelo RLS (sem FORCE), então a aplicação não muda de
comportamento. Comando idempotente; não cria políticas nem altera dados.

Tabelas novas de qualquer app precisam da mesma linha numa migration própria:
`financeiro/test_rls.py` falha se alguma ficar de fora.
"""
from django.db import migrations

TABELAS = (
    "pessoas",
    "papeis_pessoa",
    "classificacoes",
    "analises_pendentes",
    "movimentos_contas",
    "movimentos_classificacoes",
    "parcelas_contas",
    "notas_fiscais_lancadas",
)


def _sql(acao):
    return "\n".join(f'ALTER TABLE "{tabela}" {acao} ROW LEVEL SECURITY;' for tabela in TABELAS)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0003_categorias_iniciais'),
        ('documentos', '0002_correcoes_da_conferencia'),
        ('financeiro', '0004_chave_idempotencia'),
    ]

    operations = [
        migrations.RunSQL(_sql("ENABLE"), reverse_sql=_sql("DISABLE")),
    ]
