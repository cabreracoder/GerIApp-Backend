from django.core.serializers import python
from django.db import models


class Actividades(models.Model):
    id_actividad = models.AutoField(primary_key=True)
    id_bitacora = models.ForeignKey('Bitacora', models.DO_NOTHING, db_column='id_bitacora', blank=True, null=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.CharField()
    fecha_hora = models.DateTimeField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'actividades'


class AplicacionMedicamento(models.Model):
    id_aplicacion = models.AutoField(primary_key=True)
    id_medicamento_medicamento = models.IntegerField(blank=True, null=True)
    id_inventario = models.ForeignKey('Inventario', models.DO_NOTHING, db_column='id_inventario', blank=True, null=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha_hora = models.DateTimeField()
    dosis_administrada = models.CharField()
    via_administracion = models.CharField()
    estado = models.BooleanField()
    observacion = models.CharField()

    class Meta:
        managed = False
        db_table = 'aplicacion_medicamento'


class AplicacionMedicamentos(models.Model):
    id_aplicacion = models.AutoField(primary_key=True)
    fecha = models.CharField()
    hora = models.CharField()
    estado = models.CharField()
    observaciones = models.CharField()
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'aplicacion_medicamentos'


class AsignacionPacienteCuidador(models.Model):
    id_asignacion = models.AutoField(primary_key=True)
    id_paciente = models.ForeignKey('Pacientes', models.DO_NOTHING, db_column='id_paciente', blank=True, null=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    estado = models.CharField()
    observaciones = models.CharField()

    class Meta:
        managed = False
        db_table = 'asignacion_paciente_cuidador'


class AsignacionTurnoUsuario(models.Model):
    id_asignacion_turno_usuario = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    id_turno = models.ForeignKey('Turnos', models.DO_NOTHING, db_column='id_turno', blank=True, null=True)
    fecha = models.DateField()
    estado = models.CharField()

    class Meta:
        managed = False
        db_table = 'asignacion_turno_usuario'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class Bitacora(models.Model):
    id_bitacora = models.AutoField(primary_key=True)
    estado = models.BooleanField()
    tipo_registro = models.CharField()
    descripcion = models.CharField()
    fecha_hora = models.DateTimeField()
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    id_paciente = models.ForeignKey('Pacientes', models.DO_NOTHING, db_column='id_paciente', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'bitacora'


class DetalleEntregaInsumos(models.Model):
    id_detalle_entrega_insumos = models.AutoField(primary_key=True)
    id_insumo = models.ForeignKey('Insumos', models.DO_NOTHING, db_column='id_insumo', blank=True, null=True)
    cantidad = models.IntegerField()
    fecha_vencimiento = models.DateField()
    id_entrega_insumo = models.ForeignKey('EntregaInsumo', models.DO_NOTHING, db_column='id_entrega_insumo', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detalle_entrega_insumos'


class DetalleEntregaMedicamento(models.Model):
    id_detalle_entrega_medicamento = models.AutoField(primary_key=True)
    id_entrega_medica = models.ForeignKey('EntregaMedica', models.DO_NOTHING, db_column='id_entrega_medica', blank=True, null=True)
    id_medicamentos = models.ForeignKey('Medicamentos', models.DO_NOTHING, db_column='id_medicamentos', blank=True, null=True)
    cantidad = models.IntegerField()
    fecha_vencimiento = models.DateField()

    class Meta:
        managed = False
        db_table = 'detalle_entrega_medicamento'


class Diagnosticos(models.Model):
    id_diagnostico = models.AutoField(primary_key=True)
    id_historia_clinica = models.ForeignKey('HistoriaClinicas', models.DO_NOTHING, db_column='id_historia_clinica', blank=True, null=True)
    id_enfermedad = models.ForeignKey('Enfermedades', models.DO_NOTHING, db_column='id_enfermedad', blank=True, null=True)
    descripcion = models.CharField()
    estado = models.BooleanField()
    fecha_diagnostico = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'diagnosticos'


class DisponibilidadUsuario(models.Model):
    id_disponibilidad = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey('Usuarios', models.CASCADE, db_column='id_usuario')
    dia_semana = models.CharField(max_length=15)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        managed = False
        db_table = 'disponibilidad_usuario'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'



class Enfermedades(models.Model):
    id_enfermedad = models.AutoField(primary_key=True)
    nombre = models.CharField()
    descripcion = models.CharField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'enfermedades'


class EntregaInsumo(models.Model):
    id_entrega_insumo = models.AutoField(primary_key=True)
    fehca_entrega = models.DateTimeField()
    observaciones = models.CharField()
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'entrega_insumo'


class EntregaMedica(models.Model):
    id_entrega_medica = models.AutoField(primary_key=True)
    id_paciente = models.ForeignKey('Pacientes', models.DO_NOTHING, db_column='id_paciente', blank=True, null=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha_entrega = models.DateTimeField()
    observaciones = models.CharField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'entrega_medica'


class EventosAdversos(models.Model):
    id_evento_adverso = models.AutoField(primary_key=True)
    id_bitacora = models.ForeignKey(Bitacora, models.DO_NOTHING, db_column='id_bitacora', blank=True, null=True)
    id_evento = models.CharField(blank=True, null=True)
    id_tipo_emergencia = models.ForeignKey('TipoEmergencia', models.DO_NOTHING, db_column='id_tipo_emergencia', blank=True, null=True)
    fecha_hora = models.DateTimeField()
    descripcion = models.CharField()
    acciones_realizadas = models.CharField()
    estado = models.CharField()

    class Meta:
        managed = False
        db_table = 'eventos_adversos'


class FamiliarResponsable(models.Model):
    id_familiar_responsable = models.AutoField(primary_key=True)
    id_paciente = models.ForeignKey('Pacientes', models.CASCADE, db_column='id_paciente')
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    parentesco = models.CharField(max_length=50)
    telefono_uno = models.CharField(max_length=20)
    telefono_dos = models.CharField(max_length=20, blank=True, null=True)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    correo = models.CharField(max_length=150, blank=True, null=True)
    municipio = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'familiar_responsable'


class HistoriaClinicas(models.Model):
    id_historia_clinica = models.AutoField(primary_key=True)
    fecha_apertura = models.DateTimeField()
    antecedentes = models.CharField()
    alergias = models.CharField()
    observaciones = models.CharField()
    estado = models.BooleanField()
    id_paciente = models.ForeignKey('Pacientes', models.DO_NOTHING, db_column='id_paciente', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'historia_clinicas'


class ImagenesEventoAdverso(models.Model):
    id_imagen = models.AutoField(primary_key=True)
    id_evento_adverso = models.ForeignKey(EventosAdversos, models.DO_NOTHING, db_column='id_evento_adverso', blank=True, null=True)
    url_imagen = models.CharField()
    descripcion = models.CharField()
    fecha_subida = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'imagenes_evento_adverso'


class Insumos(models.Model):
    id_insumo = models.AutoField(primary_key=True)
    id_tipo_insumo = models.ForeignKey('TipoInsumo', models.DO_NOTHING, db_column='id_tipo_insumo', blank=True, null=True)
    nombre = models.CharField()
    descripcion = models.CharField()
    unidad_medida = models.CharField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'insumos'


class Inventario(models.Model):
    id_inventario = models.AutoField(primary_key=True)
    id_paciente = models.ForeignKey('Pacientes', models.DO_NOTHING, db_column='id_paciente', blank=True, null=True)
    id_medicamentos = models.ForeignKey('Medicamentos', models.DO_NOTHING, db_column='id_medicamentos', blank=True, null=True)
    cantidad_actual = models.IntegerField()
    cantidad_minima = models.IntegerField()
    fecha_ultimo_ingreso = models.DateTimeField()
    fecha_vencimiento = models.DateField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'inventario'


class Medicamentos(models.Model):
    id_medicamentos = models.AutoField(primary_key=True)
    nombre = models.CharField()
    vencimiento = models.DateField()
    descripcion = models.CharField()
    principio_activo = models.CharField()
    concentracion = models.CharField()
    presentacion = models.CharField()
    estado = models.BooleanField()
    unidad_medida = models.CharField()

    class Meta:
        managed = False
        db_table = 'medicamentos'


class MovimientoInsumo(models.Model):
    id_movimiento_insumo = models.AutoField(primary_key=True)
    id_insumo = models.ForeignKey(Insumos, models.DO_NOTHING, db_column='id_insumo', blank=True, null=True)
    id_detalle_entrega_insumos = models.ForeignKey(DetalleEntregaInsumos, models.DO_NOTHING, db_column='id_detalle_entrega_insumos', blank=True, null=True)
    tipo_insumo = models.CharField()
    cantidad = models.IntegerField()
    fecha_movimiento = models.DateTimeField()
    observacion = models.CharField()

    class Meta:
        managed = False
        db_table = 'movimiento_insumo'


class MovimientoMedicamento(models.Model):
    id_movimiento = models.AutoField(primary_key=True)
    id_inventario = models.ForeignKey(Inventario, models.DO_NOTHING, db_column='id_inventario', blank=True, null=True)
    id_detalle_entrega_medicamento = models.ForeignKey(DetalleEntregaMedicamento, models.DO_NOTHING, db_column='id_detalle_entrega_medicamento', blank=True, null=True)
    cantidad = models.IntegerField()
    fecha_movimiento = models.DateTimeField()
    observaciones = models.CharField()

    class Meta:
        managed = False
        db_table = 'movimiento_medicamento'


class Pacientes(models.Model):
    id_paciente = models.AutoField(primary_key=True)
    nombre = models.CharField()
    apellido = models.CharField()
    eps = models.CharField()
    sede = models.CharField()
    fecha_ingreso = models.DateTimeField()
    habitacion = models.IntegerField()
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    tipo_documento = models.CharField()
    numero_documento = models.CharField()
    fecha_nacimiento = models.DateField()
    genero = models.CharField()
    grupo_sanguineo = models.CharField(max_length=5, blank=True, null=True)
    rh = models.CharField(max_length=5, blank=True, null=True)
    cama = models.IntegerField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'pacientes'


class PerfilProfesional(models.Model):
    id_perfil_profesional = models.AutoField(primary_key=True)
    id_usuario = models.OneToOneField('Usuarios', models.CASCADE, db_column='id_usuario')
    especialidad = models.CharField(max_length=100, blank=True, null=True)
    licencia = models.CharField(max_length=100, blank=True, null=True)
    experiencia = models.IntegerField(blank=True, null=True)
    institucion = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'perfil_profesional'


class Permisos(models.Model):
    id_permisos = models.AutoField(primary_key=True)
    nombre = models.CharField()
    descripcion = models.CharField()

    class Meta:
        managed = False
        db_table = 'permisos'


class PermisosRol(models.Model):
    id_permisos_rol = models.AutoField(primary_key=True)
    id_permisos = models.ForeignKey(Permisos, models.DO_NOTHING, db_column='id_permisos', blank=True, null=True)
    id_rol = models.ForeignKey('Roles', models.DO_NOTHING, db_column='id_rol', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'permisos_rol'


class Roles(models.Model):
    id_rol = models.AutoField(primary_key=True)
    nombre = models.CharField()
    descripcion = models.CharField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'roles'

class Usuarios(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    id_rol = models.ForeignKey(
        'Roles',
        models.DO_NOTHING,
        db_column='id_rol',
        blank=True,
        null=True
    )
    tipo_documento = models.CharField()
    numero_documento = models.CharField()
    nombres = models.CharField()
    apellidos = models.CharField()
    correo = models.CharField()
    telefono = models.CharField(blank=True, null=True)
    fecha_ingreso = models.DateTimeField()
    estado = models.BooleanField()
    contrasena = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'usuarios'


class Documentos(models.Model):
    id_documento = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        'Usuarios',
        models.DO_NOTHING,
        db_column='id_usuario'
    )
    cedula = models.CharField(max_length=500, blank=True, null=True)
    tarjeta_profesional = models.CharField(max_length=500, blank=True, null=True)
    antecedentes = models.CharField(max_length=500, blank=True, null=True)
    hoja_de_vida = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'documentos'



class SignosVitales(models.Model):
    id_signos_vitales = models.AutoField(primary_key=True)
    id_bitacora = models.ForeignKey(Bitacora, models.DO_NOTHING, db_column='id_bitacora', blank=True, null=True)
    temperatura = models.CharField()
    presion_sistolica = models.CharField()
    presion_diastolica = models.CharField()
    frecuencia_cardiaca = models.CharField()
    frecuencia_respiratoria = models.CharField()
    saturacion_oxigeno = models.CharField()
    peso = models.CharField()
    fecha_hora = models.DateTimeField()
    observaciones = models.CharField()

    class Meta:
        managed = False
        db_table = 'signos_vitales'


class TipoEmergencia(models.Model):
    id_tipo_emergencia = models.AutoField(primary_key=True)
    nombre = models.CharField()
    descripcion = models.CharField()
    nivel = models.CharField()
    estado = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'tipo_emergencia'


class TipoEvento(models.Model):
    id_tipo_evento = models.AutoField(primary_key=True)
    nombre = models.CharField()
    descripcion = models.CharField()
    estado = models.CharField()

    class Meta:
        managed = False
        db_table = 'tipo_evento'


class TipoInsumo(models.Model):
    id_tipo_insumo = models.AutoField(primary_key=True)
    nombre = models.CharField()
    descripcion = models.CharField()
    estado = models.CharField()

    class Meta:
        managed = False
        db_table = 'tipo_insumo'


class TratamientoMedicamento(models.Model):
    id_tratamiento_medicamento = models.AutoField(primary_key=True)
    id_tratamiento = models.ForeignKey('Tratamientos', models.DO_NOTHING, db_column='id_tratamiento', blank=True, null=True)
    id_medicamentos = models.ForeignKey(Medicamentos, models.DO_NOTHING, db_column='id_medicamentos', blank=True, null=True)
    dosis = models.IntegerField()
    frecuencia = models.CharField()
    via_administracion = models.CharField()
    duracion = models.CharField()
    cantidad_prescrita = models.CharField()
    observaciones = models.CharField()
    estado = models.CharField()

    class Meta:
        managed = False
        db_table = 'tratamiento_medicamento'


class Tratamientos(models.Model):
    id_tratamiento = models.AutoField(primary_key=True)
    id_diagnostico = models.ForeignKey(Diagnosticos, models.DO_NOTHING, db_column='id_diagnostico', blank=True, null=True)
    fecha_inicio = models.TimeField()
    fecha_fin = models.TimeField()
    indicaciones = models.CharField()
    estado = models.CharField()

    class Meta:
        managed = False
        db_table = 'tratamientos'


class Turnos(models.Model):
    id_turno = models.AutoField(primary_key=True)
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(blank=True, null=True)
    estado = models.BooleanField()
    nombre = models.CharField()
    descripcion = models.CharField()

    class Meta:
        managed = False
        db_table = 'turnos'


