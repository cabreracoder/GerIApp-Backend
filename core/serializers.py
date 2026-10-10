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
    ElementosPaciente,
    RecuperacionPassword,
    Notificaciones,
    NotificacionDestinatario,
    Citas,
    FcmTokens,
    Camas,
    Habitaciones,
    Fundaciones,
    Sedes,
    Camaras,
    TiposEventoIa,
    EventosIa,
    EvidenciasIa,
    AsignacionHabitacion,
    GrupoMedicacion,
    FormulacionMedicamentos,
)



class PacientesSerializer(serializers.ModelSerializer):
    # Permite recibir una imagen desde FormData
    foto = serializers.CharField(
        required=False,
        allow_null=True
    )

    class Meta:
        model = Pacientes
        fields = '__all__'

    def to_internal_value(self, data):
        # Copiamos los datos recibidos para poder modificar la foto
        data = data.copy()

        imagen = data.get('foto')

        # Si Angular envía un archivo, lo dejamos pasar directamente
        if imagen and hasattr(imagen, 'read'):
            data.pop('foto')

            datos_validados = super().to_internal_value(data)

            # Agregamos el archivo manualmente
            datos_validados['foto'] = imagen

            return datos_validados

        return super().to_internal_value(data)

    # =====================================================
    # VALIDAR HABITACIÓN Y CAMA DEL PACIENTE
    # =====================================================

    def validate(self, attrs):

        from .models import Habitaciones, Camas, Pacientes

        # Mantener los valores actuales al editar
        habitacion_id = attrs.get(
            'habitacion',
            self.instance.habitacion if self.instance else None
        )

        cama_id = attrs.get(
            'cama',
            self.instance.cama if self.instance else None
        )

        # Comprobar que haya habitación y cama
        if habitacion_id is None or cama_id is None:
            raise serializers.ValidationError({
                'ubicacion': 'Debes seleccionar una habitación y una cama.'
            })

        # Verificar habitación
        habitacion = Habitaciones.objects.filter(
            id_habitacion=habitacion_id
        ).first()

        if not habitacion:
            raise serializers.ValidationError({
                'habitacion': 'La habitación seleccionada no existe.'
            })

        if not habitacion.estado:
            raise serializers.ValidationError({
                'habitacion': 'Esta habitación está inactiva.'
            })

        # Verificar cama
        cama = Camas.objects.filter(
            id_cama=cama_id
        ).first()

        if not cama:
            raise serializers.ValidationError({
                'cama': 'La cama seleccionada no existe.'
            })

        if not cama.estado:
            raise serializers.ValidationError({
                'cama': 'Esta cama está inactiva.'
            })

        # Verificar que pertenezca a la habitación
        if cama.id_habitacion_id != habitacion.id_habitacion:
            raise serializers.ValidationError({
                'cama': 'La cama no pertenece a la habitación seleccionada.'
            })

        # Buscar pacientes que ya ocupan esa cama
        ocupantes = Pacientes.objects.filter(
            habitacion=habitacion_id,
            cama=cama_id
        )

        # Al editar, excluir al mismo paciente
        if self.instance:
            ocupantes = ocupantes.exclude(
                id_paciente=self.instance.id_paciente
            )

        if ocupantes.exists():
            raise serializers.ValidationError({
                'cama': 'Esta cama ya está asignada a otro paciente.'
            })

        return attrs

    def create(self, validated_data):
        from servicios.cloudinary_service import subir_imagen

        # Obtener la foto enviada
        imagen = validated_data.pop('foto', None)

        # Si se envió una foto, subirla a Cloudinary
        if imagen and hasattr(imagen, 'read'):
            resultado = subir_imagen(
                imagen,
                'geriapp/pacientes'
            )

            # Guardar la URL de Cloudinary
            validated_data['foto'] = resultado['secure_url']

        paciente = Pacientes.objects.create(**validated_data)

        return paciente

    def update(self, instance, validated_data):
        from servicios.cloudinary_service import subir_imagen

        # Obtener la foto enviada
        imagen = validated_data.pop('foto', None)

        # Si se envió una nueva foto, subirla a Cloudinary
        if imagen and hasattr(imagen, 'read'):
            resultado = subir_imagen(
                imagen,
                'geriapp/pacientes'
            )

            # Guardar la URL de Cloudinary
            validated_data['foto'] = resultado['secure_url']

        # Actualizar los demás campos
        for atributo, valor in validated_data.items():
            setattr(instance, atributo, valor)

        instance.save()

        return instance


class MedicamentosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicamentos
        fields = '__all__'


class RolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Roles
        fields = '__all__'

class UsuariosSerializer(serializers.ModelSerializer):
    # Permite recibir una imagen desde FormData
    foto = serializers.CharField(
        required=False,
        allow_null=True
    )

    class Meta:
        model = Usuarios
        fields = '__all__'

    def to_internal_value(self, data):
        # Copiamos los datos recibidos para poder modificar la foto
        data = data.copy()

        imagen = data.get('foto')

        # Si Angular envía un archivo, lo dejamos pasar directamente
        if imagen and hasattr(imagen, 'read'):
            data.pop('foto')

            datos_validados = super().to_internal_value(data)

            # Agregamos el archivo manualmente para procesarlo en update()
            datos_validados['foto'] = imagen

            return datos_validados

        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        from servicios.cloudinary_service import subir_imagen

        # Obtener la foto enviada
        imagen = validated_data.pop('foto', None)

        # Si se envió una nueva foto, subirla a Cloudinary
        if imagen and hasattr(imagen, 'read'):
            resultado = subir_imagen(
                imagen,
                'geriapp/usuarios'
            )

            # Guardar la URL de Cloudinary
            validated_data['foto'] = resultado['secure_url']

        # Actualizar los demás campos
        for atributo, valor in validated_data.items():
            setattr(instance, atributo, valor)

        instance.save()

        return instance
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

class NotificacionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificaciones
        fields = '__all__'

class NotificacionDestinatarioSerializer(serializers.ModelSerializer):

    class Meta:
        model = NotificacionDestinatario
        fields = '__all__'

    def update(self, instance, validated_data):

        # =====================================================
        # OBTENER NUEVO ESTADO
        # =====================================================

        nueva_leida = validated_data.get(
            'leida',
            instance.leida
        )

        # =====================================================
        # ACTUALIZAR ESTADO
        # =====================================================

        instance.leida = nueva_leida

        # =====================================================
        # ACTUALIZAR FECHA DE LECTURA
        # =====================================================

        if nueva_leida:

            # Solo colocar fecha si todavía no tenía
            if not instance.fecha_lectura:
                instance.fecha_lectura = timezone.now()

        else:

            # Si vuelve a no leída, quitar fecha
            instance.fecha_lectura = None

        # =====================================================
        # ACTUALIZAR OTROS CAMPOS
        # =====================================================

        for atributo, valor in validated_data.items():

            if atributo not in [
                'leida',
                'fecha_lectura'
            ]:

                setattr(
                    instance,
                    atributo,
                    valor
                )

        # =====================================================
        # GUARDAR
        # =====================================================

        instance.save()

        return instance

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

class GrupoMedicacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrupoMedicacion
        fields = '__all__'

class EventosAdversosSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventosAdversos
        fields = '__all__'
        
    def create(self, validated_data):

        evento = EventosAdversos.objects.create(**validated_data)

        if not evento.id_bitacora:
            return evento

        bitacora = evento.id_bitacora

        paciente = bitacora.id_paciente
        cuidador = bitacora.id_usuario

        if not cuidador:
            return evento

        destinatarios = Usuarios.objects.filter(
            id_rol_id__in=[6, 7],
            estado=True
        )

        if not destinatarios.exists():
            return evento

        mensaje = "Se registró un evento adverso."

        if paciente:
            nombre_paciente = f"{paciente.nombre} {paciente.apellido}".strip()
            mensaje = f"Se registró un evento adverso para el paciente {nombre_paciente}."

        notificacion = Notificaciones.objects.create(
            titulo="Evento adverso registrado",
            tipo="EVENTO_ADVERSO",
            mensaje=mensaje,
            enviar_correo=False,
            fecha_hora=timezone.now(),
            estado=True,
            id_paciente=paciente,
            id_usuario=cuidador
        )

        for usuario in destinatarios:
            NotificacionDestinatario.objects.create(
                leida=False,
                fecha_lectura=None,
                id_notificacion=notificacion,
                id_usuario=usuario
            )

        return evento   
        


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

class ElementosPacienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ElementosPaciente
        fields = '__all__'

class RecuperacionPasswordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecuperacionPassword
        fields = '__all__'

class FcmTokensSerializer(serializers.ModelSerializer):

    class Meta:
        model = FcmTokens
        fields = '__all__'

class CamasSerializer(serializers.ModelSerializer):

    class Meta:
        model = Camas
        fields = '__all__'

class HabitacionesSerializer(serializers.ModelSerializer):

    class Meta:
        model = Habitaciones
        fields = '__all__'

class FundacionesSerializer(serializers.ModelSerializer):

    class Meta:
        model = Fundaciones
        fields = '__all__'

class SedesSerializer(serializers.ModelSerializer):

    class Meta:
        model = Sedes
        fields = '__all__'

class CamarasSerializer(serializers.ModelSerializer):

    class Meta:
        model = Camaras
        fields = '__all__'

class TiposEventoIaSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = TiposEventoIa
        fields = '__all__'

class EventosIaSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = EventosIa
        fields = '__all__'

class EvidenciasIaSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = EvidenciasIa
        fields = '__all__'

class AsignacionHabitacionSerializer(serializers.ModelSerializer):

    class Meta:
        model = AsignacionHabitacion
        fields = '__all__'

class FormulacionMedicamentosSerializer(serializers.ModelSerializer):

    class Meta:
        model = FormulacionMedicamentos
        fields = '__all__'
        

class CitasSerializer(serializers.ModelSerializer):

    class Meta:
        model = Citas
        fields = '__all__'

    def create(self, validated_data):


        cita = Citas.objects.create(**validated_data)

        # VERIFICAR QUE LA CITA TENGA PACIENTE

        if not cita.id_paciente:
            return cita

        # BUSCAR EL CUIDADOR ACTUAL DEL PACIENTE

        asignacion = (
            AsignacionPacienteCuidador.objects
            .filter(
                id_paciente=cita.id_paciente,
                estado__iexact="Activo"
            )
            .order_by("-fecha_inicio")
            .first()
        )


        if not asignacion or not asignacion.id_usuario:
            return cita

        # CREAR LA NOTIFICACIÓN

        nombre_paciente = (
            f"{cita.id_paciente.nombre} "
            f"{cita.id_paciente.apellido}"
        ).strip()

        mensaje = (
            f"El paciente {nombre_paciente} tiene una nueva cita "
            f"el {cita.fecha} a las {cita.hora}."
        )

        if cita.lugar:
            mensaje += f" Lugar: {cita.lugar}."

        if cita.motivo:
            mensaje += f" Motivo: {cita.motivo}."

        notificacion = Notificaciones.objects.create(
            titulo="Nueva cita",
            tipo="CITA",
            mensaje=mensaje,
            enviar_correo=False,
            fecha_hora=timezone.now(),
            estado=True,
            id_paciente=cita.id_paciente,
            id_usuario=asignacion.id_usuario
        )

        # CREAR EL DESTINATARIO

        NotificacionDestinatario.objects.create(
            leida=False,
            fecha_lectura=None,
            id_notificacion=notificacion,
            id_usuario=asignacion.id_usuario
        )

        return cita


# Esta parte permite registrar un usuario desde la aplicación,
# encripta la contraseña y establece el usuario como activo.
class RegistroUsuarioSerializer(serializers.ModelSerializer):
    # Recibe el archivo de imagen enviado desde Insomnia o Angular
    foto = serializers.FileField(
        required=False,
        allow_null=True,
        write_only=True
    )

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
            'foto',
        ]
        extra_kwargs = {
            'contrasena': {'write_only': True}
        }

    def create(self, validated_data):
        from django.contrib.auth.hashers import make_password
        from servicios.cloudinary_service import subir_imagen

        # Sacar la imagen de los datos antes de crear el usuario
        imagen = validated_data.pop('foto', None)

        # Encriptar la contraseña
        validated_data['contrasena'] = make_password(
            validated_data['contrasena']
        )

        # Datos automáticos del usuario
        validated_data['estado'] = True
        validated_data['fecha_ingreso'] = timezone.now()

        # Si se envió una imagen, subirla a Cloudinary
        if imagen:
            resultado = subir_imagen(
                imagen,
                'geriapp/usuarios'
            )

            # Guardar solamente la URL de Cloudinary
            validated_data['foto'] = resultado['secure_url']

        # Crear el usuario
        usuario = Usuarios.objects.create(
            **validated_data
        )

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

