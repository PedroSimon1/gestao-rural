"""Carga explícita e protegida das notas fictícias de demonstração."""

from ipaddress import ip_address

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from documentos.demonstracao import carregar_demonstracao


def _host_local(host):
    if not host or host.startswith("/") or host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class Command(BaseCommand):
    help = "Carrega 24 notas fictícias de demonstração, sem duplicar lançamentos."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--confirmar", action="store_true", help="Confirma a carga no banco exibido.")
        parser.add_argument(
            "--permitir-remoto", action="store_true", help="Autoriza explicitamente um host remoto.",
        )

    def handle(self, *args, **options):
        banco = connection.settings_dict
        host = str(banco.get("HOST") or "")
        self.stdout.write(f"Banco-alvo: host={host or '(socket local)'}; nome={banco['NAME']}.")
        if not options["confirmar"]:
            raise CommandError("Informe --confirmar para carregar os dados fictícios.")
        if not _host_local(host) and not options["permitir_remoto"]:
            raise CommandError("Host remoto recusado. É necessário --permitir-remoto além de --confirmar.")
        quantidade = carregar_demonstracao()
        self.stdout.write(self.style.SUCCESS(f"Notas fictícias criadas: {quantidade}."))
