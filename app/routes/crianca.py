"""Área da criança (base da Fase 1: seleção por foto + tela inicial)."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from app.acesso import area_crianca, em_modo_crianca, entrar_modo_pais, exigir, familia_id_atual
from app.extensions import db
from app.forms import PinForm
from app.models import Familia
from app.services import auditoria, familias, ledger, limite_tentativas
from app.services.senhas import conferir

bp = Blueprint("crianca", __name__, url_prefix="/crianca")

# Representação visual do saldo (decisão 11): nunca mostra número.
MAX_ICONES = 20


def _icones(valor) -> dict:
    inteiro = max(int(valor), 0)
    return {"quantidade": min(inteiro, MAX_ICONES), "transborda": inteiro > MAX_ICONES}


@bp.get("/")
@area_crianca
def selecao():
    criancas = familias.criancas_da_familia(familia_id_atual(), somente_ativas=True)
    return render_template("crianca/selecao.html", criancas=criancas)


@bp.get("/<int:crianca_id>")
@area_crianca
def inicio(crianca_id: int):
    crianca = familias.obter_crianca(familia_id_atual(), crianca_id)
    exigir(crianca is not None and crianca.ativo)
    session["crianca_id"] = crianca.id
    saldos = ledger.saldos(crianca.id)
    return render_template(
        "crianca/inicio.html",
        crianca=crianca,
        estrelas=_icones(saldos["PONTOS"]),
        # Moedas: uma por real inteiro (provisório; desenho final na Fase 6).
        moedas=_icones(saldos["BRL"]),
    )


@bp.route("/sair", methods=["GET", "POST"])
@area_crianca
def sair():
    """Volta para a área dos pais mediante PIN parental."""
    if not em_modo_crianca():
        return redirect(url_for("pais.painel"))
    form = PinForm()
    if form.validate_on_submit():
        chave = f"pin:{familia_id_atual()}:{request.remote_addr}"
        if limite_tentativas.bloqueado(chave, current_app.config["PIN_MAX_FALHAS"]):
            flash("Muitas tentativas. Aguarde alguns minutos.", "erro")
            return render_template("crianca/sair.html", form=form), 429
        familia = db.session.get(Familia, familia_id_atual())
        if conferir(familia.pin_parental_hash, form.pin.data):
            limite_tentativas.limpar(chave)
            auditoria.registrar(
                familia_id=familia.id, autor_id=current_user.id, acao="sair_modo_crianca",
                entidade="familia", entidade_id=familia.id,
            )
            db.session.commit()
            entrar_modo_pais()
            return redirect(url_for("pais.painel"))
        limite_tentativas.registrar_falha(chave)
        flash("PIN incorreto.", "erro")
    return render_template("crianca/sair.html", form=form)
