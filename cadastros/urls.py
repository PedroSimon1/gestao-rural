from django.urls import path
from . import views

urlpatterns = [
    path("pessoas/", views.pessoas, name="pessoas"),
    path("pessoas/nova/", views.pessoa_nova, name="pessoa_nova"),
    path("pessoas/<int:pessoa_id>/", views.pessoa_detalhe, name="pessoa_detalhe"),
    path("pessoas/<int:pessoa_id>/editar/", views.pessoa_editar, name="pessoa_editar"),
    path("pessoas/<int:pessoa_id>/papeis/", views.pessoa_atribuir_papel, name="pessoa_atribuir_papel"),
    path("pessoas/<int:pessoa_id>/regularizar/", views.pessoa_regularizar, name="pessoa_regularizar"),
    path("pessoas/<int:pessoa_id>/status/<str:acao>/", views.pessoa_status, name="pessoa_status"),
    path("pessoas/<int:pessoa_id>/papeis/<int:papel_id>/<str:acao>/", views.pessoa_status, name="papel_status"),
]
