from django.core.serializers import python
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework.routers import DefaultRouter

# ==============================
# ViewSets principales
# ==============================
from .views import (
    DiagnosticosViewSet,
    PacientesViewSet,
    MedicamentosViewSet,
    RolesViewSet,
    TratamientoViewSet,
    UsuariosViewSet,
    HistoriaClinicasViewSet,
    EnfermedadesViewSet,
    TratamientoMedicamentoViewSet,
    InventarioViewSet,
    EntregaMedicaViewSet,
    DetalleEntregaMedicamentoViewSet,
    MovimientoMedicamentoViewSet,
    AplicacionMedicamentoViewSet,
    GrupoMedicacionViewSet,
    FormulacionMedicamentosViewSet,
)

# ==============================
# Insumos
# ==============================
from .views import (
    TipoInsumoViewSet,
    InsumosViewSet,
    DetalleEntregaInsumoViewSet,
    EntregaInsumoViewSet,
    MovimientoInsumoViewSet,
)

# ==============================
# Bitácora y actividades
# ==============================
from .views import (
    BitacoraViewSet,
    ActividadesViewSet,
    SignosVitalesViewSet,
)

# ==============================
# Eventos y emergencias
# ==============================
from .views import (
    TipoEventoViewSet,
    TipoEmergenciaViewSet,
    EventosAdversosViewSet,
    ImagenesEventoAdversoViewSet,
)

# ==============================
# Asignaciones, turnos y permisos
# ==============================
from .views import (
    AsignacionPacienteCuidadorViewSet,
    TurnosViewSet,
    AsignacionTurnoUsuarioViewSet,
    PermisosViewSet,
    PermisosRolViewSet,
    AsignacionHabitacionViewSet,
)

# ==============================
# Información de usuarios
# ==============================
from .views import (
    FamiliarResponsableViewSet,
    PerfilProfesionalViewSet,
    DisponibilidadUsuarioViewSet,
    DocumentosViewSet,
)

# ==============================
# Cuidados y pacientes
# ==============================
from .views import (
    RecomendacionesViewSet,
    CuidadosEnfermeriaViewSet,
    ElementosPacienteViewSet,
    CitasViewSet,
)

# ==============================
# Notificaciones y recuperación
# ==============================
from .views import (
    RecuperacionPasswordViewSet,
    NotificacionesViewSet,
    NotificacionDestinatarioViewSet,
    FcmTokensViewSet,
)

# ==============================
# Autenticación
# ==============================
from .views import (
    registro_usuario,
    login_usuario,
    cambiar_contrasena,
    recuperar_password,
    verificar_codigo,
    cambiar_password_recuperacion,
    login_google,
)

# ==============================
# Cloudinary
# ==============================
from .views import (
    SubirImagenCloudinaryView,
)

# ==============================
# IA - Habitaciones y cámaras
# ==============================
from .views import (
    FundacionesViewSet,
    SedesViewSet,
    HabitacionesViewSet,
    CamasViewSet,
    AsignacionHabitacionViewSet,
    CamarasViewSet,
    TiposEventoIaViewSet,
    EventosIaViewSet,
    EvidenciasIaViewSet,
)

# ==============================
# Asignaciones, turnos y permisos
# ==============================
from .views import (
    AsignacionPacienteCuidadorViewSet,
    TurnosViewSet,
    AsignacionTurnoUsuarioViewSet,
    PermisosViewSet,
    PermisosRolViewSet,
)

# ==============================
# IA - Habitaciones y cámaras
# ==============================
from .views import (
    FundacionesViewSet,
    SedesViewSet,
    HabitacionesViewSet,
    CamasViewSet,
    AsignacionHabitacionViewSet,
    CamarasViewSet,
    TiposEventoIaViewSet,
    EventosIaViewSet,
    EvidenciasIaViewSet,
)

router = DefaultRouter()

router.register(r'pacientes', PacientesViewSet)

router.register(r'medicamentos', MedicamentosViewSet)

router.register(r'roles', RolesViewSet)

router.register(r'usuarios', UsuariosViewSet)

router.register(r'documentos', DocumentosViewSet)

router.register(r'historia_clinicas', HistoriaClinicasViewSet)

router.register(r'enfermedades', EnfermedadesViewSet)

router.register(r'diagnosticos', DiagnosticosViewSet)

router.register(r'tratamientos', TratamientoViewSet)

router.register(r'tratamiento_medicamento', TratamientoMedicamentoViewSet)

router.register(r'inventario', InventarioViewSet)

router.register(r'entrega_medica', EntregaMedicaViewSet)

router.register(r'detalle_entrega_medicamento', DetalleEntregaMedicamentoViewSet)

router.register(r'movimiento_medicamento', MovimientoMedicamentoViewSet)

router.register(r'aplicacion_medicamento', AplicacionMedicamentoViewSet)

router.register(r'tipo_insumo', TipoInsumoViewSet)

router.register(r'insumos', InsumosViewSet)

router.register(r'detalle_entrega_insumo', DetalleEntregaInsumoViewSet)

router.register(r'entrega_insumo', EntregaInsumoViewSet)

router.register(r'movimiento_insumo', MovimientoInsumoViewSet)

router.register(r'bitacora', BitacoraViewSet)

router.register(r'actividades', ActividadesViewSet)

router.register(r'signos_vitales', SignosVitalesViewSet)

router.register(r'tipo_evento', TipoEventoViewSet)

router.register(r'tipo_emergencia', TipoEmergenciaViewSet)

router.register(r'eventos_adversos', EventosAdversosViewSet)

router.register(r'imagenes_evento_adverso', ImagenesEventoAdversoViewSet)

router.register(r'asignacion_paciente_cuidador', AsignacionPacienteCuidadorViewSet)

router.register(r'turnos', TurnosViewSet)

router.register(r'asignacion_turno_usuario', AsignacionTurnoUsuarioViewSet)

router.register(r'permisos', PermisosViewSet)

router.register(r'permisos_rol', PermisosRolViewSet)

router.register(r'familiar_responsable', FamiliarResponsableViewSet)

router.register(r'perfil_profesional', PerfilProfesionalViewSet)

router.register(r'disponibilidad_usuario', DisponibilidadUsuarioViewSet)

router.register(r'recomendaciones', RecomendacionesViewSet)

router.register(r'cuidados_enfermeria', CuidadosEnfermeriaViewSet)

router.register(r'elementos_paciente', ElementosPacienteViewSet)

router.register(r'recuperacion_password', RecuperacionPasswordViewSet)

router.register(r'notificaciones', NotificacionesViewSet)

router.register(r'notificacion_destinatario', NotificacionDestinatarioViewSet)

router.register(r'citas', CitasViewSet)

router.register(r'fcm_tokens', FcmTokensViewSet)

router.register(r'camas', CamasViewSet)

router.register(r'habitaciones', HabitacionesViewSet)

router.register(r'fundaciones', FundacionesViewSet)

router.register(r'sedes', SedesViewSet)

router.register(r'camaras', CamarasViewSet)

router.register(r'tipos_evento_ia', TiposEventoIaViewSet)

router.register(r'eventos_ia', EventosIaViewSet)

router.register(r'evidencias_ia', EvidenciasIaViewSet)

router.register(r'asignacion_habitacion', AsignacionHabitacionViewSet)

router.register(r'grupo_medicacion', GrupoMedicacionViewSet)

router.register(r'formulacion_medicamentos', FormulacionMedicamentosViewSet)

urlpatterns = [

path(
    'auth/login-google/',
    login_google,
    name='login_google'
),   
path(
    'usuarios/registro/',
    registro_usuario,
    name='registro_usuario'
),

path(
    'usuarios/login/',
    login_usuario,
    name='login_usuario'
),

path(
    'usuarios/cambiar-contrasena/',
    cambiar_contrasena,
    name='cambiar_contrasena'
),
path(

    'usuarios/recuperar-password/',

    recuperar_password,

    name='recuperar_password'

),
path(
    'usuarios/verificar-codigo/',
    verificar_codigo,
    name='verificar_codigo'
),
path(
    'usuarios/cambiar-password-recuperacion/',
    cambiar_password_recuperacion,
    name='cambiar_password_recuperacion'
),
path(
    '',
    include(router.urls)
),
path(
    'subir-imagen/',
    SubirImagenCloudinaryView.as_view(),
    name='subir_imagen_cloudinary'
),


]
