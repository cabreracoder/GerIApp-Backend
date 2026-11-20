import math
import re

from django.core.serializers import python
from rest_framework import serializers
from django.utils import timezone
from .asignaciones_vigencia import (
    asegurar_aware_colombia,
    filtrar_asignaciones_vigentes,
)
from .models import SolicitudCita

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
    SeguimientoAdministracionMedicamento,
    CierreTurno,
    ConfiguracionControlesPeriodicos,
    ControlesPeriodicosBitacora,
    RegistrosFaciales,
    DocumentosHistoriaClinica,
    EstadoPosturaPaciente,
    SolicitudCita,
)

class ImagenFacialSerializer(serializers.Serializer):

    imagen = serializers.ImageField(
        required=True,
        allow_empty_file=False
    )

class DocumentosHistoriaClinicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentosHistoriaClinica
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        ruta_archivo = (
            getattr(instance.archivo, 'name', '')
            if instance.archivo
            else ''
        )
        if ruta_archivo.startswith(('http://', 'https://')):
            data['archivo'] = ruta_archivo
        return data

class RegistrosFacialesSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistrosFaciales
        fields = [
            'id_registro_facial',
            'id_paciente',
            'url_fotografia',
            'public_id',
            'tipo_fotografia',
            'activo',
            'fecha_registro',
            'fecha_actualizacion'
        ]

        read_only_fields = [
            'id_registro_facial',
            'fecha_registro',
            'fecha_actualizacion'
        ]


class PacientesSerializer(serializers.ModelSerializer):
    # Permite recibir una imagen desde FormData
    foto = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True
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

    # VALIDAR HABITACIÓN Y CAMA DEL PACIENTE

    def validate(self, attrs):

        from .models import Habitaciones, Camas, Pacientes, Sedes

        # Obtener la sede del usuario autenticado
        request = self.context.get('request')

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError({
                'id_sede': 'No se pudo verificar la sede del usuario.'
            })

        sede = getattr(request.user, 'id_sede', None)

        if sede is None:
            raise serializers.ValidationError({
                'id_sede': 'Tu usuario no tiene una sede asignada.'
            })

        # Forzar la sede autorizada, ignorando la enviada por Angular
        attrs['id_sede'] = sede


        # Validar sede obligatoria
        if sede is None:
            raise serializers.ValidationError({
                'id_sede': 'Debes seleccionar una sede.'
            })

        # Validar que la sede exista
        sede_actual = Sedes.objects.filter(
            id_sede=sede.pk
        ).first()

        if not sede_actual:
            raise serializers.ValidationError({
                'id_sede': 'La sede seleccionada no existe.'
            })

        # Validar que esté activa
        if not sede_actual.estado:
            raise serializers.ValidationError({
                'id_sede': 'La sede seleccionada está inactiva.'
            })

        # Mantener habitación y cama actuales al editar
        habitacion_id = attrs.get(
            'habitacion',
            self.instance.habitacion if self.instance else None
        )

        cama_id = attrs.get(
            'cama',
            self.instance.cama if self.instance else None
        )

        # Validar que se seleccionen habitación y cama
        if habitacion_id is None or cama_id is None:
            raise serializers.ValidationError({
                'ubicacion': 'Debes seleccionar una habitación y una cama.'
            })

        # Buscar habitación
        habitacion = Habitaciones.objects.filter(
            id_habitacion=habitacion_id
        ).first()

        if not habitacion:
            raise serializers.ValidationError({
                'habitacion': 'La habitación seleccionada no existe.'
            })

        # Validar habitación activa
        if not habitacion.estado:
            raise serializers.ValidationError({
                'habitacion': 'Esta habitación está inactiva.'
            })

        # Validar que la habitación pertenezca a la sede
        if habitacion.id_sede_id != sede_actual.id_sede:
            raise serializers.ValidationError({
                'habitacion': 'La habitación no pertenece a la sede seleccionada.'
            })

        # Buscar cama
        cama = Camas.objects.filter(
            id_cama=cama_id
        ).first()

        if not cama:
            raise serializers.ValidationError({
                'cama': 'La cama seleccionada no existe.'
            })

        # Validar cama activa
        if not cama.estado:
            raise serializers.ValidationError({
                'cama': 'Esta cama está inactiva.'
            })

        # Validar que la cama pertenezca a la habitación
        if cama.id_habitacion_id != habitacion.id_habitacion:
            raise serializers.ValidationError({
                'cama': 'La cama no pertenece a la habitación seleccionada.'
            })

        # Verificar que la cama no esté ocupada
        ocupantes = Pacientes.objects.filter(
            habitacion=habitacion_id,
            cama=cama_id
        )

        # Excluir al mismo paciente cuando se edita
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
        exclude = ['contrasena']

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

    # Campos que pueden recibir archivos
    CAMPOS_ARCHIVOS = (
        'cedula',
        'tarjeta_profesional',
        'antecedentes',
        'hoja_de_vida',
    )

    def to_internal_value(self, data):
        # Copiar los datos recibidos desde FormData
        data = data.copy()

        archivos = {}

        # Separar los archivos para procesarlos antes de guardarlos
        for campo in self.CAMPOS_ARCHIVOS:
            archivo = data.get(campo)

            if archivo and hasattr(archivo, 'read'):
                archivos[campo] = archivo
                data.pop(campo)

        # Validar los demás campos normalmente
        datos_validados = super().to_internal_value(data)

        # Agregar nuevamente los archivos validados
        datos_validados.update(archivos)

        return datos_validados

    def create(self, validated_data):
        from servicios.cloudinary_service import subir_documento

        # Subir los archivos seleccionados a Cloudinary
        for campo in self.CAMPOS_ARCHIVOS:
            archivo = validated_data.get(campo)

            if archivo and hasattr(archivo, 'read'):
                resultado = subir_documento(
                    archivo,
                    'geriapp/documentos'
                )

                # Guardar la URL, no el archivo temporal
                validated_data[campo] = resultado['secure_url']

        return Documentos.objects.create(**validated_data)

    def update(self, instance, validated_data):
        from servicios.cloudinary_service import subir_documento

        # Actualizar únicamente los documentos que se envíen
        for campo in self.CAMPOS_ARCHIVOS:
            archivo = validated_data.get(campo)

            if archivo and hasattr(archivo, 'read'):
                resultado = subir_documento(
                    archivo,
                    'geriapp/documentos'
                )

                validated_data[campo] = resultado['secure_url']

        # Guardar los cambios sin borrar documentos omitidos
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)

        instance.save()

        return instance



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

        # OBTENER NUEVO ESTADO

        nueva_leida = validated_data.get(
            'leida',
            instance.leida
        )

        # ACTUALIZAR ESTADO

        instance.leida = nueva_leida

        # ACTUALIZAR FECHA DE LECTURA

        if nueva_leida:

            # Solo colocar fecha si todavía no tenía
            if not instance.fecha_lectura:
                instance.fecha_lectura = timezone.now()

        else:

            # Si vuelve a no leída, quitar fecha
            instance.fecha_lectura = None

        # ACTUALIZAR OTROS CAMPOS

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

        # GUARDAR

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


MAPA_SIGNOS_RANGOS = (
    ("presion_sistolica", "sistolica_min", "sistolica_max", "Presión sistólica", "mmHg"),
    ("presion_diastolica", "diastolica_min", "diastolica_max", "Presión diastólica", "mmHg"),
    ("frecuencia_cardiaca", "fc_min", "fc_max", "Frecuencia cardíaca", "lpm"),
    ("frecuencia_respiratoria", "fr_min", "fr_max", "Frecuencia respiratoria", "rpm"),
    ("temperatura", "temp_min", "temp_max", "Temperatura", "°C"),
    ("saturacion_oxigeno", "sat_min", "sat_max", "Saturación de oxígeno", "%"),
)


def _parse_float_seguro(valor):
    """Convierte valores CharField de signos vitales a float sin fallar ante textos o vacíos."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        num = float(valor)
        return None if (math.isnan(num) or math.isinf(num)) else num

    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return None

    try:
        num = float(texto)
        return None if (math.isnan(num) or math.isinf(num)) else num
    except ValueError:
        pass

    match = re.search(r"[-+]?\d+(?:\.\d+)?", texto)
    if match:
        try:
            num = float(match.group(0))
            return None if (math.isnan(num) or math.isinf(num)) else num
        except ValueError:
            return None

    return None


def evaluar_rangos_signos_vitales(signo):
    """
    Compara los signos vitales contra HistoriaClinicas.rangos_vitales_json del paciente.
    Retorna el mensaje de alerta si algún valor está fuera de rango, o None en caso contrario.
    """
    bitacora = getattr(signo, "id_bitacora", None)
    paciente = getattr(bitacora, "id_paciente", None) if bitacora else None
    if not paciente:
        return None

    historia = (
        HistoriaClinicas.objects
        .filter(id_paciente=paciente, rangos_vitales_json__isnull=False)
        .order_by("-id_historia_clinica")
        .first()
    )
    rangos = historia.rangos_vitales_json if historia else None
    if not isinstance(rangos, dict) or not rangos:
        return None

    desviaciones = []
    for campo_modelo, key_min, key_max, etiqueta, unidad in MAPA_SIGNOS_RANGOS:
        valor_num = _parse_float_seguro(getattr(signo, campo_modelo, None))
        if valor_num is None:
            continue

        min_val = _parse_float_seguro(rangos.get(key_min))
        max_val = _parse_float_seguro(rangos.get(key_max))

        if min_val is not None and valor_num < min_val:
            desviaciones.append(
                f"{etiqueta} baja ({valor_num:g} {unidad}; mínimo esperado: {min_val:g} {unidad})"
            )
        elif max_val is not None and valor_num > max_val:
            desviaciones.append(
                f"{etiqueta} elevada ({valor_num:g} {unidad}; máximo esperado: {max_val:g} {unidad})"
            )

    if not desviaciones:
        return None

    return (
        "ALERTA GERIÁTRICA - Signos fuera de rango personalizado: "
        + "; ".join(desviaciones)
        + "."
    )


class SignosVitalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignosVitales
        fields = '__all__'

    def create(self, validated_data):
        signo = SignosVitales(**validated_data)
        alerta = evaluar_rangos_signos_vitales(signo)
        if alerta:
            signo.alerta_generada = alerta
        signo.save()
        return signo


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

    def validate(self, attrs):
        fecha_inicio = attrs.get(
            'fecha_inicio',
            getattr(self.instance, 'fecha_inicio', None)
        )
        fecha_fin = attrs.get(
            'fecha_fin',
            getattr(self.instance, 'fecha_fin', None)
        )

        if fecha_inicio and fecha_fin:
            inicio_cmp = asegurar_aware_colombia(fecha_inicio)
            fin_cmp = asegurar_aware_colombia(fecha_fin)

            if inicio_cmp > fin_cmp:
                raise serializers.ValidationError({
                    'fecha_fin': (
                        'La fecha de fin debe ser mayor o igual '
                        'a la fecha de inicio.'
                    )
                })

        return attrs


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


class EstadoPosturaPacienteSerializer(serializers.ModelSerializer):

    # Permite reutilizar el paciente aunque ya tenga
    # un registro en estado_postura_paciente.
    id_paciente = serializers.PrimaryKeyRelatedField(
        queryset=Pacientes.objects.all(),
        validators=[]
    )

    class Meta:
        model = EstadoPosturaPaciente

        fields = [
            'id_estado_postura',
            'id_paciente',
            'id_camara',
            'id_habitacion',
            'postura_actual',
            'confianza',
            'fecha_actualizacion',
        ]

        read_only_fields = [
            'id_estado_postura',
            'fecha_actualizacion',
        ]

        
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


class SeguimientoAdministracionMedicamentoSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = SeguimientoAdministracionMedicamento
        fields = '__all__'

        read_only_fields = (
            'id_seguimiento',
            'estado',
            'motivo_no_administracion',
            'fecha_hora_registro',
            'id_usuario',
            'id_aplicacion'
        )


class CierreTurnoSerializer(serializers.ModelSerializer):

    class Meta:
        model = CierreTurno
        fields = '__all__'

class ConfiguracionControlesPeriodicosSerializer(serializers.ModelSerializer):

    class Meta:
        model = ConfiguracionControlesPeriodicos
        fields = '__all__'

class ControlesPeriodicosBitacoraSerializer(serializers.ModelSerializer):

    class Meta:
        model = ControlesPeriodicosBitacora
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
            filtrar_asignaciones_vigentes()
            .filter(id_paciente=cita.id_paciente)
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

        from core.notificaciones_utils import enviar_notificacion_fcm

        enviar_notificacion_fcm(
            notificacion,
            asignacion.id_usuario
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

class SolicitudCitaSerializer(serializers.ModelSerializer):

    class Meta:
        model = SolicitudCita
        fields = '__all__'
        read_only_fields = [
            'id_solicitud',
            'estado',
            'fecha_creacion',
            'fecha_actualizacion',
            'resultado_automatizacion',
            'id_cita',
        ]

    def validate(self, attrs):
        paciente = attrs.get('id_paciente')
        familiar = attrs.get('id_familiar_responsable')

        if paciente and familiar:
            if familiar.id_paciente_id != paciente.id_paciente:
                raise serializers.ValidationError({
                    'id_familiar_responsable': (
                        'El familiar responsable no está '
                        'relacionado con el paciente seleccionado.'
                    )
                })

        return attrs
    
    def create(self, validated_data):
        ahora = timezone.now()

        validated_data['fecha_creacion'] = ahora
        validated_data['fecha_actualizacion'] = ahora

        return super().create(validated_data)

class SolicitudCitaActualizacionSerializer(serializers.ModelSerializer):

    class Meta:
        model = SolicitudCita
        fields = [
            'estado',
            'observaciones',
            'resultado_automatizacion',
        ]

    def validate_estado(self, value):
        estados_validos = [
            estado[0] for estado in SolicitudCita.ESTADOS
        ]

        if value not in estados_validos:
            raise serializers.ValidationError(
                'El estado proporcionado no es válido.'
            )

        return value

    def update(self, instance, validated_data):
        validated_data['fecha_actualizacion'] = timezone.now()

        return super().update(instance, validated_data)