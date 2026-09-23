from django.urls import path

from .views import (
    documento_detalhe,
    documento_inicio,
    documento_processar,
    upload_documento,
)

# Sem app_name: os nomes continuam globais (reverse("documento_upload")).
urlpatterns = [
    path("", documento_inicio, name="documento_inicio"),
    path("upload/", upload_documento, name="documento_upload"),
    path("<int:pk>/", documento_detalhe, name="documento_detalhe"),
    path("<int:pk>/processar/", documento_processar, name="documento_processar"),
]
