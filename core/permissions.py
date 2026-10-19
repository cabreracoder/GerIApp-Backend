
from rest_framework.permissions import BasePermission


# Identificadores de roles existentes en GerIApp
ROL_ADMINISTRADOR = 1
ROL_ENCARGADO = 2
ROL_CUIDADOR = 3
ROL_SUPERADMINISTRADOR = 4


def obtener_id_rol(usuario):
    """Obtiene el ID del rol del usuario autenticado."""
    rol = getattr(usuario, 'id_rol', None)

    if rol is None:
        return None

    return getattr(rol, 'id_rol', None)


class EsSuperadministrador(BasePermission):
    """Permite el acceso únicamente al Súper Administrador."""

    message = 'No tienes permisos para realizar esta operación.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and obtener_id_rol(request.user) == ROL_SUPERADMINISTRADOR
        )


class EsSuperadministradorOMetodoLectura(BasePermission):
    """
    Permite consultar información a usuarios autenticados.
    Las operaciones de escritura quedan reservadas al Súper Administrador.
    """

    message = 'Solo el Súper Administrador puede modificar este recurso.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True

        return obtener_id_rol(request.user) == ROL_SUPERADMINISTRADOR
