from django.core.serializers import python
from rest_framework import serializers
from django.utils import timezone

from .models import (
    Medicamentos,
    Pacientes,
    Roles,
    Usuarios,
    Documentos,
    HistoriaClinicas,
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
)



class PacientesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pacientes
        fields = '__all__'


class MedicamentosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicamentos
        fields = '__all__'


class RolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Roles
        fields = '__all__'


class UsuariosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuarios
        fields = '__all__'

class DocumentosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documentos
        fields = '__all__'


class HistoriaClinicasSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoriaClinicas
        fields = '__all__'


class EnfermedadesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enfermedades
        fields = '__all__'


class DiagnosticosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diagnosticos
        fields = '__all__'


class TratamientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tratamientos
        fields = '__all__'


class TratamientoMedicamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TratamientoMedicamento
        fields = '__all__'


class InventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventario
        fields = '__all__'


class EntregaMedicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntregaMedica
        fields = '__all__'


class DetalleEntregaMedicamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleEntregaMedicamento
        fields = '__all__'


class MovimientoMedicamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoMedicamento
        fields = '__all__'


class AplicacionMedicamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AplicacionMedicamento
        fields = '__all__'


class TipoInsumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoInsumo
        fields = '__all__'


class InsumosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insumos
        fields = '__all__'


class DetalleEntregaInsumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleEntregaInsumos
        fields = '__all__'


class EntregaInsumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntregaInsumo
        fields = '__all__'


class MovimientoInsumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInsumo
        fields = '__all__'


class BitacoraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bitacora
        fields = '__all__'


class ActividadesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Actividades
        fields = '__all__'


class SignosVitalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignosVitales
        fields = '__all__'


class TipoEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoEvento
        fields = '__all__'


class TipoEmergenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoEmergencia
        fields = '__all__'


class EventosAdversosSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventosAdversos
        fields = '__all__'


class ImagenesEventoAdversoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImagenesEventoAdverso
        fields = '__all__'


class AsignacionPacienteCuidadorSerializer(serializers.ModelSerializer):
    class Meta:
        model = AsignacionPacienteCuidador
        fields = '__all__'


class TurnosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Turnos
        fields = '__all__'


class AsignacionTurnoUsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = AsignacionTurnoUsuario
        fields = '__all__'

class PermisosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permisos
        fields = '__all__'

class PermisosRolSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermisosRol
        fields = '__all__'

class FamiliarResponsableSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamiliarResponsable
        fields = '__all__'


class PerfilProfesionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilProfesional
        fields = '__all__'


class DisponibilidadUsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisponibilidadUsuario
        fields = '__all__'

class RecomendacionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recomendaciones
        fields = '__all__'

class CuidadosEnfermeriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuidadosEnfermeria
        fields = '__all__'


# Esta parte permite registrar un usuario desde la aplicación,
# encripta la contraseña y establece el usuario como activo.
class RegistroUsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuarios
        fields = [
            'nombres',
            'apellidos',
            'correo',
            'tipo_documento',
            'numero_documento',
            'telefono',
            'contrasena',
        ]
        extra_kwargs = {
            'contrasena': {'write_only': True}
        }

    def create(self, validated_data):
        from django.contrib.auth.hashers import make_password

        validated_data['contrasena'] = make_password(
            validated_data['contrasena']
        )

        validated_data['estado'] = True
        validated_data['fecha_ingreso'] = timezone.now()

        usuario = Usuarios.objects.create(**validated_data)

        return usuario

#Aqui lo que estamos haciendo es crear un serializer para cambiar la contraseña del usuario,
#este serializer recibe la contraseña actual, la nueva contraseña y la confirmación de la
#nueva contraseña, si las contraseñas nuevas no coinciden se lanza un error de validación. 

class CambiarContrasenaSerializer(serializers.Serializer):
    contrasena_actual = serializers.CharField(
        write_only=True
    )

    nueva_contrasena = serializers.CharField(
        write_only=True,
        min_length=8
    )

    confirmar_contrasena = serializers.CharField(
        write_only=True
    )

    def validate(self, data):

        nueva_contrasena = data.get(
            'nueva_contrasena'
        )

        confirmar_contrasena = data.get(
            'confirmar_contrasena'
        )

        if nueva_contrasena != confirmar_contrasena:

            raise serializers.ValidationError(
                'Las contraseñas nuevas no coinciden.'
            )

        return data

