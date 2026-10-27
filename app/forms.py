from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from app.services.senhas import SENHA_MIN
from app.services.valores import ValorInvalido, ler_decimal

EXTENSOES_IMAGEM = ["jpg", "jpeg", "png", "webp", "gif"]
MSG_OBRIGATORIO = "Campo obrigatório."
PIN_VALIDADORES = [DataRequired(MSG_OBRIGATORIO), Regexp(r"^\d{4,6}$", message="Use de 4 a 6 dígitos.")]


def validar_valor_positivo(form, campo):
    if not campo.data:
        return
    try:
        valor = ler_decimal(campo.data)
    except ValorInvalido as exc:
        raise ValidationError("Valor inválido.") from exc
    if valor <= 0:
        raise ValidationError("Informe um valor maior que zero.")


class EntrarForm(FlaskForm):
    email = EmailField("E-mail", validators=[DataRequired(MSG_OBRIGATORIO), Email("E-mail inválido.")])
    senha = PasswordField("Senha", validators=[DataRequired(MSG_OBRIGATORIO)])


class PrimeiroAcessoForm(FlaskForm):
    nome_familia = StringField("Nome da família", validators=[DataRequired(MSG_OBRIGATORIO), Length(max=100)])
    nome = StringField("Seu nome", validators=[DataRequired(MSG_OBRIGATORIO), Length(max=100)])
    email = EmailField("E-mail", validators=[DataRequired(MSG_OBRIGATORIO), Email("E-mail inválido."), Length(max=255)])
    senha = PasswordField(
        "Senha",
        validators=[DataRequired(MSG_OBRIGATORIO), Length(min=SENHA_MIN, message=f"Mínimo de {SENHA_MIN} caracteres.")],
    )
    confirmar_senha = PasswordField("Confirme a senha", validators=[EqualTo("senha", "As senhas não conferem.")])
    pin = PasswordField("PIN parental (4 a 6 dígitos)", validators=PIN_VALIDADORES)
    confirmar_pin = PasswordField("Confirme o PIN", validators=[EqualTo("pin", "Os PINs não conferem.")])


class CriancaForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(MSG_OBRIGATORIO), Length(max=100)])
    data_nascimento = DateField("Data de nascimento (opcional)", validators=[Optional()])
    cor_avatar = StringField(
        "Cor do avatar",
        default="#4f86f7",
        validators=[DataRequired(MSG_OBRIGATORIO), Regexp(r"^#[0-9a-fA-F]{6}$", message="Cor inválida.")],
    )
    foto = FileField("Foto", validators=[FileAllowed(EXTENSOES_IMAGEM, "Envie uma imagem (JPG, PNG, WEBP ou GIF).")])
    remover_foto = BooleanField("Remover a foto atual")


class ResponsavelForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(MSG_OBRIGATORIO), Length(max=100)])
    email = EmailField("E-mail", validators=[DataRequired(MSG_OBRIGATORIO), Email("E-mail inválido."), Length(max=255)])
    senha = PasswordField(
        "Senha inicial",
        validators=[DataRequired(MSG_OBRIGATORIO), Length(min=SENHA_MIN, message=f"Mínimo de {SENHA_MIN} caracteres.")],
    )


class FamiliaForm(FlaskForm):
    nome = StringField("Nome da família", validators=[DataRequired(MSG_OBRIGATORIO), Length(max=100)])


class ConfiguracaoForm(FlaskForm):
    permite_saldo_negativo = BooleanField("Permitir saldo negativo")
    advertencias_antes_penalidade = IntegerField(
        "Advertências antes da penalidade",
        validators=[InputRequired(MSG_OBRIGATORIO), NumberRange(min=0, max=10, message="Entre 0 e 10.")],
    )
    penalidade_max_diaria_brl = StringField(
        "Penalidade máxima por dia, em R$ (vazio = sem limite)", validators=[Optional(), validar_valor_positivo]
    )
    penalidade_max_diaria_pontos = IntegerField(
        "Penalidade máxima por dia, em pontos (vazio = sem limite)",
        validators=[Optional(), NumberRange(min=1, message="Informe um valor maior que zero.")],
    )
    som_ativo = BooleanField("Sons ligados na tela da criança")


class TrocarPinForm(FlaskForm):
    senha_atual = PasswordField("Sua senha", validators=[DataRequired(MSG_OBRIGATORIO)])
    pin = PasswordField("Novo PIN (4 a 6 dígitos)", validators=PIN_VALIDADORES)
    confirmar_pin = PasswordField("Confirme o novo PIN", validators=[EqualTo("pin", "Os PINs não conferem.")])


class TrocarSenhaForm(FlaskForm):
    senha_atual = PasswordField("Senha atual", validators=[DataRequired(MSG_OBRIGATORIO)])
    senha = PasswordField(
        "Nova senha",
        validators=[DataRequired(MSG_OBRIGATORIO), Length(min=SENHA_MIN, message=f"Mínimo de {SENHA_MIN} caracteres.")],
    )
    confirmar_senha = PasswordField("Confirme a nova senha", validators=[EqualTo("senha", "As senhas não conferem.")])


class AjusteForm(FlaskForm):
    unidade = SelectField("Unidade", choices=[("PONTOS", "Pontos"), ("BRL", "R$")])
    direcao = SelectField("Tipo", choices=[("credito", "Acrescentar"), ("debito", "Retirar")])
    valor = StringField("Valor", validators=[DataRequired(MSG_OBRIGATORIO), validar_valor_positivo])
    motivo = TextAreaField("Motivo", validators=[DataRequired("O motivo é obrigatório."), Length(max=500)])


class EstornoForm(FlaskForm):
    motivo = TextAreaField("Motivo do estorno", validators=[DataRequired("O motivo é obrigatório."), Length(max=500)])


class PinForm(FlaskForm):
    pin = PasswordField("PIN", validators=PIN_VALIDADORES)


class VazioForm(FlaskForm):
    """Só para carregar o token CSRF em botões de ação."""
