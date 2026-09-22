from django.contrib import admin

from .models import Amortizacao, LancamentoFinanceiro, Parcela


admin.site.register(LancamentoFinanceiro)
admin.site.register(Parcela)
admin.site.register(Amortizacao)
