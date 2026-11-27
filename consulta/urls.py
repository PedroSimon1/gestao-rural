from django.urls import path

from .views import consulta

urlpatterns = [
    path("", consulta, name="consulta"),
]
