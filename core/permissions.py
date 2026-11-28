
from django.db.models import Q
from rest_framework.permissions import BasePermission


# Identificadores de roles existentes en GerIApp
ROL_ADMINISTRADOR = 1
ROL_ENCARGADO = 2
ROL_CUIDADOR = 3
ROL_SUPERADMINISTRADOR = 4

METODOS_LECTURA = ('GET', 'HEAD', 'OPTIONS')
METODOS_ESCRITURA_HISTORIA = ('POST', 'PUT', 'PATCH')


def obtener_id_rol(usuario):
    """Obtiene el ID del rol del usuario autenticado mediante la relación real Roles."""
    rol = getattr(usuario, 'id_rol', None)

    if rol is None:
        return None

    return getattr(rol, 'id_rol', None)


def obtener_usuario_clinico_activo(usuario):
    """
    Acepta UsuarioAutenticado (request.user) o una instancia directa de Usuarios,
    verificando que corresponda a un usuario clínico real y activo (excluyendo
    anónimos, inactivos o servicios externos como N8NAuthenticatedUser).
    """
    from .models import Usuarios

    if not usuario:
        return None

    if isinstance(usuario, Usuarios):
        usuario_modelo = usuario
    else:
        if getattr(usuario, 'is_authenticated', False) is not True:
            return None
        usuario_modelo = getattr(usuario, 'usuario', None)
        if not isinstance(usuario_modelo, Usuarios):
            return None

    if getattr(usuario_modelo, 'estado', False) is not True:
        return None

    return usuario_modelo


def obtener_id_rol_real(usuario):
    """
    Obtiene el ID del rol exclusivamente desde la relación real usuario.id_rol.id_rol,
    verificando que tanto el usuario como el rol estén activos.
    Nunca utiliza usuario.id_usuario ni usuario.pk.
    """
    usuario_modelo = obtener_usuario_clinico_activo(usuario)
    if usuario_modelo is None:
        return None

    rol = getattr(usuario_modelo, 'id_rol', None)
    if rol is None:
        return None

    if getattr(rol, 'estado', False) is not True:
        return None

    id_rol = getattr(rol, 'id_rol', None)
    return int(id_rol) if id_rol is not None else None


def obtener_id_sede_activa(usuario):
    """
    Obtiene el id_sede de un usuario clínico activo verificando que la sede
    exista y se encuentre activa.
    """
    usuario_modelo = obtener_usuario_clinico_activo(usuario)
    if usuario_modelo is None:
        return None

    sede = getattr(usuario_modelo, 'id_sede', None)
    if sede is None:
        return None

    if getattr(sede, 'estado', False) is not True:
        return None

    id_sede = getattr(sede, 'id_sede', None)
    return int(id_sede) if id_sede is not None else None


def _filtrar_pacientes_de_sede(sede_id):
    """
    Retorna los pacientes pertenecientes estrictamente a la sede indicada,
    impidiendo cruces si la habitación o id_sede apuntan a otra sede.
    """
    from .models import Habitaciones, Pacientes

    habitaciones_sede = Habitaciones.objects.filter(
        id_sede_id=sede_id
    ).values_list('id_habitacion', flat=True)

    habitaciones_otras_sedes = Habitaciones.objects.exclude(
        id_sede_id=sede_id
    ).values_list('id_habitacion', flat=True)

    return (
        Pacientes.objects
        .filter(Q(habitacion__in=habitaciones_sede) | Q(id_sede_id=sede_id))
        .filter(Q(id_sede__isnull=True) | Q(id_sede_id=sede_id))
        .exclude(habitacion__in=habitaciones_otras_sedes)
        .distinct()
    )


def obtener_pacientes_consulta_historia(usuario, ahora=None):
    """
    Retorna el QuerySet de Pacientes cuya historia clínica puede consultar el usuario:
    - Rol 1 (Administrador): pacientes de su propia sede activa.
    - Rol 3 (Cuidador): pacientes de su propia sede activa con asignación activa y vigente.
    - Rol 2 (Encargado), Rol 4 (Superadministrador) u otros: ningún paciente.
    """
    from .asignaciones_vigencia import filtrar_asignaciones_vigentes
    from .models import Pacientes

    rol_id = obtener_id_rol_real(usuario)
    if rol_id not in (ROL_ADMINISTRADOR, ROL_CUIDADOR):
        return Pacientes.objects.none()

    sede_id = obtener_id_sede_activa(usuario)
    if sede_id is None:
        return Pacientes.objects.none()

    pacientes_sede = _filtrar_pacientes_de_sede(sede_id)

    if rol_id == ROL_ADMINISTRADOR:
        return pacientes_sede

    usuario_modelo = obtener_usuario_clinico_activo(usuario)
    ids_asignados_vigentes = (
        filtrar_asignaciones_vigentes(ahora=ahora)
        .filter(id_usuario_id=usuario_modelo.id_usuario)
        .values_list('id_paciente_id', flat=True)
    )
    return pacientes_sede.filter(id_paciente__in=ids_asignados_vigentes).distinct()


def puede_consultar_historia_paciente(usuario, paciente, ahora=None):
    """Verifica si el usuario puede consultar la historia clínica vigente del paciente."""
    id_paciente = getattr(paciente, 'id_paciente', None)
    if id_paciente is None:
        return False

    return obtener_pacientes_consulta_historia(
        usuario,
        ahora=ahora,
    ).filter(id_paciente=id_paciente).exists()


def puede_escribir_historia_paciente(usuario, paciente):
    """
    Verifica permisos de carga, edición y reemplazo de historia clínica:
    exclusivamente Rol 1 (Administrador) sobre pacientes de su propia sede activa.
    """
    if obtener_id_rol_real(usuario) != ROL_ADMINISTRADOR:
        return False

    id_paciente = getattr(paciente, 'id_paciente', None)
    if id_paciente is None:
        return False

    sede_id = obtener_id_sede_activa(usuario)
    if sede_id is None:
        return False

    return _filtrar_pacientes_de_sede(sede_id).filter(
        id_paciente=id_paciente
    ).exists()


def puede_consultar_documento_historico(usuario, paciente):
    """
    Los documentos históricos reemplazados (estado=False) solo pueden ser
    consultados por el Administrador (id_rol=1) de la misma sede del paciente.
    """
    return puede_escribir_historia_paciente(usuario, paciente)


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


class PermisoHistoriaClinica(BasePermission):
    """
    Control de acceso en Backend para Historias Clínicas y Documentos PDF:
    - Rol 1 (Administrador): lectura y escritura solo en su propia sede; acceso a históricos.
    - Rol 2 (Encargado): sin acceso a historias clínicas (HTTP 403).
    - Rol 3 (Cuidador): solo lectura de pacientes de su sede con asignación activa y vigente.
    - Rol 4 (Superadministrador): sin acceso clínico (HTTP 403).
    - DELETE: bloqueado para todos los roles.
    """

    message = 'No tienes permisos para realizar esta operación sobre historias clínicas.'

    def has_permission(self, request, view):
        if request.method == 'DELETE':
            self.message = (
                'No está permitido eliminar historias clínicas ni documentos históricos.'
            )
            return False

        rol_id = obtener_id_rol_real(request.user)
        if rol_id == ROL_SUPERADMINISTRADOR:
            self.message = 'El superadministrador no tiene acceso a información clínica.'
            return False

        if rol_id == ROL_ENCARGADO:
            self.message = 'El rol Encargado no tiene acceso a historias clínicas.'
            return False

        if rol_id not in (ROL_ADMINISTRADOR, ROL_CUIDADOR):
            self.message = 'No tienes un rol clínico activo autorizado.'
            return False

        if obtener_id_sede_activa(request.user) is None:
            self.message = 'Tu usuario no tiene una sede activa asignada.'
            return False

        if request.method in METODOS_LECTURA:
            return True

        if request.method in METODOS_ESCRITURA_HISTORIA:
            if rol_id != ROL_ADMINISTRADOR:
                self.message = (
                    'Solo el Administrador de sede puede cargar, editar o reemplazar '
                    'historias clínicas.'
                )
                return False
            return True

        return False

    def has_object_permission(self, request, view, obj):
        from .models import DocumentosHistoriaClinica, Pacientes

        if request.method == 'DELETE':
            self.message = (
                'No está permitido eliminar historias clínicas ni documentos históricos.'
            )
            return False

        paciente = (
            obj
            if isinstance(obj, Pacientes)
            else getattr(obj, 'id_paciente', None)
        )

        if request.method in METODOS_LECTURA:
            if isinstance(obj, DocumentosHistoriaClinica) and obj.estado is not True:
                autorizado = puede_consultar_documento_historico(request.user, paciente)
                if not autorizado:
                    self.message = (
                        'Solo el Administrador de la sede del paciente puede consultar '
                        'documentos históricos.'
                    )
                return autorizado

            autorizado = puede_consultar_historia_paciente(request.user, paciente)
            if not autorizado:
                self.message = (
                    'No tienes permisos para consultar la historia clínica de este paciente.'
                )
            return autorizado

        if request.method in METODOS_ESCRITURA_HISTORIA:
            autorizado = puede_escribir_historia_paciente(request.user, paciente)
            if not autorizado:
                self.message = (
                    'Solo el Administrador de la sede del paciente puede modificar '
                    'esta historia clínica.'
                )
            return autorizado

        return False
