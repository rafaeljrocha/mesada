from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services.valores import ValorInvalido, formatar_brl, ler_decimal
from app.tempo import hoje_sp


def test_virada_do_dia_usa_fuso_de_sao_paulo():
    # 02:30 UTC = 23:30 do dia anterior em São Paulo (UTC-3).
    assert hoje_sp(datetime(2026, 3, 10, 2, 30, tzinfo=timezone.utc)) == date(2026, 3, 9)
    assert hoje_sp(datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc)) == date(2026, 3, 10)


@pytest.mark.parametrize("texto, esperado", [
    ("12", "12"), ("12,5", "12.5"), ("1.234,56", "1234.56"), ("1234.56", "1234.56"), ("R$ 3,00", "3.00"),
])
def test_ler_decimal(texto, esperado):
    assert ler_decimal(texto) == Decimal(esperado)


@pytest.mark.parametrize("texto", ["", "abc", "NaN", "Infinity", "1,2,3"])
def test_ler_decimal_invalido(texto):
    with pytest.raises(ValorInvalido):
        ler_decimal(texto)


def test_formatar_brl():
    assert formatar_brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert formatar_brl(Decimal("-0.5")) == "-R$ 0,50"
