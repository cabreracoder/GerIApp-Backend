from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth.hashers import check_password, make_password

import sib_api_v3_sdk
from django.conf import settings
import random
from datetime import timedelta
from django.utils import timezone

from .models import (
    HistoriaClinicas,
    Pacientes,
    Medicamentos,
    Roles,
    Usuarios,
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
    AsignacionPacienteCuidador,
    Turnos,
    AsignacionTurnoUsuario,
    Permisos,
    PermisosRol,
    FamiliarResponsable,
    PerfilProfesional,
    DisponibilidadUsuario,
    Recomendaciones,
    CuidadosEnfermeria,
    ElementosPaciente,
    RecuperacionPassword,
)

from .serializers import (
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
    AsignacionTurnoUsuarioSerializer,
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
)


# ============================================================
# REGISTRO DE USUARIO
# ============================================================

@api_view(['POST'])
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
                    'estado': usuario.estado
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
            'usuario': {
                'id_usuario': usuario.id_usuario,
                'nombres': usuario.nombres,
                'apellidos': usuario.apellidos,
                'correo': usuario.correo,
                'id_rol': usuario.id_rol_id,
                'rol': usuario.id_rol.nombre if usuario.id_rol else None,
                'estado': usuario.estado
            }
        },
        status=status.HTTP_200_OK
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

class PacientesViewSet(viewsets.ModelViewSet):
    queryset = Pacientes.objects.all()
    serializer_class = PacientesSerializer


class MedicamentosViewSet(viewsets.ModelViewSet):
    queryset = Medicamentos.objects.all()
    serializer_class = MedicamentosSerializer


class RolesViewSet(viewsets.ModelViewSet):
    queryset = Roles.objects.all()
    serializer_class = RolesSerializer


class UsuariosViewSet(viewsets.ModelViewSet):
    queryset = Usuarios.objects.all()
    serializer_class = UsuariosSerializer


class DocumentosViewSet(viewsets.ModelViewSet):
    queryset = Documentos.objects.all()
    serializer_class = DocumentosSerializer


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


class InventarioViewSet(viewsets.ModelViewSet):
    queryset = Inventario.objects.all()
    serializer_class = InventarioSerializer


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


class AsignacionTurnoUsuarioViewSet(viewsets.ModelViewSet):
    queryset = AsignacionTurnoUsuario.objects.all()
    serializer_class = AsignacionTurnoUsuarioSerializer


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


class CuidadosEnfermeriaViewSet(viewsets.ModelViewSet):
    queryset = CuidadosEnfermeria.objects.all()
    serializer_class = CuidadosEnfermeriaSerializer


class ElementosPacienteViewSet(viewsets.ModelViewSet):
    queryset = ElementosPaciente.objects.all()
    serializer_class = ElementosPacienteSerializer


class RecuperacionPasswordViewSet(viewsets.ModelViewSet):
    queryset = RecuperacionPassword.objects.all()
    serializer_class = RecuperacionPasswordSerializer