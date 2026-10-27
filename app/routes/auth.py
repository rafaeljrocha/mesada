from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from app.acesso import em_modo_crianca, entrar_modo_pais, responsavel_required
from app.extensions import db
from app.forms import EntrarForm, PrimeiroAcessoForm, VazioForm
from app.models import Responsavel
from app.services import auditoria, limite_tentativas
from app.services.familias import ErroCadastro, criar_familia, existe_familia, normalizar_email
from app.services.senhas import conferir
from app.tempo import agora

bp = Blueprint("auth", __name__)


@bp.get("/")
def inicio():
    if current_user.is_authenticated:
        if em_modo_crianca():
            return redirect(url_for("crianca.selecao"))
        return redirect(url_for("pais.painel"))
    if not existe_familia():
        return redirect(url_for("auth.primeiro_acesso"))
    return redirect(url_for("auth.entrar"))


def _cadastro_permitido() -> bool:
    return current_app.config["CADASTRO_ABERTO"] or not existe_familia()


def _iniciar_sessao(responsavel: Responsavel) -> None:
    session.clear()
    login_user(responsavel, remember=False)
    session.permanent = True
    entrar_modo_pais()


@bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    """Cria a família e o primeiro responsável.

    Disponível apenas enquanto não houver nenhuma família cadastrada, ou se
    CADASTRO_ABERTO=1 (preparação para uso por várias famílias).
    """
    if not _cadastro_permitido():
        abort(404)
    form = PrimeiroAcessoForm()
    if form.validate_on_submit():
        try:
            responsavel = criar_familia(
                nome_familia=form.nome_familia.data,
                nome_responsavel=form.nome.data,
                email=form.email.data,
                senha=form.senha.data,
                pin=form.pin.data,
            )
        except ErroCadastro as exc:
            db.session.rollback()
            flash(str(exc), "erro")
        else:
            db.session.commit()
            _iniciar_sessao(responsavel)
            flash("Família criada! Agora cadastre as crianças.", "sucesso")
            return redirect(url_for("pais.criancas"))
    return render_template("auth/primeiro_acesso.html", form=form)


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if current_user.is_authenticated:
        return redirect(url_for("auth.inicio"))
    form = EntrarForm()
    if form.validate_on_submit():
        email = normalizar_email(form.email.data)
        chave = f"login:{request.remote_addr}:{email}"
        if limite_tentativas.bloqueado(chave, current_app.config["LOGIN_MAX_FALHAS"]):
            flash(
                f"Muitas tentativas. Aguarde {current_app.config['BLOQUEIO_MINUTOS']} minutos e tente de novo.",
                "erro",
            )
            return render_template("auth/entrar.html", form=form), 429
        responsavel = db.session.scalar(select(Responsavel).where(Responsavel.email == email))
        if responsavel and responsavel.ativo and conferir(responsavel.senha_hash, form.senha.data):
            limite_tentativas.limpar(chave)
            responsavel.ultimo_login_em = agora()
            auditoria.registrar(
                familia_id=responsavel.familia_id, autor_id=responsavel.id, acao="login",
                entidade="responsavel", entidade_id=responsavel.id,
            )
            db.session.commit()
            _iniciar_sessao(responsavel)
            return redirect(url_for("pais.painel"))
        limite_tentativas.registrar_falha(chave)
        flash("E-mail ou senha incorretos.", "erro")
    return render_template("auth/entrar.html", form=form, cadastro_aberto=current_app.config["CADASTRO_ABERTO"])


@bp.post("/sair")
@responsavel_required
def sair():
    form = VazioForm()
    if not form.validate_on_submit():
        abort(400)
    logout_user()
    session.clear()
    flash("Você saiu.", "sucesso")
    return redirect(url_for("auth.entrar"))
