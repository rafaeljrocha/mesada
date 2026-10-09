"""Operações do livro-razão.

Regras (seção 7 da especificação e decisões em docs/decisoes.md):

- O ledger só recebe INSERT. Correções são feitas por novos lançamentos
  (ESTORNO ou AJUSTE_MANUAL), nunca por UPDATE/DELETE.
- Saldo = soma dos lançamentos por (criança, unidade). Não há saldo
  materializado; não existe nada a "reconciliar".
- Toda operação que movimenta saldo trava a linha da criança
  (SELECT ... FOR UPDATE) para serializar operações concorrentes sobre a
  mesma criança. A transação é encerrada (commit/rollback) por quem chama.
- As funções fazem flush, mas não commit.
"""

from decimal import Decimal

from sqlalchemy import event, func, select

from app.extensions import db
from app.models import ConfiguracaoFamilia, Crianca, Lancamento, TipoLancamento, Unidade
from app.models.lancamento import TIPOS_CREDITO, TIPOS_DEBITO
from app.services.valores import ValorInvalido, ler_decimal, quantizar


class ErroLedger(Exception):
    """Erro de regra de negócio do ledger (mensagem exibível ao responsável)."""


class CriancaNaoEncontrada(ErroLedger):
    pass


class LancamentoNaoEncontrado(ErroLedger):
    pass


class SaldoInsuficiente(ErroLedger):
    pass


class JaEstornado(ErroLedger):
    pass


class LancamentoImutavel(RuntimeError):
    pass


@event.listens_for(Lancamento, "before_update")
def _impedir_update(mapper, connection, alvo):
    raise LancamentoImutavel("lançamentos são imutáveis; use estorno ou ajuste")


@event.listens_for(Lancamento, "before_delete")
def _impedir_delete(mapper, connection, alvo):
    raise LancamentoImutavel("lançamentos são imutáveis; use estorno ou ajuste")


def _para_decimal(total) -> Decimal:
    # SQLite devolve float na soma; PostgreSQL devolve Decimal.
    return quantizar(Decimal(str(total or 0)))


def saldo(crianca_id: int, unidade: Unidade | str) -> Decimal:
    total = db.session.scalar(
        select(func.coalesce(func.sum(Lancamento.valor), 0)).where(
            Lancamento.crianca_id == crianca_id,
            Lancamento.unidade == Unidade(unidade).value,
        )
    )
    return _para_decimal(total)


def saldos(crianca_id: int) -> dict[str, Decimal]:
    return {u.value: saldo(crianca_id, u) for u in Unidade}


def _travar_crianca(familia_id: int, crianca_id: int) -> Crianca:
    crianca = db.session.execute(
        select(Crianca)
        .where(Crianca.id == crianca_id, Crianca.familia_id == familia_id)
        .with_for_update()
    ).scalar_one_or_none()
    if crianca is None:
        raise CriancaNaoEncontrada("criança não encontrada nesta família")
    return crianca


def _permite_negativo(familia_id: int) -> bool:
    config = db.session.get(ConfiguracaoFamilia, familia_id)
    return bool(config and config.permite_saldo_negativo)


def _normalizar_valor(tipo: TipoLancamento, unidade: Unidade, valor) -> Decimal:
    try:
        valor = quantizar(ler_decimal(valor))
    except ValorInvalido as exc:
        raise ErroLedger(str(exc)) from exc
    if valor == 0:
        raise ErroLedger("o valor do lançamento não pode ser zero")
    if abs(valor) >= Decimal("100000000"):
        raise ErroLedger("valor fora do limite permitido")
    if unidade is Unidade.PONTOS and valor != valor.to_integral_value():
        raise ErroLedger("pontos devem ser números inteiros")
    if tipo in TIPOS_CREDITO and valor < 0:
        raise ErroLedger(f"{tipo.value} deve ter valor positivo")
    if tipo in TIPOS_DEBITO and valor > 0:
        raise ErroLedger(f"{tipo.value} deve ter valor negativo")
    if tipo is TipoLancamento.PAGAMENTO and unidade is not Unidade.BRL:
        raise ErroLedger("pagamento só existe em R$")
    return valor


def lancar(*, familia_id: int, crianca_id: int, tipo, unidade, valor, autor_id: int | None = None,
           observacao: str | None = None, lote_id: str | None = None,
           permitir_negativo: bool | None = None) -> Lancamento:
    """Registra um lançamento (crédito ou débito) que não seja estorno.

    `valor` já vem com sinal. Débitos respeitam a regra de saldo negativo da
    família (decisão 4), a menos que `permitir_negativo` seja informado.
    """
    tipo = TipoLancamento(tipo)
    unidade = Unidade(unidade)
    if tipo is TipoLancamento.ESTORNO:
        raise ErroLedger("estornos devem ser feitos por estornar()")
    observacao = (observacao or "").strip() or None
    if tipo is TipoLancamento.AJUSTE_MANUAL and not observacao:
        raise ErroLedger("ajuste manual exige motivo")
    valor = _normalizar_valor(tipo, unidade, valor)

    crianca = _travar_crianca(familia_id, crianca_id)
    if not crianca.ativo:
        raise ErroLedger("criança inativa não recebe novos lançamentos")

    if valor < 0:
        if tipo is TipoLancamento.PAGAMENTO:
            # Decisão P2: pagamento limitado ao saldo em R$, sempre.
            permitir_negativo = False
        elif permitir_negativo is None:
            permitir_negativo = _permite_negativo(familia_id)
        if not permitir_negativo and saldo(crianca_id, unidade) + valor < 0:
            raise SaldoInsuficiente("saldo insuficiente para este débito")

    lancamento = Lancamento(
        familia_id=familia_id,
        crianca_id=crianca_id,
        tipo=tipo.value,
        unidade=unidade.value,
        valor=valor,
        observacao=observacao,
        autor_responsavel_id=autor_id,
        lote_id=lote_id,
    )
    db.session.add(lancamento)
    db.session.flush()
    return lancamento


def debitar_limitado_ao_saldo(*, familia_id: int, crianca_id: int, tipo, unidade, valor,
                              autor_id: int | None = None, observacao: str | None = None,
                              lote_id: str | None = None) -> Lancamento | None:
    """Débito que, com piso zero, é reduzido ao saldo disponível.

    Usado por penalidades (decisão 4 b): a penalidade nunca deixa o saldo
    negativo; se o saldo for zero, nenhum lançamento é gerado (retorna None).
    Se a família permitir saldo negativo, debita o valor integral.
    """
    tipo = TipoLancamento(tipo)
    unidade = Unidade(unidade)
    valor = _normalizar_valor(tipo, unidade, valor)
    _travar_crianca(familia_id, crianca_id)
    if not _permite_negativo(familia_id):
        disponivel = max(saldo(crianca_id, unidade), Decimal("0"))
        if unidade is Unidade.PONTOS:
            disponivel = disponivel.to_integral_value(rounding="ROUND_FLOOR")
        valor = -min(-valor, disponivel)
        if valor == 0:
            return None
    return lancar(
        familia_id=familia_id, crianca_id=crianca_id, tipo=tipo, unidade=unidade, valor=valor,
        autor_id=autor_id, observacao=observacao, lote_id=lote_id, permitir_negativo=True,
    )


def estornar(*, familia_id: int, lancamento_id: int, autor_id: int | None, motivo: str) -> Lancamento:
    """Gera o lançamento de ESTORNO de outro lançamento.

    - O original nunca é alterado nem apagado.
    - Um lançamento só pode ser estornado uma vez (UNIQUE em estorno_de_id).
    - Estorno de estorno não é permitido.
    - Estorno não é bloqueado pelo piso zero: é correção de erro (ver
      pendência P7 em docs/decisoes.md).
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErroLedger("estorno exige motivo")

    original = db.session.get(Lancamento, lancamento_id)
    if original is None or original.familia_id != familia_id:
        raise LancamentoNaoEncontrado("lançamento não encontrado")
    if original.tipo == TipoLancamento.ESTORNO.value:
        raise ErroLedger("não é possível estornar um estorno")

    # A trava na criança serializa estornos concorrentes do mesmo lançamento;
    # o UNIQUE em estorno_de_id é a última linha de defesa.
    _travar_crianca(familia_id, original.crianca_id)
    if lancamento_estornado(original.id):
        raise JaEstornado("este lançamento já foi estornado")

    estorno = Lancamento(
        familia_id=familia_id,
        crianca_id=original.crianca_id,
        tipo=TipoLancamento.ESTORNO.value,
        unidade=original.unidade,
        valor=-Decimal(original.valor),
        observacao=motivo,
        autor_responsavel_id=autor_id,
        estorno_de_id=original.id,
    )
    db.session.add(estorno)
    db.session.flush()
    return estorno


def lancamento_estornado(lancamento_id: int) -> bool:
    return db.session.scalar(
        select(func.count()).select_from(Lancamento).where(Lancamento.estorno_de_id == lancamento_id)
    ) > 0


def ids_estornados(ids: list[int]) -> set[int]:
    if not ids:
        return set()
    return set(
        db.session.scalars(select(Lancamento.estorno_de_id).where(Lancamento.estorno_de_id.in_(ids)))
    )


def extrato(familia_id: int, crianca_id: int, unidade: str | None = None, limite: int = 200):
    consulta = (
        select(Lancamento)
        .where(Lancamento.familia_id == familia_id, Lancamento.crianca_id == crianca_id)
        .order_by(Lancamento.criado_em.desc(), Lancamento.id.desc())
        .limit(limite)
    )
    if unidade:
        consulta = consulta.where(Lancamento.unidade == Unidade(unidade).value)
    return list(db.session.scalars(consulta))
