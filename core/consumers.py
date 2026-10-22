
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import AsignacionPacienteCuidador
from .permissions import ROL_CUIDADOR


@database_sync_to_async
def cuidador_puede_ver_paciente(usuario, id_paciente):
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False

    # Obtener el modelo de usuario original.
    usuario_modelo = getattr(usuario, "usuario", usuario)

    # Esta primera prueba es para el rol Cuidador.
    rol = getattr(usuario_modelo, "id_rol", None)
    id_rol = getattr(rol, "id_rol", None)

    if id_rol != ROL_CUIDADOR:
        return False

    # Comprobar que tenga una asignación activa al paciente.
    return AsignacionPacienteCuidador.objects.filter(
        id_usuario_id=usuario_modelo.id_usuario,
        id_paciente_id=id_paciente,
        estado__iexact="Activo",
    ).exists()


class CuidadosEnfermeriaConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self.id_paciente = self.scope["url_route"]["kwargs"]["id_paciente"]
        self.nombre_grupo = f"cuidados_paciente_{self.id_paciente}"

        usuario = self.scope.get("user")

        if not usuario or not getattr(usuario, "is_authenticated", False):
            await self.close(code=4401)
            return

        autorizado = await cuidador_puede_ver_paciente(
            usuario,
            self.id_paciente,
        )

        if not autorizado:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(
            self.nombre_grupo,
            self.channel_name,
        )

        await self.accept()

        await self.send_json({
            "tipo": "conexion_establecida",
            "id_paciente": self.id_paciente,
        })

    async def disconnect(self, close_code):
        if hasattr(self, "nombre_grupo"):
            await self.channel_layer.group_discard(
                self.nombre_grupo,
                self.channel_name,
            )
    async def cuidados_actualizados(self, evento):
        await self.send_json({
            "tipo": "cuidados_actualizados",
            "id_paciente": evento["id_paciente"],
            "accion": evento.get("accion", "actualizado"),
        })
