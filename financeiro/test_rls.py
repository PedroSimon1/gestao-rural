"""Row Level Security ligado em todas as tabelas dos apps (auditoria M-06)."""
from django.apps import apps
from django.db import connection
from django.test import TestCase


class RlsTests(TestCase):
    def tabelas_dos_apps(self):
        return {modelo._meta.db_table for modelo in apps.get_models()}

    def test_toda_tabela_de_app_tem_rls_habilitado(self):
        tabelas = self.tabelas_dos_apps()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity FROM pg_class "
                "WHERE relkind = 'r' AND relnamespace = current_schema()::regnamespace "
                "AND relname = ANY(%s)",
                [sorted(tabelas)],
            )
            situacao = dict(cursor.fetchall())

        self.assertEqual(set(situacao), tabelas)
        self.assertEqual([t for t, ligado in situacao.items() if not ligado], [])
