"""Livro-razão (ledger) imutável.

Saldo nunca é um campo editável: é sempre a soma dos lançamentos de uma
criança em uma unidade. A aplicação só faz INSERT nesta tabela; UPDATE e
DELETE são bloqueados por trigger no banco (ver migration inicial) e por
listener do SQLAlchemy (ver services/ledger.py).
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.tempo import agora


class TipoLancamento(str, enum.Enum):
    CREDITO_TAREFA = "CREDITO_TAREFA"
    DEBITO_PENALIDADE = "DEBITO_PENALIDADE"
    DEBITO_RESGATE = "DEBITO_RESGATE"
    CREDITO_MESADA_BASE = "CREDITO_MESADA_BASE"
    PAGAMENTO = "PAGAMENTO"
    AJUSTE_MANUAL = "AJUSTE_MANUAL"
    ESTORNO = "ESTORNO"


class Unidade(str, enum.Enum):
    # Decisão 1 (d): R$ e pontos são saldos independentes, sem conversão.
    BRL = "BRL"
    PONTOS = "PONTOS"


TIPOS_CREDITO = (TipoLancamento.CREDITO_TAREFA, TipoLancamento.CREDITO_MESADA_BASE)
TIPOS_DEBITO = (
    TipoLancamento.DEBITO_PENALIDADE,
    TipoLancamento.DEBITO_RESGATE,
    TipoLancamento.PAGAMENTO,
)


def _lista_sql(valores) -> str:
    return ", ".join(f"'{v.value}'" for v in valores)


class Lancamento(db.Model):
    __tablename__ = "lancamento"
    __table_args__ = (
        ForeignKeyConstraint(
            ["crianca_id", "familia_id"],
            ["crianca.id", "crianca.familia_id"],
            name="fk_lancamento_crianca_familia",
        ),
        CheckConstraint(f"tipo IN ({_lista_sql(TipoLancamento)})", name="tipo_valido"),
        CheckConstraint(f"unidade IN ({_lista_sql(Unidade)})", name="unidade_valida"),
        CheckConstraint("valor <> 0", name="valor_nao_zero"),
        # Pontos são sempre inteiros.
        CheckConstraint(
            "unidade <> 'PONTOS' OR valor = CAST(valor AS INTEGER)", name="pontos_inteiros"
        ),
        CheckConstraint(f"tipo NOT IN ({_lista_sql(TIPOS_CREDITO)}) OR valor > 0", name="credito_positivo"),
        CheckConstraint(f"tipo NOT IN ({_lista_sql(TIPOS_DEBITO)}) OR valor < 0", name="debito_negativo"),
        CheckConstraint("tipo <> 'PAGAMENTO' OR unidade = 'BRL'", name="pagamento_em_brl"),
        CheckConstraint(
            "(tipo = 'ESTORNO' AND estorno_de_id IS NOT NULL) "
            "OR (tipo <> 'ESTORNO' AND estorno_de_id IS NULL)",
            name="estorno_referencia",
        ),
        CheckConstraint(
            "tipo <> 'AJUSTE_MANUAL' OR (observacao IS NOT NULL AND length(trim(observacao)) > 0)",
            name="ajuste_exige_motivo",
        ),
        Index("ix_lancamento_crianca_unidade", "crianca_id", "unidade"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        ForeignKey("familia.id", ondelete="CASCADE"), nullable=False, index=True
    )
    crianca_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    unidade: Mapped[str] = mapped_column(String(10), nullable=False)
    # Com sinal: créditos positivos, débitos negativos.
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text)
    # NULL = lançamento gerado pelo sistema.
    autor_responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("responsavel.id", ondelete="SET NULL")
    )
    # Um lançamento só pode ser estornado uma vez: UNIQUE garante no banco.
    estorno_de_id: Mapped[int | None] = mapped_column(
        ForeignKey("lancamento.id", ondelete="RESTRICT"), unique=True
    )
    # Agrupa lançamentos gerados juntos (decisão 7: ocorrência coletiva;
    # decisão P1: um fato gerando lançamento em R$ e em pontos).
    lote_id: Mapped[str | None] = mapped_column(String(36), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=agora)

    crianca = relationship(
        "Crianca", primaryjoin="foreign(Lancamento.crianca_id) == Crianca.id", viewonly=True
    )
    autor = relationship("Responsavel", viewonly=True)
    estorno_de = relationship("Lancamento", remote_side=[id], foreign_keys=[estorno_de_id], viewonly=True)
