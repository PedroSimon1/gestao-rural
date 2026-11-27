"""Referência de um movimento recuperado para a consulta."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonte:
    movimento_id: int
    pontuacao: float
    motivo: str
