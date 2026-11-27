from django.urls import path
from . import views_consultas
from . import views_manuais
from . import views_pagamentos

urlpatterns = [
    path("contas/nova/", views_manuais.conta_manual_nova, name="conta_manual_nova"),
    path("contas/", views_consultas.contas, name="contas"),
    path("contas/<int:movimento_id>/", views_consultas.conta_detalhe, name="conta_detalhe"),
    path("contas/parcelas/<int:parcela_id>/pagamento/", views_pagamentos.parcela_pagamento, name="parcela_pagamento"),
]
