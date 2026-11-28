"""Carga explícita e protegida das notas fictícias de demonstração."""

from ipaddress import ip_address

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from documentos.demonstracao import TOTAL_PADRAO, carregar_demonstracao, contar_faltantes


def _host_local(host):
    if not host or host.startswith("/") or host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class Command(BaseCommand):
    help = "Carrega 200 notas fictícias determinísticas e idempotentes; permite simulação sem gravar."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--quantidade", type=int, default=TOTAL_PADRAO, help="Tamanho do catálogo (1 a 500).")
        parser.add_argument("--simular", action="store_true", help="Mostra existentes e faltantes sem gravar.")
        parser.add_argument("--confirmar", action="store_true", help="Confirma a carga no banco exibido.")
        parser.add_argument(
            "--permitir-remoto", action="store_true", help="Autoriza explicitamente um host remoto.",
        )

    def handle(self, *args, **options):
        total = options["quantidade"]
        if not 1 <= total <= 500:
            raise CommandError("--quantidade deve ser um inteiro entre 1 e 500.")
        banco = connection.settings_dict
        host = str(banco.get("HOST") or "")
        self.stdout.write(f"Banco-alvo: host={host or '(socket local)'}; nome={banco['NAME']}.")
        if options["simular"]:
            faltantes = contar_faltantes(total)
            self.stdout.write(
                f"Simulação: catálogo de {total} notas; existentes: {total - faltantes}; "
                f"seriam criadas: {faltantes}. Nenhum dado gravado."
            )
            return
        if not options["confirmar"]:
            raise CommandError("Informe --confirmar para carregar os dados fictícios.")
        if not _host_local(host) and not options["permitir_remoto"]:
            raise CommandError("Host remoto recusado. É necessário --permitir-remoto além de --confirmar.")
        quantidade = carregar_demonstracao(total)
        existentes = total - contar_faltantes(total)
        self.stdout.write(self.style.SUCCESS(
            f"Notas fictícias criadas: {quantidade} (catálogo de {total} notas; existentes agora: {existentes})."
        ))
