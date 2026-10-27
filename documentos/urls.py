from django.urls import path

from .views import documento_inicio
from .views_analises import analise_criar, analise_conferencia, analise_cancelar

urlpatterns = [
    path("", documento_inicio, name="documento_inicio"),
    path("analises/nova/", analise_criar, name="analise_criar"),
    path("analises/<uuid:analise_id>/", analise_conferencia, name="analise_conferencia"),
    path("analises/<uuid:analise_id>/salva/", analise_conferencia, name="analise_conferencia_salva"),
    path("analises/<uuid:analise_id>/cancelar/", analise_cancelar, name="analise_cancelar"),
]
