"""Serve imagens enviadas somente para usuários autenticados da própria família."""

from flask import Blueprint, abort, send_file
from flask_login import login_required

from app.acesso import familia_id_atual
from app.services import imagens

bp = Blueprint("midia", __name__)


@bp.get("/midia/<path:caminho>")
@login_required
def arquivo(caminho: str):
    if not imagens.pertence_a_familia(caminho, familia_id_atual()):
        abort(404)
    absoluto = imagens.resolver(caminho)
    if absoluto is None or not absoluto.is_file():
        abort(404)
    resposta = send_file(absoluto, mimetype="image/webp", max_age=0)
    resposta.headers["Cache-Control"] = "private, max-age=86400"
    return resposta
