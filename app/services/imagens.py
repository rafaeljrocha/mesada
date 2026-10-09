"""Upload de imagens: validação do tipo real, remoção de EXIF, redimensionamento.

As imagens ficam em UPLOAD_DIR/familia_<id>/<subpasta>/<uuid>.webp, dentro do
volume persistente, e só são servidas pela rota autenticada /midia, que
confere se o arquivo pertence à família do usuário.
"""

import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

# Proteção contra "decompression bomb".
Image.MAX_IMAGE_PIXELS = 40_000_000

FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP", "GIF"}


class ImagemInvalida(ValueError):
    pass


def _pasta_upload() -> Path:
    return Path(current_app.config["UPLOAD_DIR"])


def salvar_imagem(arquivo, familia_id: int, subpasta: str) -> str:
    """Valida, normaliza e grava a imagem. Retorna o caminho relativo."""
    if arquivo is None or not getattr(arquivo, "filename", ""):
        raise ImagemInvalida("nenhum arquivo enviado")

    try:
        # 1ª passagem: confere a integridade do arquivo (o tipo vem do
        # conteúdo, não da extensão nem do Content-Type enviado).
        imagem = Image.open(arquivo.stream)
        formato = imagem.format
        imagem.verify()
        if formato not in FORMATOS_ACEITOS:
            raise ImagemInvalida("formato não aceito; use JPG, PNG, WEBP ou GIF")
        # 2ª passagem: verify() invalida o objeto; reabre para processar.
        arquivo.stream.seek(0)
        imagem = Image.open(arquivo.stream)
        imagem.seek(0)  # GIF animado: só o primeiro quadro
        imagem = ImageOps.exif_transpose(imagem)
        imagem.load()
    except ImagemInvalida:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ImagemInvalida("o arquivo enviado não é uma imagem válida") from exc

    imagem = imagem.convert("RGBA" if imagem.mode in ("RGBA", "LA", "P") else "RGB")
    lado_max = current_app.config["IMAGEM_LADO_MAX"]
    imagem.thumbnail((lado_max, lado_max))

    relativo = Path(f"familia_{int(familia_id)}") / subpasta / f"{uuid.uuid4().hex}.webp"
    destino = _pasta_upload() / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Salvar sem passar exif/icc descarta todos os metadados (inclusive GPS).
    imagem.save(destino, format="WEBP", quality=82, method=4)
    return relativo.as_posix()


def remover_imagem(relativo: str | None) -> None:
    if not relativo:
        return
    caminho = resolver(relativo)
    if caminho and caminho.is_file():
        caminho.unlink()


def resolver(relativo: str) -> Path | None:
    """Converte o caminho relativo em absoluto, recusando path traversal."""
    base = _pasta_upload().resolve()
    caminho = (base / relativo).resolve()
    if base not in caminho.parents:
        return None
    return caminho


def pertence_a_familia(relativo: str, familia_id: int) -> bool:
    partes = Path(relativo).parts
    return bool(partes) and partes[0] == f"familia_{int(familia_id)}"
