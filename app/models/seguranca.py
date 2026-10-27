from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.tempo import agora


class TentativaAcesso(db.Model):
    """Falhas de login/PIN para rate limiting.

    Fica no banco (e não em memória) para valer entre todos os workers do
    Gunicorn e sobreviver a reinícios do container.
    """

    __tablename__ = "tentativa_acesso"
    __table_args__ = (Index("ix_tentativa_acesso_chave_em", "chave", "em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(300), nullable=False)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=agora)
