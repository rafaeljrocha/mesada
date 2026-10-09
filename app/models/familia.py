from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.tempo import agora


class Familia(db.Model):
    __tablename__ = "familia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    # Decisão P4: um único PIN parental por família.
    pin_parental_hash: Mapped[str | None] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=agora)

    configuracao: Mapped["ConfiguracaoFamilia"] = relationship(
        back_populates="familia", uselist=False, cascade="all, delete-orphan"
    )
    responsaveis: Mapped[list["Responsavel"]] = relationship(back_populates="familia")
    criancas: Mapped[list["Crianca"]] = relationship(back_populates="familia")


class ConfiguracaoFamilia(db.Model):
    """Parâmetros da família que materializam as decisões da seção 13."""

    __tablename__ = "configuracao_familia"
    __table_args__ = (
        CheckConstraint("advertencias_antes_penalidade >= 0", name="advertencias_nao_negativas"),
        CheckConstraint(
            "penalidade_max_diaria_brl IS NULL OR penalidade_max_diaria_brl > 0",
            name="limite_brl_positivo",
        ),
        CheckConstraint(
            "penalidade_max_diaria_pontos IS NULL OR penalidade_max_diaria_pontos > 0",
            name="limite_pontos_positivo",
        ),
    )

    familia_id: Mapped[int] = mapped_column(
        ForeignKey("familia.id", ondelete="CASCADE"), primary_key=True
    )
    # Decisão 4: piso zero (False). Mantido configurável conforme seção 6.3.
    permite_saldo_negativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Decisão 5: padrão global de advertências (valor inicial provisório).
    advertencias_antes_penalidade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Seção 6.3: limites diários por criança; NULL = sem limite.
    penalidade_max_diaria_brl: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    penalidade_max_diaria_pontos: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    som_ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora, onupdate=agora
    )

    familia: Mapped[Familia] = relationship(back_populates="configuracao")


class Responsavel(UserMixin, db.Model):
    __tablename__ = "responsavel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        ForeignKey("familia.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=agora)
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    familia: Mapped[Familia] = relationship(back_populates="responsaveis")

    @property
    def is_active(self) -> bool:  # Flask-Login
        return self.ativo


class Crianca(db.Model):
    __tablename__ = "crianca"
    __table_args__ = (
        # Permite FK composta (id, familia_id) a partir do ledger, garantindo no
        # banco que um lançamento nunca aponte para criança de outra família.
        UniqueConstraint("id", "familia_id", name="uq_crianca_id_familia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(
        ForeignKey("familia.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    # Caminho relativo dentro de UPLOAD_DIR; servido apenas via rota autenticada.
    foto: Mapped[str | None] = mapped_column(String(255))
    cor_avatar: Mapped[str] = mapped_column(String(7), nullable=False, default="#4f86f7")
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=agora)

    familia: Mapped[Familia] = relationship(back_populates="criancas")

    @property
    def inicial(self) -> str:
        return (self.nome.strip()[:1] or "?").upper()
