"""Configuração lida exclusivamente de variáveis de ambiente.

Nenhuma credencial fica no código. Veja `.env.example` para a lista completa.
"""

import os
import secrets
from datetime import timedelta
from pathlib import Path

AMBIENTES = {"producao", "desenvolvimento", "teste"}


class ErroConfiguracao(RuntimeError):
    pass


def _bool(nome: str, padrao: bool) -> bool:
    valor = os.environ.get(nome)
    if valor is None or valor.strip() == "":
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _int(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    if valor is None or valor.strip() == "":
        return padrao
    try:
        return int(valor)
    except ValueError as exc:
        raise ErroConfiguracao(f"{nome} deve ser um número inteiro") from exc


def _normalizar_url_banco(url: str) -> str:
    # EasyPanel e outros painéis entregam "postgres://"; o SQLAlchemy 2 exige o
    # nome do dialeto e usamos o driver psycopg 3.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def carregar_config(sobrescrever: dict | None = None) -> dict:
    sobrescrever = sobrescrever or {}
    ambiente = sobrescrever.get("APP_ENV") or os.environ.get("APP_ENV", "producao")
    if ambiente not in AMBIENTES:
        raise ErroConfiguracao(f"APP_ENV inválido: {ambiente!r}")

    data_dir = Path(sobrescrever.get("DATA_DIR") or os.environ.get("DATA_DIR", "./data")).resolve()

    secret_key = sobrescrever.get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if not secret_key:
        if ambiente == "producao":
            raise ErroConfiguracao("SECRET_KEY é obrigatória em produção")
        secret_key = secrets.token_hex(32)

    url_banco = sobrescrever.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not url_banco:
        if ambiente == "producao":
            raise ErroConfiguracao("DATABASE_URL é obrigatória em produção")
        # SQLite é aceito somente fora de produção.
        url_banco = f"sqlite:///{data_dir / 'mesada-dev.db'}"
    url_banco = _normalizar_url_banco(url_banco)
    if ambiente == "producao" and url_banco.startswith("sqlite"):
        raise ErroConfiguracao("SQLite não é permitido em produção; use PostgreSQL")

    cookies_seguros = _bool("COOKIES_SEGUROS", ambiente == "producao")
    upload_max_mb = _int("UPLOAD_MAX_MB", 8)

    config = {
        "APP_ENV": ambiente,
        "TESTING": ambiente == "teste",
        "SECRET_KEY": secret_key,
        "SQLALCHEMY_DATABASE_URI": url_banco,
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "DATA_DIR": data_dir,
        "UPLOAD_DIR": data_dir / "uploads",
        "MAX_CONTENT_LENGTH": upload_max_mb * 1024 * 1024,
        "UPLOAD_MAX_MB": upload_max_mb,
        "IMAGEM_LADO_MAX": _int("IMAGEM_LADO_MAX", 1024),
        "PROXY_FIX": _bool("PROXY_FIX", False),
        "CADASTRO_ABERTO": _bool("CADASTRO_ABERTO", False),
        "FUSO_HORARIO": "America/Sao_Paulo",
        # Sessão persistente: o tablet da criança fica "logado" na família.
        "PERMANENT_SESSION_LIFETIME": timedelta(days=_int("SESSAO_DIAS", 30)),
        "SESSION_COOKIE_NAME": "mesada_sessao",
        "SESSION_COOKIE_SECURE": cookies_seguros,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "WTF_CSRF_TIME_LIMIT": None,
        "LOGIN_MAX_FALHAS": _int("LOGIN_MAX_FALHAS", 5),
        "PIN_MAX_FALHAS": _int("PIN_MAX_FALHAS", 5),
        "BLOQUEIO_MINUTOS": _int("BLOQUEIO_MINUTOS", 15),
    }
    config.update(sobrescrever)
    return config
