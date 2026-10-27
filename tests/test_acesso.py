from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import Auditoria, Lancamento, Responsavel
from app.services import ledger
from tests.conftest import PIN, SENHA, entrar, nova_familia


def _qtd_lancamentos():
    return db.session.scalar(select(func.count()).select_from(Lancamento))


# ------------------------------------------------------------ autenticação

def test_primeiro_acesso_cria_familia_e_depois_fica_bloqueado(client):
    assert client.get("/").headers["Location"].endswith("/primeiro-acesso")
    resposta = client.post("/primeiro-acesso", data={
        "nome_familia": "Rocha", "nome": "Rafael", "email": "Pai@Exemplo.com",
        "senha": SENHA, "confirmar_senha": SENHA, "pin": PIN, "confirmar_pin": PIN,
    })
    assert resposta.status_code == 302
    resp = db.session.scalar(select(Responsavel))
    assert resp.email == "pai@exemplo.com"
    assert resp.senha_hash.startswith("$argon2")
    assert resp.familia.pin_parental_hash.startswith("$argon2")
    assert resp.familia.configuracao.permite_saldo_negativo is False
    assert client.get("/pais/").status_code == 200
    client.post("/sair")
    assert client.get("/primeiro-acesso").status_code == 404


def test_rotas_dos_pais_exigem_login(client, familia):
    resposta = client.get("/pais/")
    assert resposta.status_code == 302
    assert "/entrar" in resposta.headers["Location"]


def test_login_e_senha_errada(client, familia):
    assert entrar(client, senha="errada-errada").status_code == 200
    assert client.get("/pais/").status_code == 302
    assert entrar(client).status_code == 302
    assert client.get("/pais/").status_code == 200


def test_rate_limit_no_login(client, familia):
    for _ in range(5):
        entrar(client, senha="errada-errada")
    # Mesmo com a senha certa, fica bloqueado durante a janela.
    assert entrar(client).status_code == 429


def test_responsavel_inativo_nao_entra(client, familia):
    resp, _ = familia
    outro = Responsavel(familia_id=resp.familia_id, nome="Mãe", email="mae@exemplo.com",
                        senha_hash=resp.senha_hash, ativo=False)
    db.session.add(outro)
    db.session.commit()
    assert entrar(client, email="mae@exemplo.com").status_code == 200
    assert client.get("/pais/").status_code == 302


def test_sessao_sem_cookie_remember(client, familia):
    resposta = entrar(client)
    cookies = " ".join(resposta.headers.getlist("Set-Cookie"))
    assert "remember_token" not in cookies
    assert "HttpOnly" in cookies and "SameSite=Lax" in cookies


# ------------------------------------------------------------ modo criança

def _modo_crianca(client):
    entrar(client)
    resposta = client.post("/pais/modo-crianca")
    assert resposta.headers["Location"].endswith("/crianca/")


def test_modo_crianca_bloqueia_area_dos_pais(client, familia):
    _, (ana, _) = familia
    _modo_crianca(client)
    for url in ("/pais/", "/pais/criancas", f"/pais/criancas/{ana.id}", "/pais/familia", "/pais/auditoria"):
        resposta = client.get(url)
        assert resposta.status_code == 302, url
        assert resposta.headers["Location"].endswith("/crianca/sair"), url
    assert client.get("/crianca/").status_code == 200
    assert client.get(f"/crianca/{ana.id}").status_code == 200


def test_crianca_nao_altera_saldo_nem_sai_sem_pin(client, familia):
    resp, (ana, _) = familia
    _modo_crianca(client)
    antes = _qtd_lancamentos()
    resposta = client.post(f"/pais/criancas/{ana.id}/ajuste", data={
        "unidade": "PONTOS", "direcao": "credito", "valor": "100", "motivo": "eu mesmo",
    })
    assert resposta.headers["Location"].endswith("/crianca/sair")
    assert _qtd_lancamentos() == antes
    # Também não consegue sair (logout) sem o PIN.
    assert client.post("/sair").headers["Location"].endswith("/crianca/sair")
    assert client.get("/crianca/").status_code == 200


def test_pin_errado_e_certo(client, familia):
    _modo_crianca(client)
    assert client.post("/crianca/sair", data={"pin": "9999"}).status_code == 200
    assert client.get("/pais/").status_code == 302
    resposta = client.post("/crianca/sair", data={"pin": PIN})
    assert resposta.headers["Location"].endswith("/pais/")
    assert client.get("/pais/").status_code == 200


def test_rate_limit_no_pin(client, familia):
    _modo_crianca(client)
    for _ in range(5):
        client.post("/crianca/sair", data={"pin": "9999"})
    assert client.post("/crianca/sair", data={"pin": PIN}).status_code == 429
    assert client.get("/pais/").status_code == 302


def test_tela_da_crianca_nao_mostra_numeros(client, familia):
    resp, (ana, _) = familia
    ledger.lancar(familia_id=resp.familia_id, crianca_id=ana.id, tipo="CREDITO_TAREFA", unidade="BRL",
                  valor=Decimal("37.25"))
    ledger.lancar(familia_id=resp.familia_id, crianca_id=ana.id, tipo="CREDITO_TAREFA", unidade="PONTOS", valor=3)
    db.session.commit()
    _modo_crianca(client)
    html = client.get(f"/crianca/{ana.id}").get_data(as_text=True)
    assert "37" not in html and "R$" not in html
    assert html.count("⭐</span>") >= 3


# ------------------------------------------------------------ isolamento entre famílias

@pytest.fixture
def duas_familias(app):
    a = nova_familia(nome="Silva", email="pai@exemplo.com", criancas=("Ana",))
    b = nova_familia(nome="Souza", email="mae@outra.com", criancas=("Caio",))
    return a, b


def test_familia_nao_acessa_dados_de_outra(client, duas_familias):
    (resp_a, (ana,)), (resp_b, (caio,)) = duas_familias
    lanc = ledger.lancar(familia_id=resp_a.familia_id, crianca_id=ana.id, tipo="CREDITO_TAREFA",
                         unidade="PONTOS", valor=5)
    db.session.commit()
    entrar(client, email="mae@outra.com")

    assert client.get(f"/pais/criancas/{caio.id}").status_code == 200
    assert client.get(f"/pais/criancas/{ana.id}").status_code == 404
    assert client.get(f"/pais/criancas/{ana.id}/editar").status_code == 404
    assert client.post(f"/pais/criancas/{ana.id}/alternar-ativo").status_code == 404
    assert client.post(f"/pais/criancas/{ana.id}/ajuste", data={
        "unidade": "PONTOS", "direcao": "debito", "valor": "5", "motivo": "invasão",
    }).status_code == 404
    assert client.post(f"/pais/lancamentos/{lanc.id}/estornar", data={"motivo": "invasão"}).status_code == 404
    assert client.post(f"/pais/responsaveis/{resp_a.id}/alternar-ativo").status_code == 404
    assert client.get(f"/crianca/{ana.id}").status_code == 404
    assert "Ana" not in client.get("/pais/").get_data(as_text=True)
    assert "Ana" not in client.get("/crianca/").get_data(as_text=True)
    assert ledger.saldo(ana.id, "PONTOS") == 5
    assert not ledger.lancamento_estornado(lanc.id)


# ------------------------------------------------------------ fluxo dos pais

def test_ajuste_estorno_e_auditoria_pela_interface(client, familia):
    resp, (ana, _) = familia
    entrar(client)
    client.post(f"/pais/criancas/{ana.id}/ajuste", data={
        "unidade": "BRL", "direcao": "credito", "valor": "12,50", "motivo": "saldo inicial",
    })
    lanc = db.session.scalar(select(Lancamento))
    assert lanc.valor == Decimal("12.50") and lanc.autor_responsavel_id == resp.id
    client.post(f"/pais/lancamentos/{lanc.id}/estornar", data={"motivo": "digitei errado"})
    client.post(f"/pais/lancamentos/{lanc.id}/estornar", data={"motivo": "de novo"})
    assert ledger.saldo(ana.id, "BRL") == 0
    assert _qtd_lancamentos() == 2
    acoes = set(db.session.scalars(select(Auditoria.acao)))
    assert {"login", "lancar", "estornar"} <= acoes
    html = client.get(f"/pais/criancas/{ana.id}").get_data(as_text=True)
    assert "R$ 12,50" in html and "estornado" in html


def test_debito_alem_do_saldo_mostra_erro(client, familia):
    _, (ana, _) = familia
    entrar(client)
    resposta = client.post(f"/pais/criancas/{ana.id}/ajuste", data={
        "unidade": "PONTOS", "direcao": "debito", "valor": "3", "motivo": "teste",
    }, follow_redirects=True)
    assert "Saldo insuficiente" in resposta.get_data(as_text=True)
    assert _qtd_lancamentos() == 0


def test_nao_desativa_a_si_mesmo(client, familia):
    resp, _ = familia
    entrar(client)
    client.post(f"/pais/responsaveis/{resp.id}/alternar-ativo")
    db.session.refresh(resp)
    assert resp.ativo


def test_configuracao_da_familia(client, familia):
    resp, _ = familia
    entrar(client)
    client.post("/pais/familia", data={
        "acao": "config", "config-permite_saldo_negativo": "y", "config-advertencias_antes_penalidade": "0",
        "config-penalidade_max_diaria_brl": "5,00", "config-penalidade_max_diaria_pontos": "",
    })
    config = db.session.get(Responsavel, resp.id).familia.configuracao
    db.session.refresh(config)
    assert config.permite_saldo_negativo is True
    assert config.advertencias_antes_penalidade == 0
    assert config.penalidade_max_diaria_brl == Decimal("5.00")
    assert config.penalidade_max_diaria_pontos is None
    assert config.som_ativo is False


# ------------------------------------------------------------ CSRF e cabeçalhos

def test_csrf_obrigatorio(app, familia):
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    assert client.post("/entrar", data={"email": "pai@exemplo.com", "senha": SENHA}).status_code == 400


def test_cabecalhos_de_seguranca(client):
    resposta = client.get("/healthz")
    assert resposta.status_code == 200
    assert "default-src 'self'" in resposta.headers["Content-Security-Policy"]
    assert resposta.headers["X-Frame-Options"] == "DENY"
