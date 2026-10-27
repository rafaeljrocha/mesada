from datetime import date, datetime
from decimal import Decimal

from app.extensions import db
from app.models import Auditoria

# Campos que nunca entram na trilha de auditoria.
CAMPOS_SENSIVEIS = {"senha_hash", "pin_parental_hash"}


def _serializavel(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def instantaneo(obj, campos: list[str] | None = None) -> dict:
    """Fotografia dos campos de uma entidade, para os campos antes/depois."""
    nomes = campos or [c.key for c in obj.__table__.columns]
    return {
        nome: _serializavel(getattr(obj, nome))
        for nome in nomes
        if nome not in CAMPOS_SENSIVEIS
    }


def registrar(*, familia_id: int, autor_id: int | None, acao: str, entidade: str,
              entidade_id=None, antes: dict | None = None, depois: dict | None = None) -> Auditoria:
    registro = Auditoria(
        familia_id=familia_id,
        autor_responsavel_id=autor_id,
        acao=acao,
        entidade=entidade,
        entidade_id=None if entidade_id is None else str(entidade_id),
        antes=antes,
        depois=depois,
    )
    db.session.add(registro)
    return registro
