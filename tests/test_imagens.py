import io

from PIL import Image

from app.extensions import db
from app.models import Crianca
from tests.conftest import entrar, nova_familia


def _jpeg_com_gps(lado=3000) -> bytes:
    imagem = Image.new("RGB", (lado, lado // 2), "red")
    exif = Image.Exif()
    exif[0x010F] = "CameraTeste"  # Make
    exif[0x8825] = {1: "S", 2: (23.0, 33.0, 0.0)}  # GPSInfo
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", exif=exif)
    return saida.getvalue()


def test_upload_remove_exif_redimensiona_e_protege(app, client, familia):
    resp, _ = familia
    original = _jpeg_com_gps()
    assert Image.open(io.BytesIO(original)).getexif()  # o arquivo de teste tem EXIF
    entrar(client)
    resposta = client.post("/pais/criancas/nova", data={
        "nome": "Duda", "cor_avatar": "#ff0000", "foto": (io.BytesIO(original), "foto.jpg"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 302

    crianca = db.session.query(Crianca).filter_by(nome="Duda").one()
    assert crianca.foto.startswith(f"familia_{resp.familia_id}/criancas/")
    caminho = app.config["UPLOAD_DIR"] / crianca.foto
    salvo = Image.open(caminho)
    assert salvo.format == "WEBP"
    assert max(salvo.size) <= app.config["IMAGEM_LADO_MAX"]
    assert not salvo.getexif()
    assert "exif" not in salvo.info

    # A própria família vê; anônimo e outra família não.
    assert client.get(f"/midia/{crianca.foto}").status_code == 200
    anonimo = app.test_client()
    assert anonimo.get(f"/midia/{crianca.foto}").status_code == 302
    nova_familia(nome="Souza", email="mae@outra.com", criancas=())
    outro = app.test_client()
    entrar(outro, email="mae@outra.com")
    assert outro.get(f"/midia/{crianca.foto}").status_code == 404


def test_arquivo_falso_e_recusado(client, familia):
    entrar(client)
    resposta = client.post("/pais/criancas/nova", data={
        "nome": "Duda", "cor_avatar": "#ff0000", "foto": (io.BytesIO(b"<?php echo 1; ?>"), "foto.jpg"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 200
    assert "não é uma imagem válida" in resposta.get_data(as_text=True)
    assert db.session.query(Crianca).filter_by(nome="Duda").count() == 0


def test_path_traversal_na_midia(client, familia):
    resp, _ = familia
    entrar(client)
    assert client.get(f"/midia/familia_{resp.familia_id}/../../teste.db").status_code == 404
    assert client.get(f"/midia/familia_{resp.familia_id}/%2e%2e/%2e%2e/teste.db").status_code == 404


def test_editar_sem_nova_foto_mantem_a_atual(app, client, familia):
    entrar(client)
    client.post("/pais/criancas/nova", data={
        "nome": "Duda", "cor_avatar": "#ff0000", "foto": (io.BytesIO(_jpeg_com_gps(200)), "foto.jpg"),
    }, content_type="multipart/form-data")
    crianca = db.session.query(Crianca).filter_by(nome="Duda").one()
    foto = crianca.foto
    resposta = client.post(f"/pais/criancas/{crianca.id}/editar", data={
        "nome": "Duda Maria", "cor_avatar": "#00ff00",
    }, content_type="multipart/form-data")
    assert resposta.status_code == 302
    db.session.refresh(crianca)
    assert crianca.nome == "Duda Maria" and crianca.foto == foto
    assert (app.config["UPLOAD_DIR"] / foto).is_file()
