"""Área dos responsáveis."""

from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from werkzeug.datastructures import FileStorage

from app.acesso import entrar_modo_crianca, exigir, familia_id_atual, responsavel_required
from app.extensions import db
from app.forms import (
    AjusteForm,
    ConfiguracaoForm,
    CriancaForm,
    EstornoForm,
    FamiliaForm,
    ResponsavelForm,
    TrocarPinForm,
    TrocarSenhaForm,
    VazioForm,
)
from app.models import Auditoria, ConfiguracaoFamilia, Crianca, Familia, Lancamento, Responsavel, TipoLancamento
from app.services import auditoria, familias, imagens, ledger
from app.services.senhas import conferir, gerar_hash
from app.services.valores import ler_decimal

bp = Blueprint("pais", __name__, url_prefix="/pais")


def _registrar(acao, entidade, entidade_id=None, antes=None, depois=None):
    auditoria.registrar(
        familia_id=familia_id_atual(), autor_id=current_user.id, acao=acao, entidade=entidade,
        entidade_id=entidade_id, antes=antes, depois=depois,
    )


def _arquivo_enviado(campo) -> bool:
    # Com obj=crianca, o campo pode vir preenchido com o caminho da foto atual
    # (string); só um FileStorage com nome conta como novo upload.
    return isinstance(campo.data, FileStorage) and bool(campo.data.filename)


def _crianca_ou_404(crianca_id: int) -> Crianca:
    crianca = familias.obter_crianca(familia_id_atual(), crianca_id)
    exigir(crianca is not None)
    return crianca


# ---------------------------------------------------------------- painel

@bp.get("/")
@responsavel_required
def painel():
    criancas = familias.criancas_da_familia(familia_id_atual(), somente_ativas=True)
    saldos = {c.id: ledger.saldos(c.id) for c in criancas}
    return render_template("pais/painel.html", criancas=criancas, saldos=saldos, form=VazioForm())


@bp.post("/modo-crianca")
@responsavel_required
def ativar_modo_crianca():
    form = VazioForm()
    if not form.validate_on_submit():
        abort(400)
    familia = db.session.get(Familia, familia_id_atual())
    if not familia.pin_parental_hash:
        flash("Defina o PIN parental antes de entregar o aparelho à criança.", "erro")
        return redirect(url_for("pais.familia"))
    _registrar("ativar_modo_crianca", "familia", familia.id)
    db.session.commit()
    entrar_modo_crianca()
    return redirect(url_for("crianca.selecao"))


# ---------------------------------------------------------------- crianças

@bp.get("/criancas")
@responsavel_required
def criancas():
    lista = familias.criancas_da_familia(familia_id_atual())
    return render_template("pais/criancas.html", criancas=lista)


@bp.route("/criancas/nova", methods=["GET", "POST"])
@responsavel_required
def crianca_nova():
    form = CriancaForm()
    if form.validate_on_submit():
        crianca = Crianca(
            familia_id=familia_id_atual(),
            nome=form.nome.data.strip(),
            data_nascimento=form.data_nascimento.data,
            cor_avatar=form.cor_avatar.data.lower(),
        )
        if _arquivo_enviado(form.foto):
            try:
                crianca.foto = imagens.salvar_imagem(form.foto.data, familia_id_atual(), "criancas")
            except imagens.ImagemInvalida as exc:
                form.foto.errors.append(str(exc))
                return render_template("pais/crianca_form.html", form=form, crianca=None)
        db.session.add(crianca)
        db.session.flush()
        _registrar("criar", "crianca", crianca.id, depois=auditoria.instantaneo(crianca))
        db.session.commit()
        flash(f"{crianca.nome} cadastrada(o).", "sucesso")
        return redirect(url_for("pais.criancas"))
    return render_template("pais/crianca_form.html", form=form, crianca=None)


@bp.route("/criancas/<int:crianca_id>/editar", methods=["GET", "POST"])
@responsavel_required
def crianca_editar(crianca_id: int):
    crianca = _crianca_ou_404(crianca_id)
    form = CriancaForm(obj=crianca)
    if form.validate_on_submit():
        antes = auditoria.instantaneo(crianca)
        foto_antiga = crianca.foto
        nova_foto = None
        if _arquivo_enviado(form.foto):
            try:
                nova_foto = imagens.salvar_imagem(form.foto.data, familia_id_atual(), "criancas")
            except imagens.ImagemInvalida as exc:
                form.foto.errors.append(str(exc))
                return render_template("pais/crianca_form.html", form=form, crianca=crianca)
        crianca.nome = form.nome.data.strip()
        crianca.data_nascimento = form.data_nascimento.data
        crianca.cor_avatar = form.cor_avatar.data.lower()
        if nova_foto:
            crianca.foto = nova_foto
        elif form.remover_foto.data:
            crianca.foto = None
        _registrar("editar", "crianca", crianca.id, antes=antes, depois=auditoria.instantaneo(crianca))
        db.session.commit()
        if foto_antiga and foto_antiga != crianca.foto:
            imagens.remover_imagem(foto_antiga)
        flash("Dados atualizados.", "sucesso")
        return redirect(url_for("pais.crianca_detalhe", crianca_id=crianca.id))
    return render_template("pais/crianca_form.html", form=form, crianca=crianca)


@bp.post("/criancas/<int:crianca_id>/alternar-ativo")
@responsavel_required
def crianca_alternar_ativo(crianca_id: int):
    form = VazioForm()
    if not form.validate_on_submit():
        abort(400)
    crianca = _crianca_ou_404(crianca_id)
    antes = auditoria.instantaneo(crianca, ["ativo"])
    # Desativar não exclui: o histórico do ledger é preservado.
    crianca.ativo = not crianca.ativo
    _registrar("ativar" if crianca.ativo else "desativar", "crianca", crianca.id,
               antes=antes, depois=auditoria.instantaneo(crianca, ["ativo"]))
    db.session.commit()
    flash(f"{crianca.nome} {'reativada(o)' if crianca.ativo else 'desativada(o)'}.", "sucesso")
    return redirect(url_for("pais.criancas"))


@bp.get("/criancas/<int:crianca_id>")
@responsavel_required
def crianca_detalhe(crianca_id: int):
    crianca = _crianca_ou_404(crianca_id)
    unidade = request.args.get("unidade") or None
    if unidade not in (None, "BRL", "PONTOS"):
        unidade = None
    lancamentos = ledger.extrato(familia_id_atual(), crianca.id, unidade)
    estornados = ledger.ids_estornados([l.id for l in lancamentos])
    return render_template(
        "pais/crianca_detalhe.html",
        crianca=crianca,
        saldos=ledger.saldos(crianca.id),
        lancamentos=lancamentos,
        estornados=estornados,
        unidade=unidade,
        ajuste_form=AjusteForm(),
        estorno_form=EstornoForm(),
    )


@bp.post("/criancas/<int:crianca_id>/ajuste")
@responsavel_required
def crianca_ajuste(crianca_id: int):
    crianca = _crianca_ou_404(crianca_id)
    form = AjusteForm()
    if form.validate_on_submit():
        valor = ler_decimal(form.valor.data)
        if form.direcao.data == "debito":
            valor = -valor
        try:
            lancamento = ledger.lancar(
                familia_id=familia_id_atual(), crianca_id=crianca.id, tipo=TipoLancamento.AJUSTE_MANUAL,
                unidade=form.unidade.data, valor=valor, autor_id=current_user.id, observacao=form.motivo.data,
            )
            _registrar("lancar", "lancamento", lancamento.id, depois=auditoria.instantaneo(lancamento))
            db.session.commit()
            flash("Ajuste registrado.", "sucesso")
        except ledger.ErroLedger as exc:
            db.session.rollback()
            flash(str(exc).capitalize() + ".", "erro")
    else:
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "erro")
    return redirect(url_for("pais.crianca_detalhe", crianca_id=crianca.id))


@bp.post("/lancamentos/<int:lancamento_id>/estornar")
@responsavel_required
def lancamento_estornar(lancamento_id: int):
    original = db.session.get(Lancamento, lancamento_id)
    exigir(original is not None and original.familia_id == familia_id_atual())
    crianca_id = original.crianca_id
    form = EstornoForm()
    if form.validate_on_submit():
        try:
            estorno = ledger.estornar(
                familia_id=familia_id_atual(), lancamento_id=lancamento_id,
                autor_id=current_user.id, motivo=form.motivo.data,
            )
            _registrar("estornar", "lancamento", lancamento_id, depois=auditoria.instantaneo(estorno))
            db.session.commit()
            flash("Lançamento estornado.", "sucesso")
        except ledger.ErroLedger as exc:
            db.session.rollback()
            flash(str(exc).capitalize() + ".", "erro")
    else:
        flash("Informe o motivo do estorno.", "erro")
    return redirect(url_for("pais.crianca_detalhe", crianca_id=crianca_id))


# ---------------------------------------------------------------- responsáveis

@bp.get("/responsaveis")
@responsavel_required
def responsaveis():
    lista = familias.responsaveis_da_familia(familia_id_atual())
    return render_template("pais/responsaveis.html", responsaveis=lista, form=VazioForm())


@bp.route("/responsaveis/novo", methods=["GET", "POST"])
@responsavel_required
def responsavel_novo():
    form = ResponsavelForm()
    if form.validate_on_submit():
        if familias.email_em_uso(form.email.data):
            form.email.errors.append("Este e-mail já está cadastrado.")
        else:
            responsavel = Responsavel(
                familia_id=familia_id_atual(),
                nome=form.nome.data.strip(),
                email=familias.normalizar_email(form.email.data),
                senha_hash=gerar_hash(form.senha.data),
            )
            db.session.add(responsavel)
            db.session.flush()
            _registrar("criar", "responsavel", responsavel.id, depois=auditoria.instantaneo(responsavel))
            db.session.commit()
            flash(f"{responsavel.nome} agora tem acesso. Informe a senha inicial pessoalmente.", "sucesso")
            return redirect(url_for("pais.responsaveis"))
    return render_template("pais/responsavel_form.html", form=form)


@bp.post("/responsaveis/<int:responsavel_id>/alternar-ativo")
@responsavel_required
def responsavel_alternar_ativo(responsavel_id: int):
    form = VazioForm()
    if not form.validate_on_submit():
        abort(400)
    responsavel = familias.obter_responsavel(familia_id_atual(), responsavel_id)
    exigir(responsavel is not None)
    if responsavel.id == current_user.id:
        flash("Você não pode desativar o próprio acesso.", "erro")
        return redirect(url_for("pais.responsaveis"))
    if responsavel.ativo and familias.contar_responsaveis_ativos(familia_id_atual()) <= 1:
        flash("A família precisa de pelo menos um responsável ativo.", "erro")
        return redirect(url_for("pais.responsaveis"))
    antes = auditoria.instantaneo(responsavel, ["ativo"])
    responsavel.ativo = not responsavel.ativo
    _registrar("ativar" if responsavel.ativo else "desativar", "responsavel", responsavel.id,
               antes=antes, depois=auditoria.instantaneo(responsavel, ["ativo"]))
    db.session.commit()
    flash("Acesso atualizado.", "sucesso")
    return redirect(url_for("pais.responsaveis"))


# ---------------------------------------------------------------- família

def _formularios_familia(familia: Familia):
    config = familia.configuracao
    familia_form = FamiliaForm(obj=familia, prefix="familia")
    config_form = ConfiguracaoForm(obj=config, prefix="config")
    if request.method == "GET" and config.penalidade_max_diaria_pontos is not None:
        config_form.penalidade_max_diaria_pontos.data = int(config.penalidade_max_diaria_pontos)
    if request.method == "GET" and config.penalidade_max_diaria_brl is not None:
        config_form.penalidade_max_diaria_brl.data = f"{config.penalidade_max_diaria_brl:.2f}".replace(".", ",")
    return (
        familia_form,
        config_form,
        TrocarPinForm(prefix="pin"),
        TrocarSenhaForm(prefix="senha"),
    )


@bp.route("/familia", methods=["GET", "POST"])
@responsavel_required
def familia():
    familia = db.session.get(Familia, familia_id_atual())
    familia_form, config_form, pin_form, senha_form = _formularios_familia(familia)
    acao = request.form.get("acao")

    if acao == "familia" and familia_form.validate_on_submit():
        antes = auditoria.instantaneo(familia, ["nome"])
        familia.nome = familia_form.nome.data.strip()
        _registrar("editar", "familia", familia.id, antes=antes, depois=auditoria.instantaneo(familia, ["nome"]))
        db.session.commit()
        flash("Nome da família atualizado.", "sucesso")
        return redirect(url_for("pais.familia"))

    if acao == "config" and config_form.validate_on_submit():
        config: ConfiguracaoFamilia = familia.configuracao
        antes = auditoria.instantaneo(config)
        config.permite_saldo_negativo = config_form.permite_saldo_negativo.data
        config.advertencias_antes_penalidade = config_form.advertencias_antes_penalidade.data
        brl = config_form.penalidade_max_diaria_brl.data
        config.penalidade_max_diaria_brl = ler_decimal(brl) if brl else None
        pontos = config_form.penalidade_max_diaria_pontos.data
        config.penalidade_max_diaria_pontos = Decimal(pontos) if pontos else None
        config.som_ativo = config_form.som_ativo.data
        db.session.flush()
        _registrar("editar", "configuracao_familia", familia.id, antes=antes, depois=auditoria.instantaneo(config))
        db.session.commit()
        flash("Configurações salvas.", "sucesso")
        return redirect(url_for("pais.familia"))

    if acao == "pin" and pin_form.validate_on_submit():
        if not conferir(current_user.senha_hash, pin_form.senha_atual.data):
            pin_form.senha_atual.errors.append("Senha incorreta.")
        else:
            familia.pin_parental_hash = gerar_hash(pin_form.pin.data)
            _registrar("trocar_pin", "familia", familia.id)
            db.session.commit()
            flash("PIN parental alterado.", "sucesso")
            return redirect(url_for("pais.familia"))

    if acao == "senha" and senha_form.validate_on_submit():
        if not conferir(current_user.senha_hash, senha_form.senha_atual.data):
            senha_form.senha_atual.errors.append("Senha incorreta.")
        else:
            current_user.senha_hash = gerar_hash(senha_form.senha.data)
            _registrar("trocar_senha", "responsavel", current_user.id)
            db.session.commit()
            flash("Senha alterada.", "sucesso")
            return redirect(url_for("pais.familia"))

    return render_template(
        "pais/familia.html", familia=familia, familia_form=familia_form, config_form=config_form,
        pin_form=pin_form, senha_form=senha_form,
    )


@bp.get("/auditoria")
@responsavel_required
def auditoria_lista():
    registros = db.session.scalars(
        select(Auditoria)
        .where(Auditoria.familia_id == familia_id_atual())
        .order_by(Auditoria.em.desc(), Auditoria.id.desc())
        .limit(200)
    )
    return render_template("pais/auditoria.html", registros=list(registros))
