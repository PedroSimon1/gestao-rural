from django.urls import path
from . import views_consultas
from . import views_manuais

urlpatterns = [
    path("contas/nova/", views_manuais.conta_manual_nova, name="conta_manual_nova"),
    path("contas/", views_consultas.contas, name="contas"),
    path("contas/<int:movimento_id>/", views_consultas.conta_detalhe, name="conta_detalhe"),
]
