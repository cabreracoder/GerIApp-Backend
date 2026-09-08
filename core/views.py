from django.core.serializers import python
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth.hashers import (check_password,make_password)

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
)
#Esta parte hace que se pueda registrar un usuario, validando que no exista otro con el mismo correo o número de documento.
#Si el registro es exitoso, devuelve un mensaje de éxito y los datos del usuario registrado. Si hay errores en la validación,
#devuelve los errores correspondientes.     
@api_view(['POST'])
def registro_usuario(request):

    serializer = RegistroUsuarioSerializer(data=request.data)

    if serializer.is_valid():

        correo = serializer.validated_data['correo']
        numero_documento = serializer.validated_data['numero_documento']

        if Usuarios.objects.filter(correo=correo).exists():
            return Response(
                {'error': 'Ya existe un usuario con este correo.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if Usuarios.objects.filter(numero_documento=numero_documento).exists():
            return Response(
                {'error': 'Ya existe un usuario con este número de documento.'},
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
                    'estado': usuario.estado
                }
            },
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST

    )
#esta parte permite que un usuario pueda iniciar sesión en la aplicación, validando su correo y contraseña.
@api_view(['POST'])
def login_usuario(request):

    correo = request.data.get('correo')
    contrasena = request.data.get('contrasena')

    if not correo or not contrasena:
        return Response(
            {'error': 'El correo y la contraseña son obligatorios.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        usuario = Usuarios.objects.get(correo=correo)
    except Usuarios.DoesNotExist:
        return Response(
            {'error': 'Credenciales inválidas.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not usuario.contrasena:
        return Response(
            {'error': 'Este usuario no tiene una contraseña registrada.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not check_password(contrasena, usuario.contrasena):
        return Response(
            {'error': 'Credenciales inválidas.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not usuario.estado:
        return Response(
            {'error': 'El usuario se encuentra inactivo.'},
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

#Aqui hacemos que un usuario pueda cambiar su contraseña, 
#validando la contraseña actual y asegurando que la nueva contraseña sea diferente a la actual.    

@api_view(['POST'])
def cambiar_contrasena(request):

    id_usuario = request.data.get(
        'id_usuario'
    )

    if not id_usuario:

        return Response(
            {
                'error':
                'El ID del usuario es obligatorio.'
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
                'error':
                'El usuario no existe.'
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

    contrasena_actual = (
        serializer.validated_data[
            'contrasena_actual'
        ]
    )

    nueva_contrasena = (
        serializer.validated_data[
            'nueva_contrasena'
        ]
    )

    # =====================================================
    # VERIFICAR CONTRASEÑA ACTUAL
    # =====================================================

    if not usuario.contrasena:

        return Response(
            {
                'error':
                'Este usuario no tiene una contraseña registrada.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not check_password(
        contrasena_actual,
        usuario.contrasena
    ):

        return Response(
            {
                'error':
                'La contraseña actual es incorrecta.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # =====================================================
    # EVITAR USAR LA MISMA CONTRASEÑA
    # =====================================================

    if check_password(
        nueva_contrasena,
        usuario.contrasena
    ):

        return Response(
            {
                'error':
                'La nueva contraseña debe ser diferente a la actual.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # =====================================================
    # GUARDAR NUEVA CONTRASEÑA HASHEADA
    # =====================================================

    usuario.contrasena = make_password(
        nueva_contrasena
    )

    usuario.save(
        update_fields=['contrasena']
    )

    return Response(
        {
            'mensaje':
            'Contraseña actualizada correctamente.'
        },
        status=status.HTTP_200_OK
    )



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


class TurnosViewSet(viewsets.ModelViewSet):
    queryset = Turnos.objects.all()
    serializer_class = TurnosSerializer


class AsignacionTurnoUsuarioViewSet(viewsets.ModelViewSet):
    queryset = AsignacionTurnoUsuario.objects.all()
    serializer_class = AsignacionTurnoUsuarioSerializer

class PermisosViewSet(viewsets.ModelViewSet):
    queryset =Permisos.objects.all()
    serializer_class =PermisosSerializer

class PermisosRolViewSet(viewsets.ModelViewSet):
    queryset=PermisosRol.objects.all()
    serializer_class=PermisosRolSerializer

class FamiliarResponsableViewSet(viewsets.ModelViewSet):
    queryset = FamiliarResponsable.objects.all()
    serializer_class = FamiliarResponsableSerializer


class PerfilProfesionalViewSet(viewsets.ModelViewSet):
    queryset = PerfilProfesional.objects.all()
    serializer_class = PerfilProfesionalSerializer


class DisponibilidadUsuarioViewSet(viewsets.ModelViewSet):
    queryset = DisponibilidadUsuario.objects.all()
    serializer_class = DisponibilidadUsuarioSerializer