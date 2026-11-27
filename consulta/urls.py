from django.urls import path

from .views import consulta, consulta_indice

urlpatterns = [
    path("", consulta, name="consulta"),
    path("indice/", consulta_indice, name="consulta_indice"),
]
