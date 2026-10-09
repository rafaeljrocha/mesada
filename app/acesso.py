"""Controle de acesso: área dos pais × área da criança.

O dispositivo fica autenticado como um responsável da família (sessão
persistente). Quando o responsável ativa o "modo criança", a sessão é
marcada e qualquer rota da área dos pais passa a exigir o PIN parental.

Importante: não usamos o cookie "remember me" do Flask-Login. Se a sessão
fosse restaurada por ele, a marcação de modo criança se perderia e a
criança cairia na área dos pais sem PIN.
"""

from functools import wraps

from flask import abort, redirect, session, url_for
from flask_login import current_user, login_required

MODO_CHAVE = "modo"
MODO_PAIS = "pais"
MODO_CRIANCA = "crianca"


def em_modo_crianca() -> bool:
    return session.get(MODO_CHAVE) == MODO_CRIANCA


def entrar_modo_pais() -> None:
    session[MODO_CHAVE] = MODO_PAIS
    session.pop("crianca_id", None)


def entrar_modo_crianca() -> None:
    session[MODO_CHAVE] = MODO_CRIANCA
    session.pop("crianca_id", None)


def familia_id_atual() -> int:
    return current_user.familia_id


def responsavel_required(view):
    """Área dos pais: exige login e que o dispositivo não esteja em modo criança."""

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if em_modo_crianca():
            return redirect(url_for("crianca.sair"))
        return view(*args, **kwargs)

    return wrapper


def area_crianca(view):
    """Área da criança: exige um dispositivo autenticado na família."""

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        return view(*args, **kwargs)

    return wrapper


def exigir(condicao) -> None:
    if not condicao:
        abort(404)
