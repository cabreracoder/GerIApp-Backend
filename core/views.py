
from rest_framework import viewsets, status, parsers, mixins
from rest_framework.views import APIView
from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
    action,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import (
    MultiPartParser,
    FormParser,
    JSONParser,
)

from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone


# ==========================================
# IMPORTACIONES DE PYTHON
# ==========================================

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import base64
import logging
import os
import random
import re


# ==========================================
# OTRAS DEPENDENCIAS
# ==========================================

from dateutil.relativedelta import relativedelta

import sib_api_v3_sdk

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from firebase_admin import messaging

from google.oauth2 import id_token
from google.auth.transport import requests

from livekit import api


# ==========================================
# SERVICIOS DEL PROYECTO
# ==========================================

from servicios.cloudinary_service import (
    subir_imagen,
    eliminar_imagen,
)

from reconocimiento_facial.reconocedor import ReconocedorFacial
from reconocimiento_facial.cifrado import cifrar_embedding


# ==========================================
# CONFIGURACIONES Y UTILIDADES LOCALES
# ==========================================

from .firebase_config import inicializar_firebase
from .notificaciones_utils import enviar_notificacion_fcm

from .authentication import GeriAppTokenAuthentication, crear_token_usuario
from .permissions import EsSuperadministradorOMetodoLectura


# ==========================================
# MODELOS
# ==========================================

from .models import (
    AsignacionTurnoUsuario,
    CierreTurno,
    Notificaciones,
    Usuarios,
    Camaras,
    Habitaciones,
    Pacientes,
    AsignacionPacienteCuidador,
    HistoriaClinicas,
    Medicamentos,
    Roles,
    Documentos,
    Enfermedades,
    Diagnosticos,
    Tratamientos,
    TratamientoMedicamento,
    Inventario,
    EntregaMedica,
    DetalleEntregaMedicamento,
    MovimientoMedicamento,
    AplicacionMedicamento,
    TipoInsumo,
    Insumos,
    DetalleEntregaInsumos,
    EntregaInsumo,
    MovimientoInsumo,
    Bitacora,
    Actividades,
    SignosVitales,
    TipoEvento,
    TipoEmergencia,
    EventosAdversos,
    ImagenesEventoAdverso,
    Turnos,
    Permisos,
    PermisosRol,
    FamiliarResponsable,
    PerfilProfesional,
    DisponibilidadUsuario,
    Recomendaciones,
    CuidadosEnfermeria,
    ElementosPaciente,
    RecuperacionPassword,
    NotificacionDestinatario,
    Citas,
    FcmTokens,
    Camas,
    Fundaciones,
    Sedes,
    TiposEventoIa,
    EventosIa,
    EvidenciasIa,
    AsignacionHabitacion,
    GrupoMedicacion,
    FormulacionMedicamentos,
    SeguimientoAdministracionMedicamento,
    ConfiguracionControlesPeriodicos,
    ControlesPeriodicosBitacora,
    RegistrosFaciales,
    DocumentosHistoriaClinica,
)


# ==========================================
# SERIALIZADORES
# ==========================================

from .serializers import (
    AsignacionTurnoUsuarioSerializer,
    DiagnosticosSerializer,
    EnfermedadesSerializer,
    MedicamentosSerializer,
    PacientesSerializer,
    RolesSerializer,
    TratamientoSerializer,
    UsuariosSerializer,
    DocumentosSerializer,
    RegistroUsuarioSerializer,
    HistoriaClinicasSerializer,
    TratamientoMedicamentoSerializer,
    InventarioSerializer,
    EntregaMedicaSerializer,
    DetalleEntregaMedicamentoSerializer,
    MovimientoMedicamentoSerializer,
    AplicacionMedicamentoSerializer,
    TipoInsumoSerializer,
    InsumosSerializer,
    DetalleEntregaInsumoSerializer,
    EntregaInsumoSerializer,
    MovimientoInsumoSerializer,
    BitacoraSerializer,
    ActividadesSerializer,
    SignosVitalesSerializer,
    TipoEventoSerializer,
    TipoEmergenciaSerializer,
    EventosAdversosSerializer,
    ImagenesEventoAdversoSerializer,
    AsignacionPacienteCuidadorSerializer,
    TurnosSerializer,
    PermisosSerializer,
    PermisosRolSerializer,
    FamiliarResponsableSerializer,
    PerfilProfesionalSerializer,
    DisponibilidadUsuarioSerializer,
    CambiarContrasenaSerializer,
    RecomendacionesSerializer,
    CuidadosEnfermeriaSerializer,
    ElementosPacienteSerializer,
    RecuperacionPasswordSerializer,
    NotificacionesSerializer,
    NotificacionDestinatarioSerializer,
    CitasSerializer,
    FcmTokensSerializer,
    CamasSerializer,
    HabitacionesSerializer,
    FundacionesSerializer,
    SedesSerializer,
    CamarasSerializer,
    TiposEventoIaSerializer,
    EventosIaSerializer,
    EvidenciasIaSerializer,
    AsignacionHabitacionSerializer,
    GrupoMedicacionSerializer,
    FormulacionMedicamentosSerializer,
    SeguimientoAdministracionMedicamentoSerializer,
    CierreTurnoSerializer,
    ConfiguracionControlesPeriodicosSerializer,
    ControlesPeriodicosBitacoraSerializer,
    RegistrosFacialesSerializer,
    DocumentosHistoriaClinicaSerializer,
)


# ==========================================
# CONFIGURACIÓN DEL LOGGER
# ==========================================

logger = logging.getLogger(__name__)


# ============================================================
# REGISTRO DE USUARIO
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def registro_usuario(request):
    serializer = RegistroUsuarioSerializer(data=request.data)

    if serializer.is_valid():
        correo = serializer.validated_data['correo']
        numero_documento = serializer.validated_data['numero_documento']

        # Verificar que no exista otro usuario con el mismo correo
        if Usuarios.objects.filter(correo=correo).exists():
            return Response(
                {
                    'error': 'Ya existe un usuario con este correo.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que no exista otro usuario con el mismo documento
        if Usuarios.objects.filter(
            numero_documento=numero_documento
        ).exists():
            return Response(
                {
                    'error': 'Ya existe un usuario con este número de documento.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        usuario = serializer.save()

        return Response(
            {
                'mensaje': 'Usuario registrado correctamente.',
                'usuario': {
                    'id_usuario': usuario.id_usuario,
                    'nombres': usuario.nombres,
                    'apellidos': usuario.apellidos,
                    'correo': usuario.correo,
                    'id_rol': usuario.id_rol_id,
                    'rol': usuario.id_rol.nombre if usuario.id_rol else None,
                    'estado': usuario.estado,
                    'foto': usuario.foto

                }
            },
            status=status.HTTP_200_OK
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# ============================================================
# LOGIN
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def login_usuario(request):
    correo = request.data.get('correo')
    contrasena = request.data.get('contrasena')

    if not correo or not contrasena:
        return Response(
            {
                'error': 'El correo y la contraseña son obligatorios.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        usuario = Usuarios.objects.get(correo=correo)

    except Usuarios.DoesNotExist:
        return Response(
            {
                'error': 'Credenciales inválidas.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not usuario.contrasena:
        return Response(
            {
                'error': 'Este usuario no tiene una contraseña registrada.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Verificar contraseña
    if not check_password(
        contrasena,
        usuario.contrasena
    ):
        return Response(
            {
                'error': 'Credenciales inválidas.'
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Verificar estado del usuario
    if not usuario.estado:
        return Response(
            {
                'error': 'El usuario se encuentra inactivo.'
            },
            status=status.HTTP_403_FORBIDDEN
        )

    return Response(
        {
            'mensaje': 'Inicio de sesión exitoso.',
             'token': crear_token_usuario(usuario),
            'usuario': {
                'id_usuario': usuario.id_usuario,
                'nombres': usuario.nombres,
                'apellidos': usuario.apellidos,
                'correo': usuario.correo,
                'id_rol': usuario.id_rol_id,
                'rol': usuario.id_rol.nombre if usuario.id_rol else None,
                'id_sede': usuario.id_sede_id,
                'estado': usuario.estado,

                # URL de la foto almacenada en Cloudinary
                'foto': usuario.foto
            }
        },
        status=status.HTTP_200_OK
    )
# ============================================================
# LOGIN CON GOOGLE
# ============================================================
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def login_google(request):

    token = request.data.get('token')

    if not token:
        return Response(
            {
                'error': 'Token de Google requerido.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:

        datos_google = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )

        correo = datos_google.get('email')


        usuario = Usuarios.objects.filter(
            correo=correo
        ).first()


        if not usuario:

            return Response(
                {
                    'error':
                    'Usuario no registrado. Por favor cree una cuenta.'
                },
                status=status.HTTP_404_NOT_FOUND
                )
        if not usuario.estado:return Response(
                {
                    'error': 'El usuario se encuentra inactivo.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        return Response(
                {
                    'mensaje': 'Inicio de sesión exitoso.',
                    'token': crear_token_usuario(usuario),
                    'usuario': {
                        'id_usuario': usuario.id_usuario,
                        'nombres': usuario.nombres,
                        'apellidos': usuario.apellidos,
                        'correo': usuario.correo,
                        'id_rol': usuario.id_rol_id
                    }
                },
                status=status.HTTP_200_OK
            )


    except Exception as error:

        return Response(
            {
                'error':
                'Token de Google inválido.',
                'detalle':
                str(error)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
# ============================================================
# CAMBIAR CONTRASEÑA
# ============================================================

@api_view(['POST'])
def cambiar_contrasena(request):
    id_usuario = request.data.get('id_usuario')

    if not id_usuario:
        return Response(
            {
                'error': 'El ID del usuario es obligatorio.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    if str(request.user.id_usuario) != str(id_usuario):
        return Response(
            {'error': 'No puedes cambiar la contraseña de otro usuario.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        usuario = Usuarios.objects.get(
            id_usuario=id_usuario
        )

    except Usuarios.DoesNotExist:
        return Response(
            {
                'error': 'El usuario no existe.'
            },
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = CambiarContrasenaSerializer(
        data=request.data
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    contrasena_actual = serializer.validated_data[
        'contrasena_actual'
    ]

    nueva_contrasena = serializer.validated_data[
        'nueva_contrasena'
    ]

    # Verificar que el usuario tenga contraseña
    if not usuario.contrasena:
        return Response(
            {
                'error': 'Este usuario no tiene una contraseña registrada.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Verificar contraseña actual
    if not check_password(
        contrasena_actual,
        usuario.contrasena
    ):
        return Response(
            {
                'error': 'La contraseña actual es incorrecta.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Evitar que la nueva contraseña sea igual
    # a la contraseña actual
    if check_password(
        nueva_contrasena,
        usuario.contrasena
    ):
        return Response(
            {
                'error': 'La nueva contraseña debe ser diferente a la actual.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Guardar nueva contraseña encriptada
    usuario.contrasena = make_password(
        nueva_contrasena
    )

    usuario.save(
        update_fields=['contrasena']
    )

    return Response(
        {
            'mensaje': 'Contraseña actualizada correctamente.'
        },
        status=status.HTTP_200_OK
    )


# ============================================================
# RECUPERAR CONTRASEÑA
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def recuperar_password(request):
    correo = request.data.get('correo')

    if not correo:
        return Response(
            {
                'error': 'El correo es obligatorio.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        usuario = Usuarios.objects.get(
            correo=correo
        )

    except Usuarios.DoesNotExist:
        return Response(
            {
                'error': 'No existe un usuario con este correo.'
            },
            status=status.HTTP_404_NOT_FOUND
        )

    # Generar código de 6 dígitos
    codigo = str(
        random.randint(100000, 999999)
    )

    # Guardar código de recuperación
    RecuperacionPassword.objects.create(
        id_usuario=usuario,
        codigo=codigo,
        fecha_creacion=timezone.now(),
        fecha_expiracion=timezone.now() + timedelta(minutes=10),
        usado=False
    )

    # Configuración de Brevo
    configuration = sib_api_v3_sdk.Configuration()

    configuration.api_key['api-key'] = settings.BREVO_API_KEY

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    # Crear correo
    email = sib_api_v3_sdk.SendSmtpEmail(
        sender={
            "name": "GerIApp",
            "email": settings.EMAIL_FROM
        },
        to=[
            {
                "email": correo
            }
        ],
        subject="Recuperación de contraseña GerIApp",
        html_content=f"""
        <h2>Recuperación de contraseña</h2>
        <p>Tu código es:</p>
        <h1>{codigo}</h1>
        <p>Este código vence en 10 minutos.</p>
        """
    )

    # Enviar correo
    api_instance.send_transac_email(email)

    return Response(
        {
            'mensaje': 'Código enviado correctamente al correo.'
        },
        status=status.HTTP_200_OK
    )


# ============================================================
# VERIFICAR CÓDIGO DE RECUPERACIÓN
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def verificar_codigo(request):
    correo = request.data.get('correo')
    codigo = request.data.get('codigo')

    if not correo or not codigo:
        return Response(
            {
                'error': 'Correo y código son obligatorios.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        usuario = Usuarios.objects.get(
            correo=correo
        )

    except Usuarios.DoesNotExist:
        return Response(
            {
                'error': 'Usuario no encontrado.'
            },
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        recuperacion = RecuperacionPassword.objects.filter(
            id_usuario=usuario,
            codigo=codigo,
            usado=False
        ).latest('fecha_creacion')

    except RecuperacionPassword.DoesNotExist:
        return Response(
            {
                'error': 'Código inválido.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if timezone.now().replace(
        tzinfo=None
    ) > recuperacion.fecha_expiracion:
        return Response(
            {
                'error': 'El código ya expiró.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    return Response(
        {
            'mensaje': 'Código válido.'
        },
        status=status.HTTP_200_OK
    )


# ============================================================
# CAMBIAR CONTRASEÑA MEDIANTE RECUPERACIÓN
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def cambiar_password_recuperacion(request):
    correo = request.data.get('correo')
    codigo = request.data.get('codigo')
    nueva_contrasena = request.data.get('nueva_contrasena')

    if not correo or not codigo or not nueva_contrasena:
        return Response(
            {
                'error': 'Todos los campos son obligatorios.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        usuario = Usuarios.objects.get(
            correo=correo
        )

    except Usuarios.DoesNotExist:
        return Response(
            {
                'error': 'Usuario no encontrado.'
            },
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        recuperacion = RecuperacionPassword.objects.filter(
            id_usuario=usuario,
            codigo=codigo,
            usado=False
        ).latest('fecha_creacion')

    except RecuperacionPassword.DoesNotExist:
        return Response(
            {
                'error': 'Código inválido.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if timezone.now().replace(
        tzinfo=None
    ) > recuperacion.fecha_expiracion:
        return Response(
            {
                'error': 'El código expiró.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Guardar nueva contraseña
    usuario.contrasena = make_password(
        nueva_contrasena
    )

    usuario.save()

    # Marcar código como utilizado
    recuperacion.usado = True
    recuperacion.save()

    return Response(
        {
            'mensaje': 'Contraseña actualizada correctamente.'
        },
        status=status.HTTP_200_OK
    )


# ============================================================
# VIEWSETS
# ============================================================

class DocumentosHistoriaClinicaViewSet(viewsets.ModelViewSet):
    queryset = DocumentosHistoriaClinica.objects.all()
    serializer_class = DocumentosHistoriaClinicaSerializer
    permission_classes = [IsAuthenticated]

class ConfiguracionInstitucionView(APIView):
    def get(self, request):
        return Response({
            "nombre_institucion": settings.NOMBRE_INSTITUCION
        })


class PacientesViewSet(viewsets.ModelViewSet):
    queryset = Pacientes.objects.all()
    serializer_class = PacientesSerializer
    permission_classes = [IsAuthenticated]

    def _obtener_id_rol(self, usuario):
        rol = getattr(usuario, "id_rol", None)
        return (
            getattr(rol, "id_rol", None)
            if rol is not None
            else getattr(usuario, "id_rol_id", None)
        )

    def _validar_acceso_operativo(self, usuario):
        from rest_framework.exceptions import PermissionDenied

        if self._obtener_id_rol(usuario) not in (1, 2, 3):
            raise PermissionDenied(
                "No tienes permiso para gestionar pacientes."
            )

        if not getattr(usuario, "id_sede_id", None):
            raise PermissionDenied(
                "Tu usuario no tiene una sede asignada."
            )

    def get_queryset(self):
        usuario = self.request.user

        if not getattr(usuario, "is_authenticated", False):
            return Pacientes.objects.none()

        if self._obtener_id_rol(usuario) not in (1, 2, 3):
            return Pacientes.objects.none()

        sede_id = getattr(usuario, "id_sede_id", None)

        if not sede_id:
            return Pacientes.objects.none()

        habitaciones_sede = Habitaciones.objects.filter(
            id_sede_id=sede_id
        ).values_list("id_habitacion", flat=True)

        return Pacientes.objects.filter(
            habitacion__in=habitaciones_sede
        ).distinct()

    def _validar_sede_habitacion(self, serializer):
        from rest_framework.exceptions import ValidationError

        sede_id = self.request.user.id_sede_id

        habitacion_id = serializer.validated_data.get(
            "habitacion",
            getattr(serializer.instance, "habitacion", None)
        )

        habitacion = Habitaciones.objects.filter(
            id_habitacion=habitacion_id,
            id_sede_id=sede_id,
            estado=True
        ).select_related("id_sede").first()

        if not habitacion:
            raise ValidationError({
                "habitacion": (
                    "La habitación debe estar activa "
                    "y pertenecer a tu sede."
                )
            })

        # Forzar la sede correspondiente a la habitación autorizada
        serializer.validated_data["id_sede"] = habitacion.id_sede

        # Guardar el nombre de la sede
        serializer.validated_data["sede"] = habitacion.id_sede.nombre

    def perform_create(self, serializer):
        self._validar_acceso_operativo(self.request.user)
        self._validar_sede_habitacion(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._validar_acceso_operativo(self.request.user)
        self._validar_sede_habitacion(serializer)
        serializer.save()

    def create(self, request, *args, **kwargs):
        self._validar_acceso_operativo(request.user)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._validar_acceso_operativo(request.user)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._validar_acceso_operativo(request.user)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._validar_acceso_operativo(request.user)
        return super().destroy(request, *args, **kwargs)

class MedicamentosViewSet(viewsets.ModelViewSet):
    queryset = Medicamentos.objects.all()
    serializer_class = MedicamentosSerializer


class RolesViewSet(viewsets.ModelViewSet):
    queryset = Roles.objects.all()
    serializer_class = RolesSerializer
    permission_classes = [EsSuperadministradorOMetodoLectura]


class SeguimientoAdministracionMedicamentoViewSet(viewsets.ModelViewSet):
    queryset = SeguimientoAdministracionMedicamento.objects.all()
    serializer_class = SeguimientoAdministracionMedicamentoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filtra los registros de seguimiento según el rol del usuario.
        - Superadministrador: todos los registros.
        - Administrador: registros de su sede.
        - Encargado: registros de pacientes asignados a él.
        - Otros roles: únicamente sus propios registros.
        """
        usuario = self.request.user

        if not getattr(usuario, "is_authenticated", False):
            return SeguimientoAdministracionMedicamento.objects.none()

        rol_id = getattr(usuario, "id_rol_id", None)

        # Superadministrador
        if rol_id == 4:
            return SeguimientoAdministracionMedicamento.objects.all()

        # Administrador: solo registros de su sede
        if rol_id == 1:
            sede_id = getattr(usuario, "id_sede_id", None)
            if sede_id is None:
                return SeguimientoAdministracionMedicamento.objects.none()

            return SeguimientoAdministracionMedicamento.objects.filter(
                paciente__habitacion__id_sede_id=sede_id
            )

        # Encargado: registros de pacientes asignados a él
        if rol_id == 2:
            return SeguimientoAdministracionMedicamento.objects.filter(
                paciente__asignaciones__id_usuario=usuario
            ).distinct()

        # Otros roles: únicamente sus propios registros
        return SeguimientoAdministracionMedicamento.objects.filter(
            id_usuario=usuario
        )


class UsuariosViewSet(viewsets.ModelViewSet):
    queryset = Usuarios.objects.all()
    serializer_class = UsuariosSerializer

    parser_classes = [
        parsers.MultiPartParser,
        parsers.FormParser,
        parsers.JSONParser,
    ]

    # =====================================================
    # OBTENER ROL DEL USUARIO
    # =====================================================

    def _obtener_id_rol(self, usuario):
        """Obtiene el ID del rol del usuario autenticado."""
        rol = getattr(usuario, "id_rol", None)

        if rol is None:
            return getattr(usuario, "id_rol_id", None)

        return getattr(rol, "id_rol", None)

    # =====================================================
    # CONSULTAR USUARIOS SEGÚN ROL Y SEDE
    # =====================================================

    def get_queryset(self):
        """
        Superadministrador: todos los usuarios.
        Administrador: usuarios de su sede.
        Encargado: su perfil y todos los cuidadores.
        Otros roles: únicamente su propio perfil.

        El filtro también se aplica al consultar un usuario
        individual mediante /usuarios/<id>/.
        """
        usuario = self.request.user

        if not getattr(usuario, "is_authenticated", False):
            return Usuarios.objects.none()

        rol_id = self._obtener_id_rol(usuario)

        # Superadministrador.
        if rol_id == 4:
            return Usuarios.objects.all()

        # Administrador: solo usuarios de su sede.
        if rol_id == 1:
            sede_id = getattr(usuario, "id_sede_id", None)

            if sede_id is None:
                return Usuarios.objects.none()

            return Usuarios.objects.filter(
                id_sede_id=sede_id
            )

        # Encargado: puede consultar su perfil
        # y los cuidadores de su propia sede.
        if rol_id == 2:
            sede_id = getattr(usuario, "id_sede_id", None)

            if sede_id is None:
                return Usuarios.objects.none()

            return Usuarios.objects.filter(
                Q(id_usuario=usuario.id_usuario)
                | Q(id_rol_id=3, id_sede_id=sede_id)
            ).distinct()

        # Los demás roles solo consultan su propio perfil.
        return Usuarios.objects.filter(
            id_usuario=usuario.id_usuario
        )

    # =====================================================
    # REAR USUARIO
    # =====================================================

    # =====================================================
    # CREAR ENCARGADO O CUIDADOR POR ADMINISTRADOR DE SEDE
    # =====================================================

    @action(
        detail=False,
        methods=['post'],
        url_path='crear-usuario-sede',
        permission_classes=[IsAuthenticated],
        parser_classes=[
            parsers.MultiPartParser,
            parsers.FormParser,
            parsers.JSONParser,
        ]
    )
    @transaction.atomic
    def crear_usuario_sede(self, request):

        # 1. Validar que quien registra sea administrador
        rol_actual = self._obtener_id_rol(request.user)

        if rol_actual != 1:
            return Response(
                {
                    "error": "Solo el administrador de sede puede crear encargados y cuidadores."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Obtener automáticamente la sede del administrador
        sede_id = getattr(request.user, 'id_sede_id', None)

        if not sede_id:
            return Response(
                {
                    "error": "El administrador no tiene una sede asignada."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Validar datos obligatorios
        campos_obligatorios = [
            'id_rol',
            'tipo_documento',
            'numero_documento',
            'nombres',
            'apellidos',
            'correo',
        ]

        for campo in campos_obligatorios:
            valor = request.data.get(campo)

            if valor is None or not str(valor).strip():
                return Response(
                    {
                        "error": f"El campo {campo} es obligatorio."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 4. Validar rol solicitado
        try:
            rol_id = int(request.data.get('id_rol'))
        except (TypeError, ValueError):
            return Response(
                {"error": "El rol seleccionado no es válido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if rol_id not in (2, 3):
            return Response(
                {
                    "error": "Solo puedes crear usuarios con rol Encargado o Cuidador."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        rol = Roles.objects.filter(
            id_rol=rol_id,
            estado=True
        ).first()

        if not rol:
            return Response(
                {"error": "El rol seleccionado no existe o está inactivo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Obtener y limpiar información
        tipo_documento = str(
            request.data.get('tipo_documento')
        ).strip()

        numero_documento = str(
            request.data.get('numero_documento')
        ).strip()

        nombres = str(request.data.get('nombres')).strip()
        apellidos = str(request.data.get('apellidos')).strip()
        correo = str(request.data.get('correo')).strip()

        # 6. Verificar documentos duplicados
        if Usuarios.objects.filter(
            numero_documento=numero_documento
        ).exists():
            return Response(
                {"error": "Este número de documento ya está registrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 7. Verificar correos duplicados
        if Usuarios.objects.filter(
            correo__iexact=correo
        ).exists():
            return Response(
                {"error": "Este correo ya está registrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 8. Validar experiencia profesional
        experiencia = request.data.get('experiencia')

        if experiencia in ('', None):
            experiencia = None
        else:
            try:
                experiencia = int(experiencia)

                if experiencia < 0:
                    raise ValueError

            except (TypeError, ValueError):
                return Response(
                    {"error": "La experiencia debe ser un número válido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 9. Procesar fotografía
        imagen = request.FILES.get('foto')
        foto_url = None

        if imagen:
            resultado = subir_imagen(
                imagen,
                'geriapp/usuarios'
            )
            foto_url = resultado['secure_url']

        # 10. Crear usuario
        usuario = Usuarios.objects.create(
            id_rol=rol,
            id_sede_id=sede_id,
            tipo_documento=tipo_documento,
            numero_documento=numero_documento,
            nombres=nombres,
            apellidos=apellidos,
            correo=correo,
            telefono=request.data.get('telefono') or None,
            fecha_ingreso=timezone.now(),
            estado=True,
            contrasena=None,
            foto=foto_url
        )

        # 11. Crear perfil profesional para encargados y cuidadores
        perfil = None

        if rol_id in (2, 3):
            perfil = PerfilProfesional.objects.create(
                id_usuario=usuario,
                especialidad=request.data.get('especialidad') or None,
                licencia=request.data.get('licencia') or None,
                experiencia=experiencia,
                institucion=request.data.get('institucion') or None
            )

        # 12. Responder a Angular
        return Response(
            {
                "mensaje": "Usuario creado correctamente.",
                "usuario": UsuariosSerializer(usuario).data,
                "perfil_profesional": (
                    PerfilProfesionalSerializer(perfil).data
                    if perfil else None
                )
            },
            status=status.HTTP_201_CREATED
        )

    def create(self, request, *args, **kwargs):
        """El registro debe pasar por el endpoint específico."""
        return Response(
            {
                "error": (
                    "Utiliza el endpoint de registro de usuarios."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # =====================================================
    # ACTUALIZAR USUARIO
    # =====================================================

    def update(self, request, *args, **kwargs):
        """Valida los campos que puede modificar cada rol."""
        usuario_actual = request.user
        rol_actual = self._obtener_id_rol(usuario_actual)

        # Respeta las restricciones definidas en get_queryset().
        usuario_objetivo = self.get_object()
        rol_objetivo = self._obtener_id_rol(usuario_objetivo)

        campos_personales = {
            "nombres",
            "apellidos",
            "correo",
            "telefono",
            "tipo_documento",
            "numero_documento",
            "foto",
        }

        campos_recibidos = set(request.data.keys())

        # Superadministrador.
        if rol_actual == 4:

            # Puede actualizar sus propios datos personales,
            # pero no modificar los privilegios de su cuenta.
            if rol_objetivo == 4:
                if (
                    usuario_objetivo.id_usuario
                    != usuario_actual.id_usuario
                ):
                    return Response(
                        {
                            "error": (
                                "No puedes modificar otra cuenta "
                                "de superadministrador."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                campos_permitidos = campos_personales

            # Puede gestionar cuentas de administradores.
            elif rol_objetivo == 1:
                campos_permitidos = campos_personales | {
                    "estado",
                    "id_sede",
                }

            # Puede convertir otros usuarios en administradores.
            else:
                campos_permitidos = {
                    "id_rol",
                    "id_sede",
                }

                if "id_rol" not in campos_recibidos:
                    return Response(
                        {
                            "error": (
                                "Solo puedes modificar este usuario "
                                "para convertirlo en administrador."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                try:
                    nuevo_rol = int(request.data["id_rol"])
                except (TypeError, ValueError):
                    return Response(
                        {"error": "El rol indicado no es válido."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if nuevo_rol != 1:
                    return Response(
                        {
                            "error": (
                                "El superadministrador solo puede "
                                "asignar el rol Administrador."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

        # Administrador.
        elif rol_actual == 1:
            if (
                usuario_objetivo.id_usuario
                == usuario_actual.id_usuario
            ):
                campos_permitidos = campos_personales

            elif rol_objetivo in (2, 3):
                campos_permitidos = campos_personales | {
                    "estado",
                    "id_rol",
                }

                if "id_rol" in campos_recibidos:
                    try:
                        nuevo_rol = int(request.data["id_rol"])
                    except (TypeError, ValueError):
                        return Response(
                            {
                                "error": "El rol indicado no es válido."
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    if nuevo_rol not in (2, 3):
                        return Response(
                            {
                                "error": (
                                    "El Administrador solo puede "
                                    "asignar los roles operativos "
                                    "autorizados."
                                )
                            },
                            status=status.HTTP_403_FORBIDDEN,
                        )

            else:
                return Response(
                    {
                        "error": (
                            "No tienes permiso para modificar "
                            "este usuario."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Encargado y demás roles.
        else:
            # Poder consultar un cuidador no significa poder editarlo.
            if (
                usuario_objetivo.id_usuario
                != usuario_actual.id_usuario
            ):
                return Response(
                    {
                        "error": (
                            "No tienes permiso para modificar "
                            "este usuario."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            campos_permitidos = campos_personales

        # Bloquear campos que el rol no puede modificar.
        campos_no_permitidos = (
            campos_recibidos - campos_permitidos
        )

        if campos_no_permitidos:
            return Response(
                {
                    "error": (
                        "No tienes permiso para modificar "
                        "estos campos."
                    ),
                    "campos": sorted(campos_no_permitidos),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().update(request, *args, **kwargs)

    # =====================================================
    # ELIMINAR USUARIO
    # =====================================================

    def destroy(self, request, *args, **kwargs):
        """Permite al administrador eliminar usuarios operativos de su sede."""
        rol_actual = self._obtener_id_rol(request.user)

        # Solo el Administrador de sede puede eliminar usuarios.
        if rol_actual != 1:
            return Response(
                {
                    "error": (
                        "Solo el Administrador de sede puede "
                        "eliminar usuarios."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # get_object() respeta el filtro de sede de get_queryset().
        # Si el usuario objetivo es de otra sede, no se encontrará.
        usuario_objetivo = self.get_object()
        rol_objetivo = self._obtener_id_rol(usuario_objetivo)

        # El administrador no puede eliminarse a sí mismo,
        # eliminar otro administrador ni eliminar al superadministrador.
        if rol_objetivo not in (2, 3):
            return Response(
                {
                    "error": (
                        "Solo puedes eliminar encargados y "
                        "cuidadores autorizados de tu sede."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().destroy(request, *args, **kwargs)

    # =====================================================
    # ELIMINAR FOTO DE PERFIL
    # =====================================================

    @action(
        detail=True,
        methods=["delete"],
        url_path="foto",
    )
    def eliminar_foto(self, request, pk=None):
        """Elimina la foto de Cloudinary y limpia el campo foto."""
        usuario = self.get_object()
        url_foto = usuario.foto

        usuario_actual = request.user
        rol_actual = self._obtener_id_rol(usuario_actual)
        rol_objetivo = self._obtener_id_rol(usuario)

        es_su_propia_cuenta = (
            usuario.id_usuario == usuario_actual.id_usuario
        )

        if rol_actual == 4:
            permitido = es_su_propia_cuenta or rol_objetivo == 1

        elif rol_actual == 1:
            permitido = (
                es_su_propia_cuenta
                or rol_objetivo in (2, 3)
            )

        else:
            permitido = es_su_propia_cuenta

        if not permitido:
            return Response(
                {
                    "error": (
                        "No tienes permiso para eliminar "
                        "la fotografía de este usuario."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not url_foto:
            return Response(
                {"mensaje": "El usuario no tiene una foto."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            ruta = urlparse(str(url_foto)).path
            marcador = "/upload/"

            if marcador not in ruta:
                return Response(
                    {
                        "error": (
                            "No se pudo identificar la imagen "
                            "en Cloudinary."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            public_id = ruta.split(marcador, 1)[1]
            public_id = re.sub(r"^v\d+/", "", public_id)
            public_id = re.sub(r"\.[^/.]+$", "", public_id)

            resultado = eliminar_imagen(public_id)

            # Si Cloudinary devuelve un resultado explícito de fallo,
            # no borrar la URL guardada en la base de datos.
            if isinstance(resultado, dict):
                if resultado.get("result") not in (
                    "ok",
                    "not found",
                ):
                    return Response(
                        {
                            "error": (
                                "No se pudo eliminar la imagen "
                                "en Cloudinary."
                            )
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            usuario.foto = None
            usuario.save(update_fields=["foto"])

            return Response(
                {"mensaje": "Foto eliminada correctamente."},
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                "Error eliminando la foto del usuario %s",
                usuario.id_usuario,
            )

            return Response(
                {"error": "No se pudo eliminar la foto."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )







class DocumentosViewSet(viewsets.ModelViewSet):
    queryset = Documentos.objects.all()
    serializer_class = DocumentosSerializer

    # Permitir recibir archivos mediante FormData
    parser_classes = [
        parsers.MultiPartParser,
        parsers.FormParser,
        parsers.JSONParser,
    ]

class HistoriaClinicasViewSet(viewsets.ModelViewSet):
    queryset = HistoriaClinicas.objects.all()
    serializer_class = HistoriaClinicasSerializer


class EnfermedadesViewSet(viewsets.ModelViewSet):
    queryset = Enfermedades.objects.all()
    serializer_class = EnfermedadesSerializer


class DiagnosticosViewSet(viewsets.ModelViewSet):
    queryset = Diagnosticos.objects.all()
    serializer_class = DiagnosticosSerializer


class TratamientoViewSet(viewsets.ModelViewSet):
    queryset = Tratamientos.objects.all()
    serializer_class = TratamientoSerializer


class TratamientoMedicamentoViewSet(viewsets.ModelViewSet):
    queryset = TratamientoMedicamento.objects.all()
    serializer_class = TratamientoMedicamentoSerializer



# ============================================================
# VIEWSET DE INVENTARIO
# ============================================================

class InventarioViewSet(viewsets.ModelViewSet):

    # ========================================================
    # QUERYSET BASE
    # ========================================================

    queryset = Inventario.objects.all()

    serializer_class = InventarioSerializer

    # ========================================================
    # OBTENER INVENTARIO
    # ========================================================

    def get_queryset(self):

        queryset = Inventario.objects.all()

        # ====================================================
        # OBTENER ID DEL PACIENTE DESDE LA URL
        # ====================================================

        id_paciente = self.request.query_params.get('id_paciente')

        # ====================================================
        # FILTRAR INVENTARIO DEL PACIENTE
        # ====================================================

        if id_paciente:
            queryset = queryset.filter(
                id_paciente=id_paciente
            )

        return queryset

class EntregaMedicaViewSet(viewsets.ModelViewSet):
    queryset = EntregaMedica.objects.all()
    serializer_class = EntregaMedicaSerializer


class DetalleEntregaMedicamentoViewSet(viewsets.ModelViewSet):
    queryset = DetalleEntregaMedicamento.objects.all()
    serializer_class = DetalleEntregaMedicamentoSerializer


class MovimientoMedicamentoViewSet(viewsets.ModelViewSet):
    queryset = MovimientoMedicamento.objects.all()
    serializer_class = MovimientoMedicamentoSerializer


class AplicacionMedicamentoViewSet(viewsets.ModelViewSet):
    queryset = AplicacionMedicamento.objects.all()
    serializer_class = AplicacionMedicamentoSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # =====================================================
        # 1. IDENTIFICAR SI VIENE DE UN SEGUIMIENTO
        # =====================================================

        id_seguimiento = request.data.get('id_seguimiento')

        seguimiento = None
        usuario_cuidador = None
        formulacion = None

        if id_seguimiento not in (None, ''):

            try:
                id_seguimiento = int(id_seguimiento)
            except (TypeError, ValueError):
                return Response(
                    {'error': 'El id_seguimiento no es válido.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            usuario_cuidador = getattr(
                request.user,
                'usuario',
                request.user
            )

            if (
                not getattr(request.user, 'is_authenticated', False)
                or not getattr(usuario_cuidador, 'estado', False)
                or getattr(usuario_cuidador, 'id_rol_id', None) != 3
                or getattr(usuario_cuidador, 'id_usuario', None) is None
            ):
                return Response(
                    {'error': 'Solo un cuidador activo puede administrar medicamentos.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            try:
                seguimiento = (
                    SeguimientoAdministracionMedicamento.objects
                    .select_for_update()
                    .select_related('id_formulacion')
                    .get(pk=id_seguimiento)
                )

            except SeguimientoAdministracionMedicamento.DoesNotExist:
                return Response(
                    {'error': 'El seguimiento no existe.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Solo se puede administrar una dosis pendiente.
            if seguimiento.estado != (
                SeguimientoAdministracionMedicamento.Estado.PENDIENTE
            ):
                return Response(
                    {
                        'error':
                            'Este seguimiento ya fue procesado. '
                            'No se puede administrar nuevamente.'
                    },
                    status=status.HTTP_409_CONFLICT
                )

            formulacion = seguimiento.id_formulacion

            id_paciente = formulacion.id_paciente_id

            if id_paciente is None:
                return Response(
                    {'error': 'La formulación no tiene paciente asociado.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verificar que el cuidador siga asignado al paciente.
            asignacion_activa = (
                AsignacionPacienteCuidador.objects.filter(
                    id_usuario_id=usuario_cuidador.id_usuario,
                    id_paciente_id=id_paciente,
                    estado__iexact='Activo'
                ).exists()
            )

            if not asignacion_activa:
                return Response(
                    {'error': 'No tienes asignado actualmente este paciente.'},
                    status=status.HTTP_403_FORBIDDEN
                )


        # Obtener el ID del inventario enviado desde Android.
        inventario_id = (
            request.data.get('id_inventario')
            or serializer.validated_data.get('id_inventario')
        )

        # Convertir a ID si se recibió una Foreign Key.
        if hasattr(inventario_id, 'id_inventario'):
            inventario_id = inventario_id.id_inventario

        if not inventario_id:
            return Response(
                {"error": "Debe proporcionar el id_inventario."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Bloquear el inventario mientras se procesa
            # la administración del medicamento.
            item_inventario = (
                Inventario.objects
                .select_for_update()
                .get(pk=inventario_id)
            )
            if seguimiento is not None :
                if (
                    item_inventario.id_paciente_id != formulacion.id_paciente_id
                    or item_inventario.id_medicamentos_id !=formulacion.id_medicamentos_id
                    or item_inventario.id_medicamentos_id is None
                ):
                    return Response(
                        {
                            'error':
                            'El inventario no corresponde al paciente'
                            'y medicamento de la formulacion'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Cantidad que se va a administrar.
            cantidad_aplicada = serializer.validated_data.get(
                'cantidad_aplicada',
                1
            )

            # Validar la cantidad.
            if cantidad_aplicada <= 0:
                return Response(
                    {
                        "error":
                            "La cantidad aplicada debe ser mayor que cero."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validar las existencias reales.
            if item_inventario.cantidad_actual < cantidad_aplicada:
                return Response(
                    {
                        "error": (
                            "Stock insuficiente en inventario. "
                            f"Disponible: {item_inventario.cantidad_actual}. "
                            f"Solicitado: {cantidad_aplicada}."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 1. Descontar el inventario.
            item_inventario.cantidad_actual -= cantidad_aplicada

            item_inventario.save(
                update_fields=['cantidad_actual']
            )

            # 2. Sincronizar el elemento asociado al paciente.
            if item_inventario.id_elemento_id is not None:
                elemento = (
                    ElementosPaciente.objects
                    .select_for_update()
                    .get(pk=item_inventario.id_elemento_id)
                )

                elemento.cantidad = item_inventario.cantidad_actual

                elemento.save(
                    update_fields=['cantidad']
                )

            # 3. Registrar la administración del medicamento.
            self.perform_create(serializer)

            # Recuperar la aplicación recién creada.
            aplicacion = serializer.instance

            # Asociar el cuidador autenticado cuando
            # la administración proviene de un seguimiento.
            if usuario_cuidador is not None:
                aplicacion.id_usuario = usuario_cuidador

            # Garantizar que el medicamento registrado
            # corresponda al inventario utilizado.
            aplicacion.id_medicamento_medicamento = (
                item_inventario.id_medicamentos_id
            )

            campos_actualizados = [
                'id_medicamento_medicamento'
            ]

            if usuario_cuidador is not None:
                campos_actualizados.append('id_usuario')

            aplicacion.save(
                update_fields=campos_actualizados
            )

            # Actualizar el seguimiento únicamente
            # cuando la aplicación está asociada a uno.
            if seguimiento is not None:

                seguimiento.estado = (
                    SeguimientoAdministracionMedicamento.Estado.ADMINISTRADO
                )

                seguimiento.motivo_no_administracion = None

                seguimiento.fecha_hora_registro = timezone.now()

                seguimiento.id_usuario = usuario_cuidador

                seguimiento.id_aplicacion = aplicacion

                seguimiento.save(
                    update_fields=[
                        'estado',
                        'motivo_no_administracion',
                        'fecha_hora_registro',
                        'id_usuario',
                        'id_aplicacion'
                    ]
                )
            headers = self.get_success_headers(serializer.data)

            # Devolver también las existencias confirmadas por Django.
            respuesta = serializer.data
            respuesta['cantidad_actual'] = (
                item_inventario.cantidad_actual
            )
            respuesta['cantidad_minima'] = (
                item_inventario.cantidad_minima
            )

            return Response(
                respuesta,
                status=status.HTTP_201_CREATED,
                headers=headers
            )

        except Inventario.DoesNotExist:
            return Response(
                {
                    "error":
                        "El registro de inventario especificado no existe."
                },
                status=status.HTTP_404_NOT_FOUND
            )

class TipoInsumoViewSet(viewsets.ModelViewSet):
    queryset = TipoInsumo.objects.all()
    serializer_class = TipoInsumoSerializer


class InsumosViewSet(viewsets.ModelViewSet):
    queryset = Insumos.objects.all()
    serializer_class = InsumosSerializer


class DetalleEntregaInsumoViewSet(viewsets.ModelViewSet):
    queryset = DetalleEntregaInsumos.objects.all()
    serializer_class = DetalleEntregaInsumoSerializer


class EntregaInsumoViewSet(viewsets.ModelViewSet):
    queryset = EntregaInsumo.objects.all()
    serializer_class = EntregaInsumoSerializer


class MovimientoInsumoViewSet(viewsets.ModelViewSet):
    queryset = MovimientoInsumo.objects.all()
    serializer_class = MovimientoInsumoSerializer


class BitacoraViewSet(viewsets.ModelViewSet):
    queryset = Bitacora.objects.all()
    serializer_class = BitacoraSerializer


class ActividadesViewSet(viewsets.ModelViewSet):
    queryset = Actividades.objects.all()
    serializer_class = ActividadesSerializer


class SignosVitalesViewSet(viewsets.ModelViewSet):
    queryset = SignosVitales.objects.all()
    serializer_class = SignosVitalesSerializer


class TipoEventoViewSet(viewsets.ModelViewSet):
    queryset = TipoEvento.objects.all()
    serializer_class = TipoEventoSerializer


class TipoEmergenciaViewSet(viewsets.ModelViewSet):
    queryset = TipoEmergencia.objects.all()
    serializer_class = TipoEmergenciaSerializer


class EventosAdversosViewSet(viewsets.ModelViewSet):
    queryset = EventosAdversos.objects.all()
    serializer_class = EventosAdversosSerializer


class ImagenesEventoAdversoViewSet(viewsets.ModelViewSet):
    queryset = ImagenesEventoAdverso.objects.all()
    serializer_class = ImagenesEventoAdversoSerializer


class AsignacionPacienteCuidadorViewSet(viewsets.ModelViewSet):
    queryset = AsignacionPacienteCuidador.objects.all()
    serializer_class = AsignacionPacienteCuidadorSerializer



class NotificacionesViewSet(viewsets.ModelViewSet):

    queryset = Notificaciones.objects.all()
    serializer_class = NotificacionesSerializer

    def create(self, request, *args, **kwargs):

        # ============================================================
        # CREAR NOTIFICACIÓN
        # ============================================================

        response = super().create(
            request,
            *args,
            **kwargs
        )

        id_notificacion = response.data.get(
            "id_notificacion"
        )

        if not id_notificacion:
            return response

        # ============================================================
        # BUSCAR NOTIFICACIÓN CREADA
        # ============================================================

        try:

            notificacion = Notificaciones.objects.get(
                id_notificacion=id_notificacion
            )

        except Notificaciones.DoesNotExist:

            return response

        # ============================================================
        # OBTENER USUARIO DESTINATARIO
        # ============================================================

        usuario = notificacion.id_usuario

        if not usuario:
            print(
                "FCM: la notificación no tiene usuario destinatario."
            )
            return response

        # ============================================================
        # CREAR DESTINATARIO
        # ============================================================

        destinatario, creado = (
            NotificacionDestinatario.objects.get_or_create(

                id_notificacion=notificacion,

                id_usuario=usuario,

                defaults={
                    "leida": False,
                    "fecha_lectura": None
                }
            )
        )

        print(
            f"NOTIFICACION: {notificacion.id_notificacion} "
            f"creada para usuario {usuario.id_usuario}"
        )

        # ============================================================
        # BUSCAR TOKENS FCM DEL USUARIO
        # ============================================================

        tokens = FcmTokens.objects.filter(
            id_usuario=usuario,
            activo=True
        )

        print(
            f"FCM - Usuario: {usuario.id_usuario} - "
            f"Cantidad de tokens: {tokens.count()}"
        )

        if not tokens.exists():

            print(
                f"FCM - El usuario {usuario.id_usuario} "
                f"no tiene tokens FCM activos."
            )

            return response

        # ============================================================
        # INICIALIZAR FIREBASE
        # ============================================================

        try:

            app = inicializar_firebase()

            if app is None:

                print(
                    "FCM - Firebase no pudo inicializarse."
                )

                return response

        except Exception as error_firebase:

            print(
                "FCM - Error inicializando Firebase: "
                f"{error_firebase}"
            )

            return response

        # ============================================================
        # ENVIAR PUSH A CADA TOKEN
        # ============================================================

        for fcm_token in tokens:

            mensaje = messaging.Message(

                notification=messaging.Notification(

                    title=notificacion.titulo,

                    body=notificacion.mensaje
                ),

                data={

                    "id_notificacion": str(
                        notificacion.id_notificacion
                    ),

                    "tipo": str(
                        notificacion.tipo or ""
                    )
                },

                android=messaging.AndroidConfig(

                    priority="high",

                    notification=messaging.AndroidNotification(

                        channel_id="geriapp_notificaciones"
                    )
                ),

                token=fcm_token.token
            )

            try:

                respuesta = messaging.send(
                    mensaje
                )

                print(
                    "FCM enviado correctamente. "
                    f"Usuario: {usuario.id_usuario}, "
                    f"Token: {fcm_token.id_fcm_token}, "
                    f"Respuesta: {respuesta}"
                )

            except Exception as error_token:

                print(
                    "FCM - Error enviando al token "
                    f"{fcm_token.id_fcm_token}: "
                    f"{error_token}"
                )

        return response

class GrupoMedicacionViewSet(viewsets.ModelViewSet):
    queryset = GrupoMedicacion.objects.all()
    serializer_class = GrupoMedicacionSerializer

class FormulacionMedicamentosViewSet(viewsets.ModelViewSet):
    queryset = FormulacionMedicamentos.objects.all()
    serializer_class = FormulacionMedicamentosSerializer

class SeguimientoAdministracionMedicamentoViewSet(
    viewsets.GenericViewSet
):
    queryset = SeguimientoAdministracionMedicamento.objects.all()
    serializer_class = SeguimientoAdministracionMedicamentoSerializer
    permission_classes = [IsAuthenticated]

    def _obtener_cuidador(self, request):

        usuario = getattr(
            request.user,
            'usuario',
            request.user
        )

        if (
            not getattr(usuario, 'estado', False)
            or getattr(usuario, 'id_rol_id', None) != 3
            or getattr(usuario, 'id_usuario', None) is None
        ):
            return None

        return usuario

    # =====================================================
    # VERIFICAR ASIGNACIÓN ACTIVA
    # =====================================================

    def _tiene_asignacion_activa(self, usuario, id_paciente):

        return AsignacionPacienteCuidador.objects.filter(
            id_usuario_id=usuario.id_usuario,
            id_paciente_id=id_paciente,
            estado__iexact='Activo'
        ).exists()

    # =====================================================
    # CONSULTAR SEGUIMIENTOS DE UN PACIENTE
    # GET ?id_paciente=1
    # =====================================================

    def list(self, request, *args, **kwargs):

        usuario = self._obtener_cuidador(request)

        if usuario is None:
            return Response(
                {'error': 'No tienes permisos para consultar seguimientos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            id_paciente = int(
                request.query_params.get('id_paciente')
            )
        except (TypeError, ValueError):
            return Response(
                {'error': 'Debes proporcionar un id_paciente válido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not self._tiene_asignacion_activa(
            usuario,
            id_paciente
        ):
            return Response(
                {'error': 'No tienes asignado este paciente.'},
                status=status.HTTP_403_FORBIDDEN
            )

        seguimientos = (
            self.get_queryset()
            .filter(
                id_formulacion__id_paciente_id=id_paciente
            )
            .order_by(
                'fecha_hora_programada',
                'id_seguimiento'
            )
        )

        serializer = self.get_serializer(
            seguimientos,
            many=True
        )

        return Response(serializer.data)

    # =====================================================
    # CREAR SEGUIMIENTO PENDIENTE
    # POST
    # =====================================================

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        usuario = self._obtener_cuidador(request)

        if usuario is None:
            return Response(
                {'error': 'Solo un cuidador activo puede crear seguimientos.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        formulacion = serializer.validated_data.get(
            'id_formulacion'
        )

        fecha_programada = serializer.validated_data.get(
            'fecha_hora_programada'
        )

        try:
            # Bloquear la formulación para evitar
            # duplicados en solicitudes simultáneas.
            formulacion_bloqueada = (
                FormulacionMedicamentos.objects
                .select_for_update()
                .get(pk=formulacion.pk)
            )

        except FormulacionMedicamentos.DoesNotExist:
            return Response(
                {'error': 'La formulación no existe.'},
                status=status.HTTP_404_NOT_FOUND
            )

        id_paciente = formulacion_bloqueada.id_paciente_id

        if id_paciente is None:
            return Response(
                {'error': 'La formulación no tiene paciente asociado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not self._tiene_asignacion_activa(
            usuario,
            id_paciente
        ):
            return Response(
                {'error': 'No tienes asignado este paciente.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Comprobar si ya existe el seguimiento.
        existente = SeguimientoAdministracionMedicamento.objects.filter(
            id_formulacion_id=formulacion_bloqueada.id_formulacion,
            fecha_hora_programada=fecha_programada
        ).first()

        if existente:

            return Response(
                self.get_serializer(existente).data,
                status=status.HTTP_200_OK
            )

        # Crear el seguimiento pendiente.
        seguimiento = serializer.save(

            id_formulacion=formulacion_bloqueada,

            estado=SeguimientoAdministracionMedicamento.Estado.PENDIENTE,

            motivo_no_administracion=None,

            fecha_hora_registro=None,

            id_usuario=usuario,

            id_aplicacion=None
        )

        return Response(
            self.get_serializer(seguimiento).data,
            status=status.HTTP_201_CREATED
        )

    # =====================================================
    # REGISTRAR DOSIS NO ADMINISTRADA
    # POST /{id}/no-administrado/
    # =====================================================

    @action(
        detail=True,
        methods=['post'],
        url_path='no-administrado'
    )
    @transaction.atomic
    def no_administrado(self, request, pk=None):

        usuario = self._obtener_cuidador(request)

        if usuario is None:
            return Response(
                {'error': 'No tienes permisos para realizar esta operación.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            seguimiento = (
                SeguimientoAdministracionMedicamento.objects
                .select_for_update()
                .select_related('id_formulacion')
                .get(pk=pk)
            )

        except SeguimientoAdministracionMedicamento.DoesNotExist:
            return Response(
                {'error': 'El seguimiento no existe.'},
                status=status.HTTP_404_NOT_FOUND
            )

        id_paciente = seguimiento.id_formulacion.id_paciente_id

        if id_paciente is None:
            return Response(
                {'error': 'La formulación no tiene paciente asociado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not self._tiene_asignacion_activa(
            usuario,
            id_paciente
        ):
            return Response(
                {'error': 'No tienes asignado este paciente.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Solo se pueden modificar seguimientos pendientes.
        if seguimiento.estado != (
            SeguimientoAdministracionMedicamento.Estado.PENDIENTE
        ):
            return Response(
                {
                    'error':
                        'Solo se pueden registrar como no administrados '
                        'los seguimientos pendientes.'
                },
                status=status.HTTP_409_CONFLICT
            )

        motivo = request.data.get(
            'motivo_no_administracion'
        )

        if not isinstance(motivo, str) or not motivo.strip():
            return Response(
                {'error': 'Debes proporcionar el motivo de no administración.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Actualizar el seguimiento.
        seguimiento.estado = (
            SeguimientoAdministracionMedicamento.Estado.NO_ADMINISTRADO
        )

        seguimiento.motivo_no_administracion = motivo.strip()

        seguimiento.fecha_hora_registro = timezone.now()

        seguimiento.id_usuario = usuario

        seguimiento.id_aplicacion = None

        seguimiento.save(
            update_fields=[
                'estado',
                'motivo_no_administracion',
                'fecha_hora_registro',
                'id_usuario',
                'id_aplicacion'
            ]
        )

        return Response(
            self.get_serializer(seguimiento).data,
            status=status.HTTP_200_OK
        )
class FcmTokensViewSet(viewsets.ModelViewSet):
    queryset = FcmTokens.objects.all()
    serializer_class = FcmTokensSerializer

    def create(self, request, *args, **kwargs):
        id_usuario = request.data.get("id_usuario")
        token = request.data.get("token")

        if not id_usuario or not token:
            return Response(
                {"error": "id_usuario y token son obligatorios"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            id_usuario = int(id_usuario)
        except (TypeError, ValueError):
            return Response(
                {"error": "id_usuario debe ser un número válido"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if id_usuario <= 0 or not isinstance(token, str) or not token.strip():
            return Response(
                {"error": "id_usuario o token no son válidos"},
                status=status.HTTP_400_BAD_REQUEST
            )

        token = token.strip()

        # Buscar si el token ya existe
        fcm_token = FcmTokens.objects.filter(token=token).first()

        if fcm_token:
            # Actualizar el usuario y la fecha sin reactivar
            # un token que el usuario haya desactivado
            fcm_token.id_usuario_id = id_usuario
            fcm_token.fecha_actualizacion = timezone.now()
            fcm_token.save(
                update_fields=["id_usuario", "fecha_actualizacion"]
            )
            creado = False
        else:
            # Si el usuario ya tiene tokens registrados y todos estan
            # desactivados, conservar esa preferencia para el nuevo token
            tokens_usuario = FcmTokens.objects.filter(
                id_usuario_id=id_usuario
            )

            tiene_tokens = tokens_usuario.exists()
            push_desactivadas = (
                tiene_tokens and not tokens_usuario.filter(activo=True).exists()
            )

            fcm_token = FcmTokens.objects.create(
                id_usuario_id=id_usuario,
                token=token,
                activo=not push_desactivadas,
                fecha_actualizacion=timezone.now()
            )
            creado = True

        serializer = self.get_serializer(fcm_token)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if creado
            else status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="preferencia")
    def configurar_preferencia(self, request, *args, **kwargs):
        id_usuario = request.data.get("id_usuario")
        activadas = request.data.get("activadas")

        if id_usuario is None or activadas is None:
            return Response(
                {"error": "id_usuario y activadas son obligatorios"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            id_usuario = int(id_usuario)
        except (TypeError, ValueError):
            return Response(
                {"error": "id_usuario debe ser un número válido"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar un booleano real evitar aceptar cadenas como "false".
        if id_usuario <= 0 or not isinstance(activadas, bool):
            return Response(
                {"error": "id_usuario o activadas no son válidos"},
                status=status.HTTP_400_BAD_REQUEST
            )

        tokens = FcmTokens.objects.filter(id_usuario_id=id_usuario)

        if not tokens.exists():
            return Response(
                {
                    "error": "El usuario no tiene tokens FCM registrados",
                    "id_usuario": id_usuario,
                    "push_activadas": activadas
                },
                status=status.HTTP_404_NOT_FOUND
            )

        tokens.update(
            activo=activadas,
            fecha_actualizacion=timezone.now()
        )

        return Response(
            {
                "id_usuario": id_usuario,
                "push_activadas": activadas,
                "mensaje": (
                    "Notificaciones push activadas"
                    if activadas
                    else "Notificaciones push desactivadas"
                )
            },
            status=status.HTTP_200_OK
        )


class CamasViewSet(viewsets.ModelViewSet):
    queryset = Camas.objects.all()
    serializer_class = CamasSerializer

class HabitacionesViewSet(viewsets.ModelViewSet):

    queryset = Habitaciones.objects.all()
    serializer_class = HabitacionesSerializer

    # --------------------------------------------------------
    # ELIMINAR SOLO SI NO EXISTEN RELACIONES
    # --------------------------------------------------------

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):

        from django.db.models.deletion import ProtectedError, RestrictedError
        from django.db import IntegrityError

        habitacion = self.get_object()
        id_habitacion = habitacion.id_habitacion

        # Comprobar todas las relaciones conocidas

        tiene_pacientes = Pacientes.objects.filter(
            habitacion=id_habitacion
        ).exists()

        tiene_camas = Camas.objects.filter(
            id_habitacion_id=id_habitacion
        ).exists()

        tiene_asignaciones = AsignacionHabitacion.objects.filter(
            id_habitacion_id=id_habitacion
        ).exists()

        tiene_camaras = Camaras.objects.filter(
            id_habitacion_id=id_habitacion
        ).exists()

        tiene_eventos = EventosIa.objects.filter(
            id_habitacion_id=id_habitacion
        ).exists()

        if any([
            tiene_pacientes,
            tiene_camas,
            tiene_asignaciones,
            tiene_camaras,
            tiene_eventos
        ]):

            return Response(
                {
                    "error": (
                        "No se puede eliminar esta habitación "
                        "porque tiene información relacionada. "
                        "Puedes desactivarla si está desocupada."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Eliminar solamente la habitación.
        # Nunca borrar los registros relacionados.

        try:
            with transaction.atomic():
                habitacion.delete()

        except (IntegrityError, ProtectedError, RestrictedError):
            return Response(
                {
                    "error": (
                        "No se puede eliminar la habitación "
                        "porque existen relaciones adicionales "
                        "en la base de datos."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        return Response(
            {
                "mensaje": "Habitación eliminada correctamente."
            },
            status=status.HTTP_200_OK
        )

    # --------------------------------------------------------
    # ACTIVAR / DESACTIVAR
    # --------------------------------------------------------

    def perform_update(self, serializer):

        from rest_framework.exceptions import ValidationError

        with transaction.atomic():

            habitacion = self.get_object()

            nuevo_estado = serializer.validated_data.get(
                "estado",
                habitacion.estado
            )

            # Si se va a desactivar la habitación
            if habitacion.estado and nuevo_estado is False:

                # Comprobar pacientes asignados
                pacientes_asignados = Pacientes.objects.filter(
                    habitacion=habitacion.id_habitacion
                ).exists()

                # Comprobar asignaciones vigentes
                asignaciones_activas = AsignacionHabitacion.objects.filter(
                    id_habitacion_id=habitacion.id_habitacion,
                    estado=True
                ).exists()

                if pacientes_asignados or asignaciones_activas:

                    raise ValidationError({
                        "estado": (
                            "No se puede desactivar esta habitación "
                            "porque tiene pacientes asignados. "
                            "Primero debes trasladarlos."
                        )
                    })

            serializer.save()

            # Las camas conservan su estado independiente.

class NotificacionDestinatarioViewSet(
    viewsets.ModelViewSet
):
    queryset = NotificacionDestinatario.objects.all()
    serializer_class = NotificacionDestinatarioSerializer

    # ============================================================
    # LISTAR DESTINATARIOS
    # ============================================================

    def list(self, request, *args, **kwargs):

        # --------------------------------------------------------
        # Reparar notificaciones antiguas que no tengan
        # destinatario para el usuario indicado en id_usuario
        # --------------------------------------------------------

        notificaciones = Notificaciones.objects.filter(
            id_usuario__isnull=False
        )

        for notificacion in notificaciones:

            NotificacionDestinatario.objects.get_or_create(
                id_notificacion=notificacion,
                id_usuario=notificacion.id_usuario,
                defaults={
                    "leida": False,
                    "fecha_lectura": None
                }
            )

        return super().list(
            request,
            *args,
            **kwargs
        )

    # ============================================================
    # MARCAR CUALQUIER NOTIFICACIÓN COMO LEÍDA
    # ============================================================

    @action(
        detail=False,
        methods=["post"],
        url_path="marcar-leida"
    )
    def marcar_leida(
        self,
        request,
        *args,
        **kwargs
    ):

        id_notificacion = request.data.get(
            "id_notificacion"
        )

        id_usuario = request.data.get(
            "id_usuario"
        )

        # --------------------------------------------------------
        # VALIDAR DATOS
        # --------------------------------------------------------

        if not id_notificacion:
            return Response(
                {
                    "error": "Se requiere id_notificacion."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not id_usuario:
            return Response(
                {
                    "error": "Se requiere id_usuario."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            id_notificacion = int(
                id_notificacion
            )

            id_usuario = int(
                id_usuario
            )

        except (TypeError, ValueError):

            return Response(
                {
                    "error": "Los IDs deben ser números."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------------
        # BUSCAR NOTIFICACIÓN
        # --------------------------------------------------------

        try:

            notificacion = Notificaciones.objects.get(
                id_notificacion=id_notificacion
            )

        except Notificaciones.DoesNotExist:

            return Response(
                {
                    "error": "La notificación no existe."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # --------------------------------------------------------
        # BUSCAR O CREAR DESTINATARIO
        # --------------------------------------------------------

        destinatario, creado = (
            NotificacionDestinatario.objects.get_or_create(

                id_notificacion=notificacion,

                id_usuario_id=id_usuario,

                defaults={
                    "leida": False,
                    "fecha_lectura": None
                }
            )
        )

        # --------------------------------------------------------
        # MARCAR COMO LEÍDA
        # --------------------------------------------------------

        destinatario.leida = True
        destinatario.fecha_lectura = timezone.now()

        destinatario.save(
            update_fields=[
                "leida",
                "fecha_lectura"
            ]
        )

        # --------------------------------------------------------
        # RESPUESTA
        # --------------------------------------------------------

        return Response(
            {
                "mensaje": "Notificación marcada como leída.",
                "id_notificacion": notificacion.id_notificacion,
                "id_notificacion_destinatario":
                    destinatario.id_notificacion_destinatario,
                "id_usuario": id_usuario,
                "leida": True,
                "creado": creado
            },
            status=status.HTTP_200_OK
        )

    # ============================================================
    # CREAR DESTINATARIO
    # ============================================================

    def create(
        self,
        request,
        *args,
        **kwargs
    ):

        response = super().create(
            request,
            *args,
            **kwargs
        )

        id_destinatario = response.data.get(
            "id_notificacion_destinatario"
        )

        if not id_destinatario:
            return response

        try:

            destinatario = (
                NotificacionDestinatario.objects.get(
                    id_notificacion_destinatario=
                        id_destinatario
                )
            )

        except NotificacionDestinatario.DoesNotExist:

            return response

        notificacion = (
            destinatario.id_notificacion
        )

        usuario = (
            destinatario.id_usuario
        )

        # ========================================================
        # ENVÍO DE CORREO
        # ========================================================

        if (
            notificacion
            and notificacion.enviar_correo
            and usuario
            and usuario.correo
        ):

            try:

                configuration = (
                    sib_api_v3_sdk.Configuration()
                )

                configuration.api_key[
                    "api-key"
                ] = settings.BREVO_API_KEY

                api_instance = (
                    sib_api_v3_sdk.TransactionalEmailsApi(
                        sib_api_v3_sdk.ApiClient(
                            configuration
                        )
                    )
                )

                email = (
                    sib_api_v3_sdk.SendSmtpEmail(
                        sender={
                            "name": "GerIApp",
                            "email": settings.EMAIL_FROM
                        },
                        to=[
                            {
                                "email":
                                    usuario.correo
                            }
                        ],
                        subject=
                            notificacion.titulo,
                        html_content=f"""
                            <h2>
                                {notificacion.titulo}
                            </h2>

                            <p>
                                {notificacion.mensaje}
                            </p>
                        """
                    )
                )

                api_instance.send_transac_email(
                    email
                )

            except Exception as error:

                print(
                    "Error al enviar correo de "
                    f"notificación: {error}"
                )

        # ============================================
        # Enviar la notificación Push al destinatario
        # ============================================

        if notificacion and usuario:

            tokens = FcmTokens.objects.filter(
                id_usuario=usuario,
                activo=True
            )

            try:
                inicializar_firebase()

                print(
                    f"FCM - Usuario: {usuario.id_usuario} - "
                    f"Cantidad de tokens: {tokens.count()}"
                )

                for fcm_token in tokens:

                    mensaje = messaging.Message(
                        notification=messaging.Notification(
                            title=notificacion.titulo,
                            body=notificacion.mensaje
                        ),
                        data={
                            "id_notificacion": str(
                                notificacion.id_notificacion
                            ),
                            "tipo": str(
                                notificacion.tipo or ""
                            )
                        },
                        android=messaging.AndroidConfig(
                            priority="high",
                            notification=messaging.AndroidNotification(
                                channel_id="geriapp_notificaciones"
                            )
                        ),
                        token=fcm_token.token
                    )

                    try:
                        respuesta = messaging.send(mensaje)

                        print(
                            f"FCM enviado correctamente. "
                            f"Usuario: {usuario.id_usuario}, "
                            f"Token: {fcm_token.id_fcm_token}, "
                            f"Respuesta: {respuesta}"
                        )

                    except Exception as error_token:

                        print(
                            f"Error enviando FCM al token "
                            f"{fcm_token.id_fcm_token}: "
                            f"{error_token}"
                        )

            except Exception as error_firebase:

                print(
                    f"Error inicializando/enviando Firebase: "
                    f"{error_firebase}"
                )

        return response

class CitasViewSet(viewsets.ModelViewSet):
    queryset = Citas.objects.all()
    serializer_class = CitasSerializer

    def perform_create(self, serializer):
        # Guardar la cita normalmente.
        cita = serializer.save()

        # Verificar que la cita tenga un paciente.
        paciente = cita.id_paciente

        if not paciente:
            print(
                "CITAS: La cita fue guardada, "
                "pero no tiene paciente asociado."
            )
            return

        # Buscar la asignación activa más reciente del cuidador.
        asignacion = (
            AsignacionPacienteCuidador.objects
            .filter(
                id_paciente=paciente,
                estado__iexact="Activo"
            )
            .order_by("-fecha_inicio")
            .first()
        )

        if not asignacion or not asignacion.id_usuario:
            print(
                "CITAS: No se encontró un cuidador "
                "con asignación activa para este paciente."
            )
            return

        cuidador = asignacion.id_usuario

        # Crear la notificación dirigida al cuidador.
        notificacion = Notificaciones.objects.create(
            titulo="Nueva cita en tu agenda",
            tipo="cita",
            mensaje=(
                "Se ha registrado una nueva cita para un paciente "
                "a tu cargo. Ingresa a GeriApp para consultar "
                "los detalles."
            ),
            enviar_correo=False,
            fecha_hora=timezone.now(),
            estado=True,
            id_paciente=paciente,
            id_usuario=cuidador
        )

        print(
            "CITAS: Notificación creada. "
            f"Cita: {cita.id_cita}, "
            f"Paciente: {paciente.pk}, "
            f"Cuidador: {cuidador.pk}, "
            f"Notificación: {notificacion.id_notificacion}"
        )


# ============================================================
# TURNOS
# No permite eliminar un turno que tenga asignaciones.
# ============================================================


class TurnosViewSet(viewsets.ModelViewSet):
    queryset = Turnos.objects.all()
    serializer_class = TurnosSerializer

    def destroy(self, request, *args, **kwargs):
        turno = self.get_object()

        # Verificar si el turno tiene asignaciones
        tiene_asignaciones = AsignacionTurnoUsuario.objects.filter(
            id_turno=turno.id_turno
        ).exists()

        # Si tiene asignaciones, no permitir eliminar
        if tiene_asignaciones:
            return Response(
                {
                    'error': 'No se puede eliminar el turno porque está siendo utilizado en asignaciones.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Si no tiene asignaciones, permitir eliminar
        turno.delete()

        return Response(
            {
                'mensaje': 'Turno eliminado correctamente.'
            },
            status=status.HTTP_204_NO_CONTENT
        )

class CierreTurnoViewSet(viewsets.ModelViewSet):
    queryset = CierreTurno.objects.all()
    serializer_class = CierreTurnoSerializer

    def create(self, request, *args, **kwargs):
        """
        Registra el cierre y finaliza la asignación correspondiente.
        La asignación solo cambia a Finalizado si el cierre se guarda.
        """

        id_asignacion = request.data.get(
            "id_asignacion_turno_usuario"
        )

        if not id_asignacion:
            return Response(
                {
                    "error": (
                        "Debes indicar la asignación "
                        "del turno que deseas cerrar."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            id_asignacion = int(id_asignacion)
        except (TypeError, ValueError):
            return Response(
                {"error": "El ID de la asignación no es válido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Bloquea la asignación durante esta operación.
                asignacion = (
                    AsignacionTurnoUsuario.objects
                    .select_for_update()
                    .get(
                        id_asignacion_turno_usuario=id_asignacion
                    )
                )

                # Impide registrar otro cierre para la misma asignación.
                if CierreTurno.objects.filter(
                    id_asignacion_turno_usuario_id=id_asignacion
                ).exists():
                    return Response(
                        {
                            "error": (
                                "Esta asignación ya tiene "
                                "un cierre registrado."
                            )
                        },
                        status=status.HTTP_409_CONFLICT
                    )

                datos = request.data.copy()

                # Estos valores los establece el servidor.
                datos["id_asignacion_turno_usuario"] = id_asignacion
                datos["fecha_hora"] = timezone.now().isoformat()
                datos["confirmo_revision"] = "Sí"
                datos["estado"] = "Finalizado"

                serializer = self.get_serializer(data=datos)
                serializer.is_valid(raise_exception=True)

                # Si falla el guardado, la transacción se revierte.
                cierre = serializer.save()

                # Se actualiza únicamente la asignación cerrada.
                asignacion.estado = "Finalizado"
                asignacion.save(update_fields=["estado"])

            return Response(
                self.get_serializer(cierre).data,
                status=status.HTTP_201_CREATED
            )

        except AsignacionTurnoUsuario.DoesNotExist:
            return Response(
                {"error": "No se encontró la asignación indicada."},
                status=status.HTTP_404_NOT_FOUND
            )


class ResumenCuidadosTurnoView(APIView):

    def get(self, request, id_asignacion):

        try:
            # 1. Obtener asignación, cuidador y turno
            asignacion = (
                AsignacionTurnoUsuario.objects
                .select_related("id_usuario", "id_turno")
                .get(
                    id_asignacion_turno_usuario=id_asignacion
                )
            )

            if not asignacion.id_usuario:
                return Response(
                    {"error": "La asignación no tiene un cuidador."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not asignacion.id_turno:
                return Response(
                    {"error": "La asignación no tiene un turno asociado."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            turno = asignacion.id_turno
            id_cuidador = asignacion.id_usuario_id

            if not turno.hora_inicio:
                return Response(
                    {"error": "El turno no tiene hora de inicio configurada."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Calcular inicio real del turno en Colombia
            zona_colombia = ZoneInfo("America/Bogota")

            fecha_inicio = timezone.make_aware(
                datetime.combine(
                    asignacion.fecha,
                    turno.hora_inicio
                ),
                zona_colombia
            )

            # 3. Buscar únicamente un cierre definitivo
            cierre_turno = (
                CierreTurno.objects
                .filter(
                    id_asignacion_turno_usuario_id=id_asignacion,
                    estado__iexact="Finalizado"
                )
                .order_by("-fecha_hora")
                .first()
            )

            # 4. Determinar el límite final de consulta
            if cierre_turno:
                fecha_fin_consulta = cierre_turno.fecha_hora

                if timezone.is_naive(fecha_fin_consulta):
                    fecha_fin_consulta = timezone.make_aware(
                        fecha_fin_consulta,
                        zona_colombia
                    )

                turno_cerrado = True

            else:
                fecha_fin_consulta = timezone.now()
                turno_cerrado = False

            # Evitar consultas con un intervalo invertido
            fecha_fin_consulta = max(
                fecha_inicio,
                fecha_fin_consulta
            )

            # 5. Obtener pacientes activos del cuidador
            asignaciones_pacientes = (
                AsignacionPacienteCuidador.objects
                .select_related("id_paciente")
                .filter(
                    id_usuario_id=id_cuidador,
                    estado__iexact="Activo"
                )
            )

            pacientes_por_id = {}

            for asignacion_paciente in asignaciones_pacientes:
                paciente = asignacion_paciente.id_paciente

                if paciente:
                    pacientes_por_id[paciente.id_paciente] = paciente

            resultado_pacientes = []

            # 6. Consultar bitácoras, signos vitales y controles
            for id_paciente, paciente in pacientes_por_id.items():

                bitacoras = (
                    Bitacora.objects
                    .filter(
                        id_usuario_id=id_cuidador,
                        id_paciente_id=id_paciente,
                        fecha_hora__gte=fecha_inicio,
                        fecha_hora__lte=fecha_fin_consulta
                    )
                    .order_by("fecha_hora")
                )

                ids_bitacoras = list(
                    bitacoras.values_list(
                        "id_bitacora",
                        flat=True
                    )
                )

                signos = (
                    SignosVitales.objects
                    .filter(
                        id_bitacora_id__in=ids_bitacoras
                    )
                    .order_by("fecha_hora")
                )

                signos_por_bitacora = {}

                for signo in signos:
                    id_bitacora = signo.id_bitacora_id

                    signos_por_bitacora.setdefault(
                        id_bitacora,
                        []
                    ).append(
                        SignosVitalesSerializer(signo).data
                    )

                resultado_bitacoras = []

                for bitacora in bitacoras:
                    datos_bitacora = BitacoraSerializer(
                        bitacora
                    ).data

                    datos_bitacora["signos_vitales"] = (
                        signos_por_bitacora.get(
                            bitacora.id_bitacora,
                            []
                        )
                    )

                    resultado_bitacoras.append(datos_bitacora)

                controles = (
                    ControlesPeriodicosBitacora.objects
                    .filter(
                        id_usuario_id=id_cuidador,
                        id_paciente_id=id_paciente,
                        fecha_registro__gte=fecha_inicio,
                        fecha_registro__lte=fecha_fin_consulta
                    )
                    .order_by("fecha_registro")
                )

                resultado_pacientes.append({
                    "id_paciente": paciente.id_paciente,
                    "nombre": paciente.nombre,
                    "apellido": paciente.apellido,
                    "foto": paciente.foto,
                    "habitacion": paciente.habitacion,
                    "cama": paciente.cama,
                    "bitacoras": resultado_bitacoras,
                    "controles_periodicos": (
                        ControlesPeriodicosBitacoraSerializer(
                            controles,
                            many=True
                        ).data
                    )
                })

            # 7. Respuesta final
            return Response({
                "id_asignacion": asignacion.id_asignacion_turno_usuario,
                "id_cuidador": id_cuidador,

                "turno": {
                    "id_turno": turno.id_turno,
                    "nombre": turno.nombre,
                    "fecha": str(asignacion.fecha),
                    "hora_inicio": str(turno.hora_inicio),
                    "hora_fin": str(turno.hora_fin)
                },

                "fecha_hora_inicio": fecha_inicio,
                "fecha_hora_fin": fecha_fin_consulta,
                "turno_cerrado": turno_cerrado,

                "pacientes": resultado_pacientes

            }, status=status.HTTP_200_OK)

        except AsignacionTurnoUsuario.DoesNotExist:
            return Response(
                {"error": "No se encontró la asignación del turno."},
                status=status.HTTP_404_NOT_FOUND
            )

class AsignacionTurnoUsuarioViewSet(viewsets.ModelViewSet):
        queryset = AsignacionTurnoUsuario.objects.all()
        serializer_class = AsignacionTurnoUsuarioSerializer

        def perform_create(self, serializer):
            asignacion = serializer.save()
            usuario = asignacion.id_usuario

            print("========== PUSH TURNO ==========")
            print("Asignación creada:", asignacion.pk)
            print("Usuario asignado:", usuario.pk if usuario else None)
            print("Fecha del turno:", asignacion.fecha)

            if not usuario:
                print("ERROR: La asignación no tiene usuario.")
                return

            try:
                fecha_turno = asignacion.fecha.strftime("%d/%m/%Y")

                mensaje = (
                    f"Te han asignado un nuevo turno para el día "
                    f"{fecha_turno}. Consulta la sección Inicio de GerIApp."
                )

                notificacion = Notificaciones.objects.create(
                    titulo="Nuevo turno asignado",
                    tipo="TURNO",
                    mensaje=mensaje,
                    enviar_correo=False,
                    fecha_hora=timezone.now(),
                    estado=True,
                    id_usuario=usuario,
                )

                print(
                    "Notificación creada:",
                    notificacion.id_notificacion
                )

                enviar_notificacion_fcm(notificacion, usuario)

                print("Función de envío FCM ejecutada.")

            except Exception as e:
                print("ERROR EN PUSH TURNO:", repr(e))
                raise

class PermisosViewSet(viewsets.ModelViewSet):
    queryset = Permisos.objects.all()
    serializer_class = PermisosSerializer


class PermisosRolViewSet(viewsets.ModelViewSet):
    queryset = PermisosRol.objects.all()
    serializer_class = PermisosRolSerializer


class FamiliarResponsableViewSet(viewsets.ModelViewSet):
    queryset = FamiliarResponsable.objects.all()
    serializer_class = FamiliarResponsableSerializer


class PerfilProfesionalViewSet(viewsets.ModelViewSet):
    queryset = PerfilProfesional.objects.all()
    serializer_class = PerfilProfesionalSerializer


class DisponibilidadUsuarioViewSet(viewsets.ModelViewSet):
    queryset = DisponibilidadUsuario.objects.all()
    serializer_class = DisponibilidadUsuarioSerializer


class RecomendacionesViewSet(viewsets.ModelViewSet):
    queryset = Recomendaciones.objects.all()
    serializer_class = RecomendacionesSerializer
    def perform_create(self, serializer):
        serializer.save(
            fecha_registro=timezone.localdate()
        )


class CuidadosEnfermeriaViewSet(viewsets.ModelViewSet):
    queryset = CuidadosEnfermeria.objects.all()
    serializer_class = CuidadosEnfermeriaSerializer

class AsignacionHabitacionViewSet(viewsets.ModelViewSet):
    queryset = AsignacionHabitacion.objects.all()
    serializer_class = AsignacionHabitacionSerializer

class FundacionesViewSet(viewsets.ModelViewSet):
    queryset = Fundaciones.objects.all()
    serializer_class = FundacionesSerializer

class SedesViewSet(viewsets.ModelViewSet):
    queryset = Sedes.objects.all()
    serializer_class = SedesSerializer
    permission_classes = [EsSuperadministradorOMetodoLectura]

class CamarasViewSet(viewsets.ModelViewSet):
    queryset = Camaras.objects.all()
    serializer_class = CamarasSerializer

class TiposEventoIaViewSet(viewsets.ModelViewSet):
    queryset = TiposEventoIa.objects.all()
    serializer_class = TiposEventoIaSerializer

class EventosIaViewSet(viewsets.ModelViewSet):
    queryset = EventosIa.objects.all()
    serializer_class = EventosIaSerializer

class EvidenciasIaViewSet(viewsets.ModelViewSet):
    queryset = EvidenciasIa.objects.all()
    serializer_class = EvidenciasIaSerializer

class ConfiguracionControlesPeriodicosViewSet(viewsets.ModelViewSet):
    queryset = ConfiguracionControlesPeriodicos.objects.all()
    serializer_class = ConfiguracionControlesPeriodicosSerializer

    @action(detail=False, methods=['get'])
    def estado_paciente(self, request):
        id_paciente = request.query_params.get('id_paciente')

        if not id_paciente:
            return Response(
                {'error': 'Debes enviar el id_paciente'},
                status=status.HTTP_400_BAD_REQUEST
            )

        configuracion = ConfiguracionControlesPeriodicos.objects.filter(
            id_paciente_id=id_paciente
        ).first()

        if not configuracion:
            return Response({
                'configurado': False,
                'habilitado': False,
                'mensaje': 'El administrador todavía no configura los controles.'
            })

        if not configuracion.activo:
            return Response({
                'configurado': True,
                'habilitado': False,
                'activo': False,
                'mensaje': 'Los controles periódicos están desactivados.'
            })

        ultimo_control = ControlesPeriodicosBitacora.objects.filter(
            id_configuracion=configuracion
        ).order_by('-fecha_registro').first()

        ahora = timezone.now()

        if ultimo_control:
            proxima_fecha = ultimo_control.fecha_proximo_control
            habilitado = ahora >= proxima_fecha
        else:
            proxima_fecha = None
            habilitado = True

        return Response({
            'configurado': True,
            'habilitado': habilitado,
            'activo': True,
            'id_configuracion': configuracion.id_configuracion,
            'intervalo_valor': configuracion.intervalo_valor,
            'intervalo_unidad': configuracion.intervalo_unidad,
            'ultimo_control': ultimo_control.fecha_control if ultimo_control else None,
            'fecha_proximo_control': proxima_fecha,
            'mensaje': (
                'Puedes registrar los controles periódicos.'
                if habilitado
                else 'Los controles periódicos todavía están dentro del período establecido.'
            )
        })

class ControlesPeriodicosBitacoraViewSet(viewsets.ModelViewSet):
    queryset = ControlesPeriodicosBitacora.objects.all()
    serializer_class = ControlesPeriodicosBitacoraSerializer

    def create(self, request, *args, **kwargs):
        id_configuracion = request.data.get('id_configuracion')

        if not id_configuracion:
            return Response(
                {'error': 'Debes enviar el id_configuracion'},
                status=status.HTTP_400_BAD_REQUEST
            )

        configuracion = ConfiguracionControlesPeriodicos.objects.filter(
            id_configuracion=id_configuracion,
            activo=True
        ).first()

        if not configuracion:
            return Response(
                {'error': 'No existe una configuración activa.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ultimo_control = ControlesPeriodicosBitacora.objects.filter(
            id_configuracion=configuracion
        ).order_by('-fecha_registro').first()

        ahora = timezone.now()

        if ultimo_control and ahora < ultimo_control.fecha_proximo_control:
            return Response(
                {
                    'error': 'Todavía no se cumple el período de los controles.',
                    'fecha_proximo_control': ultimo_control.fecha_proximo_control
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        intervalo = configuracion.intervalo_valor
        unidad = configuracion.intervalo_unidad.lower().strip()

        if intervalo <= 0:
            return Response(
                {'error': 'El intervalo debe ser mayor que cero.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if unidad in ['dias', 'día', 'día(s)', 'días']:
            proxima_fecha = ahora + timedelta(days=intervalo)

        elif unidad in ['semanas', 'semana']:
            proxima_fecha = ahora + timedelta(weeks=intervalo)

        elif unidad in ['meses', 'mes']:
            proxima_fecha = ahora + relativedelta(months=intervalo)

        else:
            return Response(
                {'error': 'La unidad debe ser días, semanas o meses.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        datos = request.data.copy()
        datos['fecha_registro'] = ahora.isoformat()
        datos['fecha_proximo_control'] = proxima_fecha.isoformat()

        serializer = self.get_serializer(data=datos)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

# ============================================================
# VIEWSET DE REGISTROS FACIALES
# ============================================================

class RegistrosFacialesViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    serializer_class = RegistrosFacialesSerializer

    authentication_classes = [GeriAppTokenAuthentication]
    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "delete",
        "head",
        "options"
    ]

    serializer_class = RegistrosFacialesSerializer
    authentication_classes = [GeriAppTokenAuthentication]
    permission_classes = [IsAuthenticated]

    authentication_classes = [GeriAppTokenAuthentication]
    permission_classes = [IsAuthenticated]

    # ==========================================
    # OBTENER ID DEL ROL
    # ==========================================

    def _obtener_id_rol(self, usuario):

        rol = getattr(usuario, "id_rol", None)

        return (
            getattr(rol, "id_rol", None)
            if rol is not None
            else getattr(usuario, "id_rol_id", None)
        )

    # ==========================================
    # CONSULTAR REGISTROS FACIALES
    # ==========================================

    def get_queryset(self):

        usuario = self.request.user

        if not usuario.is_authenticated:
            return RegistrosFaciales.objects.none()

        if self._obtener_id_rol(usuario) not in (1, 2, 3):
            return RegistrosFaciales.objects.none()

        sede_id = getattr(usuario, "id_sede_id", None)

        if not sede_id:
            return RegistrosFaciales.objects.none()

        # Obtener las habitaciones pertenecientes a la sede
        habitaciones_sede = Habitaciones.objects.filter(
            id_sede_id=sede_id
        ).values_list("id_habitacion", flat=True)

        # Consultar registros faciales de pacientes activos
        # que estén ubicados en habitaciones de la sede
        queryset = RegistrosFaciales.objects.filter(
            activo=True,
            id_paciente__estado=True,
            id_paciente__habitacion__in=habitaciones_sede
        ).select_related("id_paciente").distinct()

        # Filtrar por paciente cuando se envíe el identificador
        id_paciente = self.request.query_params.get("id_paciente")

        if id_paciente:
            queryset = queryset.filter(
                id_paciente_id=id_paciente
            )

        return queryset

    # ==========================================
    # OBTENER PLANTILLAS FACIALES POR CÁMARA
    # ==========================================

    @action(
        detail=False,
        methods=["get"],
        url_path="plantillas"
    )
    def plantillas(self, request):

        # 1. Obtener el usuario autenticado
        usuario = request.user

        if not usuario.is_authenticated:
            return Response(
                {"error": "Usuario no autenticado."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 2. Validar el rol
        if self._obtener_id_rol(usuario) not in (1, 2, 3):
            return Response(
                {"error": "No tienes permisos para consultar plantillas faciales."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Obtener la sede del usuario
        sede_id = getattr(usuario, "id_sede_id", None)

        if not sede_id:
            return Response(
                {"error": "Tu usuario no tiene una sede asignada."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Obtener el ID de la cámara
        id_camara = request.query_params.get("id_camara")

        if not id_camara:
            return Response(
                {"error": "El parámetro id_camara es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            id_camara = int(id_camara)
        except (ValueError, TypeError):
            return Response(
                {"error": "El ID de la cámara debe ser un número válido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Buscar la cámara y verificar que pertenezca a la sede
        camara = Camaras.objects.filter(
            id_camara=id_camara,
            estado=True,
            id_habitacion__estado=True,
            id_habitacion__id_sede_id=sede_id
        ).select_related(
            "id_habitacion"
        ).first()

        if not camara:
            return Response(
                {
                    "error": "La cámara no existe, está inactiva "
                             "o no pertenece a tu sede."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # 6. Obtener la habitación de la cámara
        id_habitacion = camara.id_habitacion_id

        if not id_habitacion:
            return Response(
                {"error": "La cámara no tiene una habitación asignada."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 7. Consultar registros faciales de pacientes activos
        #    que pertenezcan a la habitación de esta cámara
        registros = RegistrosFaciales.objects.filter(
            activo=True,
            id_paciente__estado=True,
            id_paciente__habitacion=id_habitacion
        ).select_related(
            "id_paciente"
        )

        # 8. Preparar las plantillas para el programa local
        plantillas = []

        for registro in registros:

            embedding_cifrado = bytes(registro.embedding)

            plantillas.append({
                "id_registro_facial": registro.id_registro_facial,
                "id_paciente": registro.id_paciente_id,
                "embedding_cifrado": base64.b64encode(
                    embedding_cifrado
                ).decode("ascii")
            })

        # 9. Responder
        return Response(
            {
                "id_camara": camara.id_camara,
                "id_habitacion": id_habitacion,
                "total_plantillas": len(plantillas),
                "plantillas": plantillas
            },
            status=status.HTTP_200_OK
        )

    # ==========================================
    # VALIDAR PACIENTE Y SEDE
    # ==========================================

    def _validar_paciente(self, id_paciente):

        usuario = self.request.user

        if self._obtener_id_rol(usuario) not in (1, 2, 3):
            return None

        sede_id = getattr(usuario, "id_sede_id", None)

        if not sede_id:
            return None

        # Obtener habitaciones de la sede del usuario
        habitaciones_sede = Habitaciones.objects.filter(
            id_sede_id=sede_id
        ).values_list("id_habitacion", flat=True)

        # Buscar paciente activo que esté en una habitación
        # perteneciente a la sede del usuario
        paciente = Pacientes.objects.filter(
            id_paciente=id_paciente,
            estado=True,
            habitacion__in=habitaciones_sede
        ).first()

        return paciente

    # ==========================================
    # PROCESAR FOTOGRAFÍA Y GENERAR EMBEDDING
    # ==========================================

    def _procesar_fotografia(self, fotografia):

        if not fotografia:
            raise ValueError("Debe seleccionar una fotografía.")

        reconocedor = ReconocedorFacial()

        resultados = reconocedor.procesar_imagen(fotografia)

        print(
        f"[REGISTRO FACIAL] Archivo: {fotografia.name} | "
        f"Detecciones: {len(resultados)}"
    )

        if len(resultados) == 0:
            raise ValueError(
                "No se detectó ningún rostro en la fotografía."
            )

        if len(resultados) > 1:
            raise ValueError(
                "La fotografía debe contener únicamente un rostro."
            )

        embedding = resultados[0]["embedding"]

        embedding_bytes = embedding.tobytes()

        embedding_cifrado = cifrar_embedding(embedding_bytes)

        fotografia.seek(0)

        return embedding_cifrado

    # ==========================================
    # REGISTRAR ROSTRO
    # ==========================================
    @action(
    detail=False,
    methods=["post"],
    url_path="registrar",
    parser_classes=[MultiPartParser, FormParser]
    )
    def registrar(self, request):

        id_paciente = request.data.get("id_paciente")

        # Recibir todas las fotografías enviadas desde Angular
        fotografias = request.FILES.getlist("fotografias")

        # 1. Validar paciente
        if not id_paciente:
            return Response(
                {"error": "El id_paciente es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Validar fotografías
        if len(fotografias) < 3:
            return Response(
                {
                    "error": (
                        "Debe enviar al menos tres fotografías: "
                        "frontal, perfil izquierdo y perfil derecho."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Validar que el paciente exista y pertenezca a la sede
        paciente = self._validar_paciente(id_paciente)

        if not paciente:
            return Response(
                {
                    "error": (
                        "El paciente no existe, está inactivo "
                        "o no pertenece a tu sede."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. Procesar todas las fotografías antes de subirlas
        embeddings = []

        try:
            for fotografia in fotografias:

                embedding_cifrado = self._procesar_fotografia(
                    fotografia
                )

                embeddings.append(embedding_cifrado)

        except ValueError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception:
            logger.exception(
                "Error procesando las fotografías faciales."
            )

            return Response(
                {
                    "error": (
                        "No fue posible procesar una o varias "
                        "fotografías."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Identificar el tipo de cada fotografía según su posición
        tipos_fotografia = [
            "FRONTAL",
            "IZQUIERDA",
            "DERECHA"
        ]

        tipos_fotografia.extend(
            ["ADICIONAL"] * max(0, len(fotografias) - 3)
        )

        # 5. Subir las fotografías a Cloudinary
        imagenes_subidas = []
        registros_creados = []

        try:

            for fotografia in fotografias:

                fotografia.seek(0)

                resultado_cloudinary = subir_imagen(
                    fotografia,
                    carpeta="geriapp/reconocimiento_facial"
                )

                if not resultado_cloudinary.get("secure_url"):
                    raise RuntimeError(
                        "Cloudinary no devolvió la URL de la fotografía."
                    )

                if not resultado_cloudinary.get("public_id"):
                    raise RuntimeError(
                        "Cloudinary no devolvió el public_id."
                    )

                imagenes_subidas.append(resultado_cloudinary)

            # 6. Crear un registro independiente por fotografía
            with transaction.atomic():

                for embedding_cifrado, imagen, tipo in zip(
                    embeddings,
                    imagenes_subidas,
                    tipos_fotografia
                ):

                    registro = RegistrosFaciales.objects.create(
                        id_paciente=paciente,
                        embedding=embedding_cifrado,
                        url_fotografia=imagen["secure_url"],
                        public_id=imagen["public_id"],
                        tipo_fotografia=tipo,
                        activo=True
                    )

                    registros_creados.append(registro)

            # 7. Serializar todos los registros creados
            serializer = self.get_serializer(
                registros_creados,
                many=True
            )

            return Response(
                {
                    "mensaje": (
                        "Registro facial completado correctamente."
                    ),
                    "id_paciente": paciente.id_paciente,
                    "total_fotografias": len(registros_creados),
                    "registros": serializer.data
                },
                status=status.HTTP_201_CREATED
            )

        except Exception:

            logger.exception(
                "Error guardando los registros faciales."
            )

            # 8. Limpiar las imágenes de Cloudinary si ocurre un error
            for imagen in imagenes_subidas:

                public_id = imagen.get("public_id")

                if public_id:
                    try:
                        eliminar_imagen(public_id)

                    except Exception:
                        logger.exception(
                            "No fue posible eliminar una imagen "
                            "de Cloudinary."
                        )

            return Response(
                {
                    "error": (
                        "No fue posible completar el registro facial. "
                        "Verifique las fotografías e intente nuevamente."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ==========================================
    # ACTUALIZAR ROSTRO
    # ==========================================

    @action(
        detail=False,
        methods=["post"],
        url_path="actualizar",
        parser_classes=[MultiPartParser, FormParser]
    )
    def actualizar(self, request):

        id_registro_facial = request.data.get("id_registro_facial")
        fotografia = request.FILES.get("fotografia")

        # 1. Validar identificador del registro facial
        if not id_registro_facial:
            return Response(
                {"error": "El id_registro_facial es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Validar fotografía
        if not fotografia:
            return Response(
                {"error": "Debe enviar una nueva fotografía."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Buscar el registro facial específico
        registro = self.get_queryset().filter(
            id_registro_facial=id_registro_facial,
            activo=True
        ).first()

        if not registro:
            return Response(
                {
                    "error": (
                        "El registro facial no existe, está inactivo "
                        "o no pertenece a tu sede."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. Guardar el public_id anterior
        public_id_anterior = registro.public_id

        resultado_cloudinary = None

        try:

            # 5. Procesar nueva fotografía y generar embedding
            embedding_cifrado = self._procesar_fotografia(
                fotografia
            )

        except ValueError as error:

            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception:

            logger.exception(
                "Error procesando nueva fotografía facial."
            )

            return Response(
                {
                    "error": "No fue posible procesar la nueva fotografía."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:

            # 6. Subir nueva fotografía a Cloudinary
            fotografia.seek(0)

            resultado_cloudinary = subir_imagen(
                fotografia,
                carpeta="geriapp/reconocimiento_facial"
            )

            if not resultado_cloudinary.get("secure_url"):
                raise RuntimeError(
                    "Cloudinary no devolvió la URL."
                )

            if not resultado_cloudinary.get("public_id"):
                raise RuntimeError(
                    "Cloudinary no devolvió el public_id."
                )

            # 7. Actualizar únicamente el registro seleccionado
            with transaction.atomic():

                registro.embedding = embedding_cifrado

                registro.url_fotografia = (
                    resultado_cloudinary["secure_url"]
                )

                registro.public_id = (
                    resultado_cloudinary["public_id"]
                )

                registro.save(
                    update_fields=[
                        "embedding",
                        "url_fotografia",
                        "public_id",
                        "fecha_actualizacion"
                    ]
                )

        except Exception:

            logger.exception(
                "Error actualizando el registro facial."
            )

            # 8. Eliminar la nueva imagen si falló la actualización
            if resultado_cloudinary:

                public_id_nuevo = resultado_cloudinary.get(
                    "public_id"
                )

                if public_id_nuevo:

                    try:

                        eliminar_imagen(public_id_nuevo)

                    except Exception:

                        logger.exception(
                            "No fue posible eliminar la nueva imagen de Cloudinary."
                        )


            return Response(
                    {
                        "error": "No fue posible actualizar el registro facial."
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    # 9. Eliminar fotografía anterior de Cloudinary
            advertencia = None

            if public_id_anterior:
                try:
                    eliminar_imagen(public_id_anterior)
                except Exception:
                    logger.exception(
                        "No fue posible eliminar la fotografía anterior."
                    )
                    advertencia = (
                        "La fotografía fue actualizada, pero no se pudo "
                        "eliminar la imagen anterior de Cloudinary."
                    )

            # 10. Devolver registro actualizado
            serializer = self.get_serializer(registro)

            respuesta = {
                "mensaje": "Registro facial actualizado correctamente.",
                "registro": serializer.data
            }

            if advertencia:
                respuesta["advertencia"] = advertencia

            return Response(
                respuesta,
                status=status.HTTP_200_OK
            )

        # ==========================================
        # ELIMINAR UNA FOTOGRAFÍA FACIAL
        # ==========================================

    def destroy(self, request, *args, **kwargs):

        registro = self.get_object()
        public_id = registro.public_id

        try:
            registro.activo = False
            registro.save(update_fields=["activo"])

        except Exception:
            logger.exception(
                "Error desactivando el registro facial."
            )
            return Response(
                {"error": "No fue posible eliminar la fotografía."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        advertencia = None

        if public_id:
            try:
                eliminar_imagen(public_id)
            except Exception:
                logger.exception(
                    "No fue posible eliminar la imagen de Cloudinary."
                )
                advertencia = (
                    "El registro fue desactivado, pero la imagen "
                    "no pudo eliminarse de Cloudinary."
                )

        respuesta = {
            "mensaje": "Fotografía facial eliminada correctamente."
        }

        if advertencia:
            respuesta["advertencia"] = advertencia

        return Response(
            respuesta,
            status=status.HTTP_200_OK
        )


# ============================================================
# VIEWSET DE ELEMENTOS DEL PACIENTE
# ============================================================

class ElementosPacienteViewSet(viewsets.ModelViewSet):

    queryset = ElementosPaciente.objects.all()

    serializer_class = ElementosPacienteSerializer

    # ========================================================
    # CREAR ELEMENTO DEL PACIENTE
    # ========================================================

    def perform_create(self, serializer):

        # ====================================================
        # GUARDAR EL ELEMENTO DEL PACIENTE
        # ====================================================

        elemento = serializer.save()

        # ====================================================
        # VALIDAR SI ES UN MEDICAMENTO
        # ====================================================

        if elemento.id_medicamentos:

            # =================================================
            # CREAR SU REGISTRO CORRESPONDIENTE EN INVENTARIO
            # =================================================

            Inventario.objects.create(
                id_paciente=elemento.id_paciente,
                id_medicamentos=elemento.id_medicamentos,
                id_elemento=elemento,
                cantidad_actual=elemento.cantidad,
                cantidad_minima=5,
                fecha_ultimo_ingreso=elemento.fecha_ingreso,
                fecha_vencimiento=elemento.fecha_vencimiento,
                estado=True
            )

    # ========================================================
    # EDITAR ELEMENTO DEL PACIENTE
    # ========================================================

    def perform_update(self, serializer):

        # ====================================================
        # OBTENER EL ELEMENTO QUE SE ESTÁ EDITANDO
        # ====================================================

        elemento = self.get_object()

        # ====================================================
        # GUARDAR LOS CAMBIOS
        # ====================================================

        elemento = serializer.save()

        # ====================================================
        # BUSCAR EL INVENTARIO RELACIONADO
        # ====================================================

        inventario = Inventario.objects.filter(
            id_elemento=elemento.id_elemento
        ).first()

        # ====================================================
        # SI SIGUE SIENDO UN MEDICAMENTO
        # ====================================================

        if elemento.id_medicamentos:

            # =================================================
            # SI YA TIENE INVENTARIO, ACTUALIZARLO
            # =================================================

            if inventario:

                inventario.id_paciente = elemento.id_paciente
                inventario.id_medicamentos = elemento.id_medicamentos
                inventario.cantidad_actual = elemento.cantidad
                inventario.fecha_ultimo_ingreso = elemento.fecha_ingreso
                inventario.fecha_vencimiento = elemento.fecha_vencimiento
                inventario.estado = True

                inventario.save()

            # =================================================
            # SI NO TIENE INVENTARIO, CREARLO
            # =================================================

            else:

                Inventario.objects.create(
                    id_paciente=elemento.id_paciente,
                    id_medicamentos=elemento.id_medicamentos,
                    id_elemento=elemento,
                    cantidad_actual=elemento.cantidad,
                    cantidad_minima=5,
                    fecha_ultimo_ingreso=elemento.fecha_ingreso,
                    fecha_vencimiento=elemento.fecha_vencimiento,
                    estado=True
                )

        # ====================================================
        # SI EL ELEMENTO DEJÓ DE SER UN MEDICAMENTO
        # ====================================================

        else:

            # =================================================
            # ELIMINAR SU INVENTARIO
            # =================================================

            if inventario:

                inventario.delete()

    # ========================================================
    # ELIMINAR ELEMENTO DEL PACIENTE
    # ========================================================

    def perform_destroy(self, instance):

        # ====================================================
        # BUSCAR EL INVENTARIO RELACIONADO
        # ====================================================

        inventario = Inventario.objects.filter(
            id_elemento=instance.id_elemento
        ).first()

        # ====================================================
        # ELIMINAR PRIMERO EL INVENTARIO
        # ====================================================

        if inventario:

            inventario.delete()

        # ====================================================
        # ELIMINAR EL ELEMENTO DEL PACIENTE
        # ====================================================

        instance.delete()

class RecuperacionPasswordViewSet(viewsets.ModelViewSet):
    queryset = RecuperacionPassword.objects.all()
    serializer_class = RecuperacionPasswordSerializer

# ============================================================
# SUBIR IMAGEN A CLOUDINARY
# ============================================================

class SubirImagenCloudinaryView(APIView):

    def post(self, request):

        # Obtener la imagen enviada desde Insomnia
        imagen = request.FILES.get('imagen')

        # Verificar que se haya enviado una imagen
        if not imagen:
            return Response(
                {
                    'error': 'Debe seleccionar una imagen.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            # Subir la imagen a Cloudinary
            resultado = subir_imagen(
                imagen,
                'geriapp/imagenes'
            )

            # Devolver la URL generada por Cloudinary
            return Response(
                {
                    'mensaje': 'Imagen subida correctamente.',
                    'url': resultado['secure_url'],
                    'public_id': resultado['public_id']
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as error:

            return Response(
                {
                    'error': 'No se pudo subir la imagen.',
                    'detalle': str(error)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def obtener_token_livekit(request):
    """Genera un token temporal para ver una habitación autorizada."""

    usuario = getattr(request.user, 'usuario', request.user)

    if not usuario.estado or usuario.id_rol_id != 3:
        return Response(
            {'error': 'Solo los cuidadores activos pueden ver las cámaras.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        id_habitacion = int(request.data.get('id_habitacion'))
    except (TypeError, ValueError):
        return Response(
            {'error': 'Debes indicar un id_habitacion válido.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    habitacion = Habitaciones.objects.filter(
        id_habitacion=id_habitacion,
        estado=True
    ).first()

    if not habitacion:
        return Response(
            {'error': 'La habitación no existe o está inactiva.'},
            status=status.HTTP_404_NOT_FOUND
        )

    camara = Camaras.objects.filter(
        id_habitacion_id=id_habitacion,
        estado=True
    ).first()

    if not camara:
        return Response(
            {'error': 'La habitación no tiene una cámara activa.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Comprobar que el cuidador tenga asignado un paciente activo
    # que figure actualmente en la habitación solicitada.
    paciente_autorizado = AsignacionPacienteCuidador.objects.filter(
    id_usuario_id=usuario.id_usuario,
    id_paciente__habitacion=id_habitacion,
    id_paciente__estado=True,
    estado__iexact='Activo'
    ).exists()

    if not paciente_autorizado:
        return Response(
            {'error': 'No tienes pacientes activos asignados en esta habitación.'},
            status=status.HTTP_403_FORBIDDEN
        )

    livekit_url = os.getenv('LIVEKIT_RTC_URL')
    livekit_api_key = os.getenv('LIVEKIT_API_KEY')
    livekit_api_secret = os.getenv('LIVEKIT_API_SECRET')

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        return Response(
            {'error': 'La configuración de LiveKit está incompleta.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if not livekit_url.startswith('wss://'):
        return Response(
            {'error': 'LIVEKIT_URL debe ser la dirección segura wss:// de LiveKit.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    nombre_sala = f'geriapp-habitacion-{id_habitacion}'

    token = (
        api.AccessToken(livekit_api_key, livekit_api_secret)
        .with_identity(f'cuidador-{usuario.id_usuario}')
        .with_name(
            f'{getattr(usuario, "nombres", "")} '
            f'{getattr(usuario, "apellidos", "")}'.strip()
        )
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=nombre_sala,
                can_subscribe=True,
                can_publish=False,
                can_publish_data=False
            )
        )
        .to_jwt()
    )
    return Response(
        {
            'token': token,
            'url': livekit_url,
            'room': nombre_sala,
            'id_habitacion': id_habitacion,
        },
        status=status.HTTP_200_OK
    )