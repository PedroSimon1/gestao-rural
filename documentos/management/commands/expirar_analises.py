"""Marca como EXPIRADA as análises pendentes vencidas e apaga os dados (GR-43).

Pode rodar a qualquer momento e quantas vezes for preciso: as análises também
expiram sozinhas quando alguém tenta usá-las depois do prazo.
"""

from django.core.management.base import BaseCommand

from documentos.analises import expirar_analises


class Command(BaseCommand):
    help = "Expira as análises pendentes vencidas e apaga os dados da nota."

    def handle(self, *args, **options):
        quantidade = expirar_analises()
        self.stdout.write(f"Análises expiradas: {quantidade}.")
