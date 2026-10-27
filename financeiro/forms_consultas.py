"""Filtros de consulta; inclusive cadastros inativos para preservar histórico."""
from django import forms

from cadastros.models import Classificacao, Pessoa
from .models import OrigemMovimento, StatusMovimento, TipoMovimento


class FiltroContasForm(forms.Form):
    tipo = forms.ChoiceField(label="Tipo de conta", required=False, choices=[("", "A pagar e a receber"), *TipoMovimento.choices])
    origem = forms.ChoiceField(label="Origem", required=False, choices=[("", "Todas as origens"), *OrigemMovimento.choices])
    status = forms.ChoiceField(label="Situação do lançamento", required=False, initial=StatusMovimento.CONFIRMADO,
        choices=[*StatusMovimento.choices, ("TODOS", "Confirmados e cancelados")])
    contraparte = forms.ModelChoiceField(label="Contraparte", required=False,
        queryset=Pessoa.objects.all(), empty_label="Todas as contrapartes")
    classificacao = forms.ModelChoiceField(label="Classificação", required=False,
        queryset=Classificacao.objects.all(), empty_label="Todas as classificações")
    por_pagina = forms.ChoiceField(label="Contas por página", required=False, initial="30",
        choices=[("10", "10"), ("30", "30"), ("100", "100")])
    pagina = forms.IntegerField(required=False, min_value=1, max_value=10**9, widget=forms.HiddenInput)
