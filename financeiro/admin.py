from django.contrib import admin

from .models import LancamentoFinanceiro, Parcela

admin.site.register(LancamentoFinanceiro)
admin.site.register(Parcela)