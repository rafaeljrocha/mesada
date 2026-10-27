"""Rate limiting de login e PIN, persistido no banco."""

from datetime import timedelta

from flask import current_app
from sqlalchemy import delete, func, select

from app.extensions import db
from app.models import TentativaAcesso
from app.tempo import agora


def _janela():
    return timedelta(minutes=current_app.config["BLOQUEIO_MINUTOS"])


def bloqueado(chave: str, maximo: int) -> bool:
    limite = agora() - _janela()
    falhas = db.session.scalar(
        select(func.count()).select_from(TentativaAcesso).where(
            TentativaAcesso.chave == chave, TentativaAcesso.em >= limite
        )
    )
    return falhas >= maximo


def registrar_falha(chave: str) -> None:
    db.session.add(TentativaAcesso(chave=chave[:300]))
    # Limpeza oportunista de registros antigos.
    db.session.execute(delete(TentativaAcesso).where(TentativaAcesso.em < agora() - timedelta(days=1)))
    db.session.commit()


def limpar(chave: str) -> None:
    db.session.execute(delete(TentativaAcesso).where(TentativaAcesso.chave == chave))
    db.session.commit()
