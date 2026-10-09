import threading
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.extensions import db
from app.models import ConfiguracaoFamilia, Crianca, Lancamento, TipoLancamento as T
from app.services import ledger
from tests.conftest import nova_familia, usando_postgres


def _lancar(resp, crianca, tipo, unidade, valor, **kw):
    return ledger.lancar(
        familia_id=resp.familia_id, crianca_id=crianca.id, tipo=tipo, unidade=unidade, valor=valor,
        autor_id=resp.id, **kw,
    )


def _soma_sql(crianca_id, unidade):
    total = db.session.scalar(
        select(func.coalesce(func.sum(Lancamento.valor), 0)).where(
            Lancamento.crianca_id == crianca_id, Lancamento.unidade == unidade
        )
    )
    return Decimal(str(total)).quantize(Decimal("0.01"))


# ------------------------------------------------------------ regras básicas

def test_saldos_independentes_por_unidade(familia):
    resp, (ana, beto) = familia
    _lancar(resp, ana, T.CREDITO_TAREFA, "PONTOS", 3)
    _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", "2,50")
    _lancar(resp, beto, T.CREDITO_TAREFA, "PONTOS", 1)
    db.session.commit()
    assert ledger.saldos(ana.id) == {"BRL": Decimal("2.50"), "PONTOS": Decimal("3.00")}
    assert ledger.saldos(beto.id) == {"BRL": Decimal("0.00"), "PONTOS": Decimal("1.00")}


@pytest.mark.parametrize("tipo, unidade, valor, mensagem", [
    (T.CREDITO_TAREFA, "PONTOS", -1, "positivo"),
    (T.DEBITO_PENALIDADE, "PONTOS", 1, "negativo"),
    (T.PAGAMENTO, "PONTOS", -1, "pagamento só"),
    (T.CREDITO_TAREFA, "PONTOS", "1,5", "inteiros"),
    (T.CREDITO_TAREFA, "BRL", 0, "zero"),
    (T.CREDITO_TAREFA, "BRL", "abc", "inválido"),
    (T.AJUSTE_MANUAL, "BRL", 1, "motivo"),
    (T.ESTORNO, "BRL", 1, "estornar"),
])
def test_validacoes_de_lancamento(familia, tipo, unidade, valor, mensagem):
    resp, (ana, _) = familia
    with pytest.raises(ledger.ErroLedger, match=mensagem):
        _lancar(resp, ana, tipo, unidade, valor)


def test_ajuste_manual_com_motivo(familia):
    resp, (ana, _) = familia
    lanc = _lancar(resp, ana, T.AJUSTE_MANUAL, "BRL", "10", observacao="saldo inicial")
    db.session.commit()
    assert lanc.autor_responsavel_id == resp.id
    assert ledger.saldo(ana.id, "BRL") == Decimal("10.00")


def test_crianca_de_outra_familia_e_rejeitada(familia):
    resp, _ = familia
    _, (outra,) = nova_familia(nome="Souza", email="mae@outra.com", criancas=("Caio",))
    with pytest.raises(ledger.CriancaNaoEncontrada):
        _lancar(resp, outra, T.CREDITO_TAREFA, "PONTOS", 1)


def test_crianca_inativa_nao_recebe_lancamento(familia):
    resp, (ana, _) = familia
    ana.ativo = False
    db.session.commit()
    with pytest.raises(ledger.ErroLedger, match="inativa"):
        _lancar(resp, ana, T.CREDITO_TAREFA, "PONTOS", 1)


# ------------------------------------------------------------ saldo negativo (decisão 4)

def test_piso_zero_rejeita_debito_maior_que_saldo(familia):
    resp, (ana, _) = familia
    _lancar(resp, ana, T.CREDITO_TAREFA, "PONTOS", 2)
    with pytest.raises(ledger.SaldoInsuficiente):
        _lancar(resp, ana, T.DEBITO_PENALIDADE, "PONTOS", -3)
    _lancar(resp, ana, T.DEBITO_PENALIDADE, "PONTOS", -2)
    db.session.commit()
    assert ledger.saldo(ana.id, "PONTOS") == 0


def test_configuracao_permite_saldo_negativo(familia):
    resp, (ana, _) = familia
    db.session.get(ConfiguracaoFamilia, resp.familia_id).permite_saldo_negativo = True
    db.session.commit()
    _lancar(resp, ana, T.DEBITO_PENALIDADE, "PONTOS", -3)
    db.session.commit()
    assert ledger.saldo(ana.id, "PONTOS") == Decimal("-3")


def test_pagamento_limitado_ao_saldo_mesmo_com_negativo_permitido(familia):
    resp, (ana, _) = familia
    db.session.get(ConfiguracaoFamilia, resp.familia_id).permite_saldo_negativo = True
    _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 5)
    with pytest.raises(ledger.SaldoInsuficiente):
        _lancar(resp, ana, T.PAGAMENTO, "BRL", "-5,01")
    _lancar(resp, ana, T.PAGAMENTO, "BRL", -5)
    db.session.commit()
    assert ledger.saldo(ana.id, "BRL") == 0


def test_debito_limitado_ao_saldo(familia):
    resp, (ana, _) = familia
    _lancar(resp, ana, T.CREDITO_TAREFA, "PONTOS", 2)
    lanc = ledger.debitar_limitado_ao_saldo(
        familia_id=resp.familia_id, crianca_id=ana.id, tipo=T.DEBITO_PENALIDADE, unidade="PONTOS", valor=-5,
    )
    assert lanc.valor == Decimal("-2")
    nada = ledger.debitar_limitado_ao_saldo(
        familia_id=resp.familia_id, crianca_id=ana.id, tipo=T.DEBITO_PENALIDADE, unidade="PONTOS", valor=-1,
    )
    assert nada is None
    db.session.commit()
    assert ledger.saldo(ana.id, "PONTOS") == 0


def test_debito_limitado_com_negativo_permitido_debita_integral(familia):
    resp, (ana, _) = familia
    db.session.get(ConfiguracaoFamilia, resp.familia_id).permite_saldo_negativo = True
    lanc = ledger.debitar_limitado_ao_saldo(
        familia_id=resp.familia_id, crianca_id=ana.id, tipo=T.DEBITO_PENALIDADE, unidade="BRL", valor="-1,50",
    )
    db.session.commit()
    assert lanc.valor == Decimal("-1.50")
    assert ledger.saldo(ana.id, "BRL") == Decimal("-1.50")


# ------------------------------------------------------------ estorno

def test_estorno_reverte_e_preserva_original(familia):
    resp, (ana, _) = familia
    original = _lancar(resp, ana, T.CREDITO_TAREFA, "PONTOS", 4)
    db.session.commit()
    estorno = ledger.estornar(familia_id=resp.familia_id, lancamento_id=original.id, autor_id=resp.id,
                              motivo="aprovado por engano")
    db.session.commit()
    assert estorno.valor == Decimal("-4")
    assert estorno.estorno_de_id == original.id
    assert db.session.get(Lancamento, original.id).valor == Decimal("4")
    assert ledger.saldo(ana.id, "PONTOS") == 0
    assert db.session.scalar(select(func.count()).select_from(Lancamento)) == 2


def test_estorno_nao_pode_ser_aplicado_duas_vezes(familia):
    resp, (ana, _) = familia
    original = _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 3)
    db.session.commit()
    ledger.estornar(familia_id=resp.familia_id, lancamento_id=original.id, autor_id=resp.id, motivo="erro")
    db.session.commit()
    with pytest.raises(ledger.JaEstornado):
        ledger.estornar(familia_id=resp.familia_id, lancamento_id=original.id, autor_id=resp.id, motivo="de novo")
    db.session.rollback()
    assert ledger.saldo(ana.id, "BRL") == 0


def test_estorno_de_estorno_e_proibido(familia):
    resp, (ana, _) = familia
    original = _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 3)
    estorno = ledger.estornar(familia_id=resp.familia_id, lancamento_id=original.id, autor_id=resp.id, motivo="x")
    with pytest.raises(ledger.ErroLedger, match="estorno"):
        ledger.estornar(familia_id=resp.familia_id, lancamento_id=estorno.id, autor_id=resp.id, motivo="y")


def test_estorno_exige_motivo_e_mesma_familia(familia):
    resp, (ana, _) = familia
    original = _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 3)
    db.session.commit()
    with pytest.raises(ledger.ErroLedger, match="motivo"):
        ledger.estornar(familia_id=resp.familia_id, lancamento_id=original.id, autor_id=resp.id, motivo="  ")
    outro, _ = nova_familia(nome="Souza", email="mae@outra.com", criancas=())
    with pytest.raises(ledger.LancamentoNaoEncontrado):
        ledger.estornar(familia_id=outro.familia_id, lancamento_id=original.id, autor_id=outro.id, motivo="x")


def test_unique_impede_segundo_estorno_mesmo_fora_do_service(familia):
    resp, (ana, _) = familia
    original = _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 3)
    ledger.estornar(familia_id=resp.familia_id, lancamento_id=original.id, autor_id=resp.id, motivo="x")
    db.session.commit()
    db.session.add(Lancamento(familia_id=resp.familia_id, crianca_id=ana.id, tipo="ESTORNO", unidade="BRL",
                              valor=Decimal("-3"), observacao="burlando", estorno_de_id=original.id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ------------------------------------------------------------ imutabilidade

def test_orm_nao_altera_nem_apaga_lancamento(familia):
    resp, (ana, _) = familia
    lanc = _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 3)
    db.session.commit()
    lanc.valor = Decimal("300")
    with pytest.raises(ledger.LancamentoImutavel):
        db.session.flush()
    db.session.rollback()
    db.session.delete(db.session.get(Lancamento, lanc.id))
    with pytest.raises(ledger.LancamentoImutavel):
        db.session.flush()
    db.session.rollback()


@pytest.mark.parametrize("sql", [
    "UPDATE lancamento SET valor = 999",
    "DELETE FROM lancamento",
])
def test_trigger_do_banco_bloqueia_update_e_delete(familia, sql):
    resp, (ana, _) = familia
    _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 3)
    db.session.commit()
    with pytest.raises(DBAPIError, match="imutavel"):
        db.session.execute(text(sql))
    db.session.rollback()
    assert ledger.saldo(ana.id, "BRL") == Decimal("3.00")


@pytest.mark.parametrize("valores", [
    {"tipo": "CREDITO_TAREFA", "unidade": "BRL", "valor": Decimal("-1")},
    {"tipo": "PAGAMENTO", "unidade": "PONTOS", "valor": Decimal("-1")},
    {"tipo": "AJUSTE_MANUAL", "unidade": "BRL", "valor": Decimal("1"), "observacao": " "},
    {"tipo": "CREDITO_TAREFA", "unidade": "PONTOS", "valor": Decimal("1.5")},
    {"tipo": "INVENTADO", "unidade": "BRL", "valor": Decimal("1")},
])
def test_constraints_do_banco(familia, valores):
    resp, (ana, _) = familia
    db.session.add(Lancamento(familia_id=resp.familia_id, crianca_id=ana.id, **valores))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_fk_composta_impede_lancamento_com_familia_trocada(familia):
    resp, (ana, _) = familia
    outro, _ = nova_familia(nome="Souza", email="mae@outra.com", criancas=())
    db.session.add(Lancamento(familia_id=outro.familia_id, crianca_id=ana.id, tipo="CREDITO_TAREFA",
                              unidade="BRL", valor=Decimal("1")))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ------------------------------------------------------------ propriedade: saldo = soma do ledger

operacao = st.one_of(
    st.tuples(st.just("credito"), st.sampled_from(["BRL", "PONTOS"]), st.integers(1, 5000)),
    st.tuples(st.just("debito"), st.sampled_from(["BRL", "PONTOS"]), st.integers(1, 5000)),
    st.tuples(st.just("penalidade_limitada"), st.sampled_from(["BRL", "PONTOS"]), st.integers(1, 5000)),
    st.tuples(st.just("ajuste"), st.sampled_from(["BRL", "PONTOS"]), st.integers(-5000, 5000).filter(bool)),
    st.tuples(st.just("pagamento"), st.just("BRL"), st.integers(1, 5000)),
    st.tuples(st.just("estorno"), st.just(None), st.integers(0, 50)),
)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(operacao, max_size=25), st.booleans())
def test_saldo_igual_soma_do_ledger_em_qualquer_sequencia(familia, operacoes, negativo):
    resp, _ = familia
    db.session.get(ConfiguracaoFamilia, resp.familia_id).permite_saldo_negativo = negativo
    crianca = Crianca(familia_id=resp.familia_id, nome="Prop")
    db.session.add(crianca)
    db.session.commit()

    esperado = {"BRL": Decimal("0"), "PONTOS": Decimal("0")}
    feitos: list[Lancamento] = []

    def converter(unidade, n):
        # BRL em centavos; pontos inteiros.
        return Decimal(n) / 100 if unidade == "BRL" else Decimal(n)

    for nome, unidade, n in operacoes:
        try:
            if nome == "credito":
                lanc = _lancar(resp, crianca, T.CREDITO_TAREFA, unidade, converter(unidade, n))
            elif nome == "debito":
                lanc = _lancar(resp, crianca, T.DEBITO_RESGATE, unidade, -converter(unidade, n))
            elif nome == "penalidade_limitada":
                lanc = ledger.debitar_limitado_ao_saldo(
                    familia_id=resp.familia_id, crianca_id=crianca.id, tipo=T.DEBITO_PENALIDADE,
                    unidade=unidade, valor=-converter(unidade, n),
                )
            elif nome == "ajuste":
                lanc = _lancar(resp, crianca, T.AJUSTE_MANUAL, unidade, converter(unidade, n), observacao="prop")
            elif nome == "pagamento":
                lanc = _lancar(resp, crianca, T.PAGAMENTO, "BRL", -converter("BRL", n))
            else:
                if not feitos:
                    continue
                alvo = feitos[n % len(feitos)]
                lanc = ledger.estornar(familia_id=resp.familia_id, lancamento_id=alvo.id, autor_id=resp.id,
                                       motivo="prop")
            db.session.commit()
        except ledger.ErroLedger:
            db.session.rollback()
            continue
        if lanc is None:
            continue
        esperado[lanc.unidade] += Decimal(lanc.valor)
        if lanc.tipo != "ESTORNO":
            feitos.append(lanc)
        # Com piso zero, só um estorno pode deixar o saldo negativo.
        if not negativo and lanc.tipo != "ESTORNO" and lanc.tipo != "AJUSTE_MANUAL" and lanc.valor < 0:
            assert ledger.saldo(crianca.id, lanc.unidade) >= 0

    for unidade in ("BRL", "PONTOS"):
        assert ledger.saldo(crianca.id, unidade) == esperado[unidade].quantize(Decimal("0.01"))
        assert ledger.saldo(crianca.id, unidade) == _soma_sql(crianca.id, unidade)
    # Nenhum lançamento foi estornado mais de uma vez.
    repetidos = db.session.scalar(
        select(func.count()).select_from(
            select(Lancamento.estorno_de_id).where(Lancamento.estorno_de_id.is_not(None))
            .group_by(Lancamento.estorno_de_id).having(func.count() > 1).subquery()
        )
    )
    assert repetidos == 0


# ------------------------------------------------------------ concorrência (PostgreSQL)

@pytest.mark.skipif(not usando_postgres(), reason="concorrência real exige PostgreSQL")
def test_estornos_concorrentes_so_um_vence(app, familia):
    resp, (ana, _) = familia
    original = _lancar(resp, ana, T.CREDITO_TAREFA, "BRL", 10)
    db.session.commit()
    ids = (resp.familia_id, original.id, resp.id)
    resultados, barreira = [], threading.Barrier(4)

    def tentar():
        with app.app_context():
            barreira.wait()
            try:
                ledger.estornar(familia_id=ids[0], lancamento_id=ids[1], autor_id=ids[2], motivo="concorrente")
                db.session.commit()
                resultados.append("ok")
            except (ledger.JaEstornado, IntegrityError):
                db.session.rollback()
                resultados.append("recusado")
            finally:
                db.session.remove()

    threads = [threading.Thread(target=tentar) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(resultados) == ["ok", "recusado", "recusado", "recusado"]
    assert ledger.saldo(ana.id, "BRL") == 0


@pytest.mark.skipif(not usando_postgres(), reason="concorrência real exige PostgreSQL")
def test_debitos_concorrentes_respeitam_piso_zero(app, familia):
    resp, (ana, _) = familia
    _lancar(resp, ana, T.CREDITO_TAREFA, "PONTOS", 5)
    db.session.commit()
    ids = (resp.familia_id, ana.id)
    resultados, barreira = [], threading.Barrier(5)

    def tentar():
        with app.app_context():
            barreira.wait()
            try:
                ledger.lancar(familia_id=ids[0], crianca_id=ids[1], tipo=T.DEBITO_RESGATE, unidade="PONTOS", valor=-2)
                db.session.commit()
                resultados.append("ok")
            except ledger.SaldoInsuficiente:
                db.session.rollback()
                resultados.append("recusado")
            finally:
                db.session.remove()

    threads = [threading.Thread(target=tentar) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert resultados.count("ok") == 2
    assert ledger.saldo(ana.id, "PONTOS") == 1
