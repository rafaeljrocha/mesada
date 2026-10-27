"""Fixtures de teste.

Por padrão os testes usam SQLite (um arquivo novo por teste). Para rodar
contra PostgreSQL — como no CI — defina TEST_DATABASE_URL, por exemplo:

    TEST_DATABASE_URL=postgresql://mesada:mesada@localhost/mesada_teste pytest

O schema é sempre criado pelas migrations (nunca por create_all), para que
os testes também validem as migrations e os triggers do ledger.
"""

import os

import pytest
from flask.testing import FlaskClient
from flask_migrate import upgrade
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.services.familias import criar_familia

URL_PG = os.environ.get("TEST_DATABASE_URL")


def usando_postgres() -> bool:
    return bool(URL_PG)


class ClienteIsolado(FlaskClient):
    """Cada requisição roda em um app context novo.

    Sem isso, a requisição reaproveitaria o app context da fixture e, com ele,
    o `g` (usuário logado em cache do Flask-Login) e a sessão do banco do
    próprio teste — mascarando falhas de autenticação e de transação.
    """

    def open(self, *args, **kwargs):
        with self.application.app_context():
            return super().open(*args, **kwargs)


@pytest.fixture
def app(tmp_path):
    url = URL_PG or f"sqlite:///{tmp_path / 'teste.db'}"
    app = create_app({
        "APP_ENV": "teste",
        "SECRET_KEY": "teste",
        "SQLALCHEMY_DATABASE_URI": url,
        "DATA_DIR": tmp_path,
        "UPLOAD_DIR": tmp_path / "uploads",
        "WTF_CSRF_ENABLED": False,
        "SESSION_COOKIE_SECURE": False,
    })
    app.test_client_class = ClienteIsolado
    with app.app_context():
        upgrade()
        yield app
        db.session.remove()
        if usando_postgres():
            tabelas = ", ".join(t.name for t in db.metadata.sorted_tables)
            with db.engine.begin() as conexao:
                # TRUNCATE não dispara os triggers de linha do ledger.
                conexao.execute(text(f"TRUNCATE {tabelas} RESTART IDENTITY CASCADE"))
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


SENHA = "senha-segura-123"
PIN = "1234"


def nova_familia(nome="Silva", email="pai@exemplo.com", criancas=("Ana", "Beto")):
    """Cria família + responsável + crianças. Retorna (responsavel, [criancas])."""
    from app.models import Crianca

    responsavel = criar_familia(
        nome_familia=nome, nome_responsavel="Responsável " + nome, email=email, senha=SENHA, pin=PIN
    )
    lista = []
    for nome_crianca in criancas:
        crianca = Crianca(familia_id=responsavel.familia_id, nome=nome_crianca)
        db.session.add(crianca)
        lista.append(crianca)
    db.session.commit()
    return responsavel, lista


def entrar(client, email="pai@exemplo.com", senha=SENHA):
    return client.post("/entrar", data={"email": email, "senha": senha})


@pytest.fixture
def familia(app):
    return nova_familia()
