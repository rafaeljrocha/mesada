"""Conversão e formatação de valores. Nunca usar float para dinheiro."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")


class ValorInvalido(ValueError):
    pass


def ler_decimal(texto) -> Decimal:
    """Aceita "12", "12,5", "1.234,56", "1234.56" e Decimal."""
    if isinstance(texto, Decimal):
        valor = texto
    elif isinstance(texto, int):
        valor = Decimal(texto)
    elif isinstance(texto, str):
        limpo = texto.strip().replace("R$", "").replace(" ", "")
        if not limpo:
            raise ValorInvalido("valor vazio")
        if "," in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        try:
            valor = Decimal(limpo)
        except InvalidOperation as exc:
            raise ValorInvalido(f"valor inválido: {texto!r}") from exc
    else:
        raise ValorInvalido(f"tipo não suportado: {type(texto).__name__}")
    if not valor.is_finite():
        raise ValorInvalido("valor inválido")
    return valor


def quantizar(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def formatar_brl(valor) -> str:
    valor = quantizar(Decimal(valor or 0))
    sinal = "-" if valor < 0 else ""
    inteiro, centavos = f"{abs(valor):.2f}".split(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{sinal}R$ {inteiro},{centavos}"


def formatar_pontos(valor) -> str:
    n = int(Decimal(valor or 0))
    return f"{n} ponto" if abs(n) == 1 else f"{n} pontos"
