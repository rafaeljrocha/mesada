from sqlalchemy import func, select

from app.extensions import db
from app.models import ConfiguracaoFamilia, Crianca, Familia, Responsavel
from app.services import auditoria
from app.services.senhas import SENHA_MIN, gerar_hash, pin_valido


class ErroCadastro(ValueError):
    pass


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def email_em_uso(email: str, exceto_id: int | None = None) -> bool:
    consulta = select(func.count()).select_from(Responsavel).where(
        Responsavel.email == normalizar_email(email)
    )
    if exceto_id is not None:
        consulta = consulta.where(Responsavel.id != exceto_id)
    return db.session.scalar(consulta) > 0


def existe_familia() -> bool:
    return db.session.scalar(select(func.count()).select_from(Familia)) > 0


def criar_familia(*, nome_familia: str, nome_responsavel: str, email: str, senha: str, pin: str) -> Responsavel:
    if len(senha or "") < SENHA_MIN:
        raise ErroCadastro(f"a senha deve ter pelo menos {SENHA_MIN} caracteres")
    if not pin_valido(pin):
        raise ErroCadastro("o PIN deve ter de 4 a 6 dígitos")
    if email_em_uso(email):
        raise ErroCadastro("este e-mail já está cadastrado")

    familia = Familia(nome=nome_familia.strip(), pin_parental_hash=gerar_hash(pin))
    familia.configuracao = ConfiguracaoFamilia()
    db.session.add(familia)
    db.session.flush()
    responsavel = Responsavel(
        familia_id=familia.id,
        nome=nome_responsavel.strip(),
        email=normalizar_email(email),
        senha_hash=gerar_hash(senha),
    )
    db.session.add(responsavel)
    db.session.flush()
    auditoria.registrar(
        familia_id=familia.id, autor_id=responsavel.id, acao="criar", entidade="familia",
        entidade_id=familia.id, depois=auditoria.instantaneo(familia),
    )
    return responsavel


def criancas_da_familia(familia_id: int, somente_ativas: bool = False) -> list[Crianca]:
    consulta = select(Crianca).where(Crianca.familia_id == familia_id).order_by(Crianca.nome)
    if somente_ativas:
        consulta = consulta.where(Crianca.ativo.is_(True))
    return list(db.session.scalars(consulta))


def obter_crianca(familia_id: int, crianca_id: int) -> Crianca | None:
    return db.session.scalar(
        select(Crianca).where(Crianca.id == crianca_id, Crianca.familia_id == familia_id)
    )


def responsaveis_da_familia(familia_id: int) -> list[Responsavel]:
    return list(
        db.session.scalars(
            select(Responsavel).where(Responsavel.familia_id == familia_id).order_by(Responsavel.nome)
        )
    )


def obter_responsavel(familia_id: int, responsavel_id: int) -> Responsavel | None:
    return db.session.scalar(
        select(Responsavel).where(Responsavel.id == responsavel_id, Responsavel.familia_id == familia_id)
    )


def contar_responsaveis_ativos(familia_id: int) -> int:
    return db.session.scalar(
        select(func.count()).select_from(Responsavel).where(
            Responsavel.familia_id == familia_id, Responsavel.ativo.is_(True)
        )
    )
