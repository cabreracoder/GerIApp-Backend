
from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import Usuarios


TOKEN_SALT = 'geriapp.auth'
TOKEN_DURACION = 60 * 60 * 24 * 90  # 90 días


def crear_token_usuario(usuario):
    """Genera un token firmado para un usuario de GerIApp."""
    return signing.dumps(
        {'id_usuario': usuario.id_usuario},
        salt=TOKEN_SALT
    )


class UsuarioAutenticado:
    """Permite usar el usuario de GerIApp con DRF."""

    def __init__(self, usuario):
        self.usuario = usuario

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __getattr__(self, nombre):
        return getattr(self.usuario, nombre)


class GeriAppTokenAuthentication(BaseAuthentication):
    """Verifica el token Bearer enviado por el cliente."""

    def authenticate(self, request):
        partes = get_authorization_header(request).split()

        if not partes:
            return None

        if partes[0].lower() != b'bearer':
            return None

        if len(partes) != 2:
            raise AuthenticationFailed('Formato de token inválido.')

        try:
            token = partes[1].decode('utf-8')

            datos = signing.loads(
                token,
                salt=TOKEN_SALT,
                max_age=TOKEN_DURACION
            )

            id_usuario = datos.get('id_usuario')

            if id_usuario is None:
                raise AuthenticationFailed('Token inválido.')

        except (signing.BadSignature, UnicodeDecodeError):
            raise AuthenticationFailed(
                'El token es inválido o ha vencido.'
            )

        try:
            usuario = Usuarios.objects.select_related(
                'id_rol',
                'id_sede'
            ).get(id_usuario=id_usuario)

        except (Usuarios.DoesNotExist, ValueError, TypeError):
            raise AuthenticationFailed(
                'El usuario del token no existe.'
            )

        if not usuario.estado:
            raise AuthenticationFailed(
                'El usuario está inactivo.'
            )

        return UsuarioAutenticado(usuario), token

    def authenticate_header(self, request):
        return 'Bearer'
