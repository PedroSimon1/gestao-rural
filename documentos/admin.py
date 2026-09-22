from django.contrib import admin

from .models import Documento


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("nome_original", "status", "titular", "enviado_em")
    list_filter = ("status", "enviado_em")
    search_fields = ("nome_original",)
    readonly_fields = ("enviado_em",)