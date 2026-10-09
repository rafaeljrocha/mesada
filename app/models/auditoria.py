from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.tempo import agora


class Auditoria(db.Model):
    """Trilha de auditoria das ações dos responsáveis (quem, quando, o quê)."""

    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_familia_em", "familia_id", "em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    familia_id: Mapped[int] = mapped_column(ForeignKey("familia.id", ondelete="CASCADE"), nullable=False)
    autor_responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("responsavel.id", ondelete="SET NULL")
    )
    acao: Mapped[str] = mapped_column(String(50), nullable=False)
    entidade: Mapped[str] = mapped_column(String(50), nullable=False)
    entidade_id: Mapped[str | None] = mapped_column(String(50))
    antes: Mapped[dict | None] = mapped_column(JSON)
    depois: Mapped[dict | None] = mapped_column(JSON)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=agora)

    autor = relationship("Responsavel", viewonly=True)
