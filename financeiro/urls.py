from django.urls import path
from . import views_consultas

urlpatterns = [
    path("contas/", views_consultas.contas, name="contas"),
    path("contas/<int:movimento_id>/", views_consultas.conta_detalhe, name="conta_detalhe"),
]
