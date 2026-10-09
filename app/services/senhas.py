"""Hash de senhas e PIN com Argon2id."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

SENHA_MIN = 10
PIN_REGEX = re.compile(r"^\d{4,6}$")


def gerar_hash(segredo: str) -> str:
    return _hasher.hash(segredo)


def conferir(hash_: str | None, segredo: str) -> bool:
    if not hash_:
        return False
    try:
        return _hasher.verify(hash_, segredo)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def pin_valido(pin: str) -> bool:
    return bool(PIN_REGEX.match(pin or ""))
