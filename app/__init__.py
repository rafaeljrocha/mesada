from pathlib import Path

from flask import Flask, render_template
from sqlalchemy import event, text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import carregar_config
from app.extensions import csrf, db, login_manager, migrate


def create_app(sobrescrever: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(carregar_config(sobrescrever))

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    if app.config["PROXY_FIX"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        with app.app_context():
            _ativar_fk_sqlite(db.engine)
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent / "migrations"))
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.entrar"
    login_manager.login_message = "Entre para continuar."
    login_manager.session_protection = "basic"

    from app import models  # noqa: F401  (registra os modelos)
    from app.services import ledger  # noqa: F401  (registra listeners de imutabilidade)

    @login_manager.user_loader
    def carregar_usuario(responsavel_id: str):
        responsavel = db.session.get(models.Responsavel, int(responsavel_id))
        if responsavel is None or not responsavel.ativo:
            return None
        return responsavel

    _registrar_blueprints(app)
    _registrar_filtros(app)
    _registrar_cabecalhos(app)
    _registrar_erros(app)

    from app.cli import registrar_comandos

    registrar_comandos(app)

    @app.get("/favicon.ico")
    def favicon():
        return app.send_static_file("img/icone.svg"), 200, {"Content-Type": "image/svg+xml"}

    @app.get("/healthz")
    def healthz():
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


def _ativar_fk_sqlite(engine) -> None:
    # SQLite (só desenvolvimento) vem com chaves estrangeiras desligadas.
    @event.listens_for(engine, "connect")
    def _pragma(conexao, _registro):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _registrar_blueprints(app: Flask) -> None:
    from app.routes.auth import bp as auth_bp
    from app.routes.crianca import bp as crianca_bp
    from app.routes.midia import bp as midia_bp
    from app.routes.pais import bp as pais_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pais_bp)
    app.register_blueprint(crianca_bp)
    app.register_blueprint(midia_bp)


def _registrar_filtros(app: Flask) -> None:
    from app.services.valores import formatar_brl, formatar_pontos
    from app.tempo import em_sp

    app.jinja_env.filters["brl"] = formatar_brl
    app.jinja_env.filters["pontos"] = formatar_pontos
    app.jinja_env.filters["data_hora"] = lambda d: em_sp(d).strftime("%d/%m/%Y %H:%M") if d else ""
    app.jinja_env.filters["data"] = lambda d: d.strftime("%d/%m/%Y") if d else ""

    rotulos = {
        "CREDITO_TAREFA": "Crédito por tarefa",
        "DEBITO_PENALIDADE": "Penalidade",
        "DEBITO_RESGATE": "Resgate de prêmio",
        "CREDITO_MESADA_BASE": "Mesada-base",
        "PAGAMENTO": "Pagamento",
        "AJUSTE_MANUAL": "Ajuste manual",
        "ESTORNO": "Estorno",
    }
    app.jinja_env.filters["rotulo_tipo"] = lambda t: rotulos.get(t, t)


def _registrar_cabecalhos(app: Flask) -> None:
    # Sem scripts/estilos inline e sem origens externas: a criança não sai do app.
    csp = (
        "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers.setdefault("Content-Security-Policy", csp)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        return resposta


def _registrar_erros(app: Flask) -> None:
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(404)
    def nao_encontrado(_erro):
        return render_template("erros/erro.html", titulo="Página não encontrada", codigo=404), 404

    @app.errorhandler(413)
    def grande_demais(_erro):
        mensagem = f"O arquivo enviado passa do limite de {app.config['UPLOAD_MAX_MB']} MB."
        return render_template("erros/erro.html", titulo="Arquivo grande demais", mensagem=mensagem, codigo=413), 413

    @app.errorhandler(CSRFError)
    def csrf_invalido(_erro):
        mensagem = "O formulário expirou. Volte, recarregue a página e tente de novo."
        return render_template("erros/erro.html", titulo="Formulário expirado", mensagem=mensagem, codigo=400), 400
