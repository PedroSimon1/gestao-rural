from django.urls import path

from .views import documento_inicio

urlpatterns = [
    path("", documento_inicio, name="documento_inicio"),
]
