"""Utilitários de data/hora.

Todo instante é gravado em UTC (timestamptz). Toda regra baseada em "dia"
usa o fuso America/Sao_Paulo.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

FUSO_SP = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    return datetime.now(timezone.utc)


def em_sp(instante: datetime) -> datetime:
    if instante.tzinfo is None:
        # Bancos sem suporte a timezone (SQLite) devolvem datetime "ingênuo",
        # mas o valor gravado é sempre UTC.
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(FUSO_SP)


def hoje_sp(instante: datetime | None = None) -> date:
    return em_sp(instante or agora()).date()
