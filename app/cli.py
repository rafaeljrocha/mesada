"""Comandos de manutenção (rodam pelo console do EasyPanel).

    flask --app wsgi redefinir-senha email@exemplo.com
"""

import getpass

import click
from flask import Flask
from sqlalchemy import select

from app.extensions import db
from app.models import Responsavel
from app.services import auditoria
from app.services.familias import normalizar_email
from app.services.senhas import SENHA_MIN, gerar_hash


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("redefinir-senha")
    @click.argument("email")
    def redefinir_senha(email: str):
        """Define nova senha para um responsável (recuperação de acesso)."""
        responsavel = db.session.scalar(select(Responsavel).where(Responsavel.email == normalizar_email(email)))
        if responsavel is None:
            raise click.ClickException("responsável não encontrado")
        senha = getpass.getpass("Nova senha: ")
        if len(senha) < SENHA_MIN:
            raise click.ClickException(f"a senha deve ter pelo menos {SENHA_MIN} caracteres")
        if senha != getpass.getpass("Repita a nova senha: "):
            raise click.ClickException("as senhas não conferem")
        responsavel.senha_hash = gerar_hash(senha)
        responsavel.ativo = True
        auditoria.registrar(
            familia_id=responsavel.familia_id, autor_id=None, acao="redefinir_senha_console",
            entidade="responsavel", entidade_id=responsavel.id,
        )
        db.session.commit()
        click.echo("Senha redefinida.")
