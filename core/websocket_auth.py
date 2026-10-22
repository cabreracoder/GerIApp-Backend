
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.core import signing

from .authentication import (
    TOKEN_DURACION,
    TOKEN_SALT,
    UsuarioAutenticado,
)
from .models import Usuarios


@database_sync_to_async
def obtener_usuario_desde_token(token):
    if not token:
        return AnonymousUser()

    try:
        datos = signing.loads(
            token,
            salt=TOKEN_SALT,
            max_age=TOKEN_DURACION,
        )

        id_usuario = datos.get("id_usuario")

        if id_usuario is None:
            return AnonymousUser()

        usuario = Usuarios.objects.get(
            id_usuario=id_usuario
        )

        if not usuario.estado:
            return AnonymousUser()

        return UsuarioAutenticado(usuario)

    except (
        signing.BadSignature,
        Usuarios.DoesNotExist,
        ValueError,
        TypeError,
    ):
        return AnonymousUser()


class GeriAppWebSocketTokenMiddleware:

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        try:
            cabeceras = dict(scope.get("headers", []))
            autorizacion = cabeceras.get(
                b"authorization",
                b"",
            ).decode("utf-8")
        except UnicodeDecodeError:
            autorizacion = ""

        partes = autorizacion.split()

        token = None

        if (
            len(partes) == 2
            and partes[0].lower() == "bearer"
        ):
            token = partes[1]

        scope["user"] = await obtener_usuario_desde_token(
            token
        )

        return await self.inner(scope, receive, send)
