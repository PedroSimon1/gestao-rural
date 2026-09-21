from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Titular, Usuario

admin.site.register(Usuario, UserAdmin)


@admin.register(Titular)
class TitularAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf", "ativo", "usuario")
    list_filter = ("ativo",)
    search_fields = ("nome", "cpf")
