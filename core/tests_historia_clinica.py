import io
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, DataError, connection
from django.test import SimpleTestCase, TestCase
from pypdf import PdfWriter
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from config.settings_test import verificar_aislamiento_bd_pruebas

from .asignaciones_vigencia import ZONA_COLOMBIA
from .authentication import (
    N8NAuthenticatedUser,
    UsuarioAutenticado,
    crear_token_usuario,
)
from .models import (
    AsignacionPacienteCuidador,
    Bitacora,
    DocumentosHistoriaClinica,
    Fundaciones,
    Habitaciones,
    HistoriaClinicas,
    Pacientes,
    Roles,
    Sedes,
    SignosVitales,
    Usuarios,
)
from .permissions import (
    ROL_ADMINISTRADOR,
    ROL_CUIDADOR,
    ROL_ENCARGADO,
    ROL_SUPERADMINISTRADOR,
    PermisoHistoriaClinica,
    obtener_id_rol_real,
    obtener_id_sede_activa,
    obtener_pacientes_consulta_historia,
    puede_consultar_documento_historico,
    puede_consultar_historia_paciente,
    puede_escribir_historia_paciente,
)
from .serializers import HistoriaClinicasSerializer, evaluar_rangos_signos_vitales

MODELOS_ETAPA_1 = [
    Fundaciones,
    Sedes,
    Habitaciones,
    Roles,
    Usuarios,
    Pacientes,
    AsignacionPacienteCuidador,
    HistoriaClinicas,
    DocumentosHistoriaClinica,
]

RANGOS_MOCK_ETAPA_1 = {
    'sistolica_min': 110.0,
    'sistolica_max': 140.0,
    'diastolica_min': 65.0,
    'diastolica_max': 85.0,
    'fc_min': 60.0,
    'fc_max': 90.0,
    'fr_min': 12.0,
    'fr_max': 20.0,
    'temp_min': 36.0,
    'temp_max': 37.2,
    'sat_min': 92.0,
    'sat_max': 98.0,
    'resumen_condicion': 'Paciente estable de prueba.',
}


def dt_colombia(anio, mes, dia, hora=8, minuto=0, segundo=0):
    return datetime(anio, mes, dia, hora, minuto, segundo, tzinfo=ZONA_COLOMBIA)


class BaseTablasHistoriaEnMemoriaTestCase(TestCase):
    """Base común que crea y limpia únicamente en SQLite en memoria las tablas requeridas."""

    @classmethod
    def setUpClass(cls):
        cls._managed_original = {}
        cls._tablas_creadas = []
        tablas_existentes = set(connection.introspection.table_names())
        with connection.schema_editor() as editor:
            for modelo in MODELOS_ETAPA_1:
                cls._managed_original[modelo] = modelo._meta.managed
                modelo._meta.managed = True
                if modelo._meta.db_table not in tablas_existentes:
                    editor.create_model(modelo)
                    cls._tablas_creadas.append(modelo)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as editor:
            for modelo in reversed(cls._tablas_creadas):
                if modelo._meta.db_table in connection.introspection.table_names():
                    editor.delete_model(modelo)
            for modelo, managed in cls._managed_original.items():
                modelo._meta.managed = managed

    def setUp(self):
        self.factory = APIRequestFactory()
        self.permiso = PermisoHistoriaClinica()
        self.ahora_fijo = dt_colombia(2026, 11, 27, 10, 0, 0)

        self.fundacion = Fundaciones.objects.create(
            nombre='Fundación GerIApp',
            estado=True,
            fecha_registro=self.ahora_fijo,
        )
        self.sede_norte = Sedes.objects.create(
            id_sede=10,
            nombre='Sede Norte',
            estado=True,
            fecha_registro=self.ahora_fijo,
            id_fundacion=self.fundacion,
        )
        self.sede_sur = Sedes.objects.create(
            id_sede=20,
            nombre='Sede Sur',
            estado=True,
            fecha_registro=self.ahora_fijo,
            id_fundacion=self.fundacion,
        )
        self.sede_inactiva = Sedes.objects.create(
            id_sede=30,
            nombre='Sede Inactiva',
            estado=False,
            fecha_registro=self.ahora_fijo,
            id_fundacion=self.fundacion,
        )

        self.hab_norte = Habitaciones.objects.create(
            id_habitacion=101,
            nombre='Habitación Norte 101',
            numero='101',
            estado=True,
            id_sede=self.sede_norte,
        )
        self.hab_sur = Habitaciones.objects.create(
            id_habitacion=201,
            nombre='Habitación Sur 201',
            numero='201',
            estado=True,
            id_sede=self.sede_sur,
        )

        self.rol_admin = Roles.objects.create(
            id_rol=ROL_ADMINISTRADOR,
            nombre='Administrador',
            descripcion='Administrador de sede',
            estado=True,
        )
        self.rol_encargado = Roles.objects.create(
            id_rol=ROL_ENCARGADO,
            nombre='Encargado',
            descripcion='Encargado de sede',
            estado=True,
        )
        self.rol_cuidador = Roles.objects.create(
            id_rol=ROL_CUIDADOR,
            nombre='Cuidador',
            descripcion='Cuidador de turno',
            estado=True,
        )
        self.rol_superadmin = Roles.objects.create(
            id_rol=ROL_SUPERADMINISTRADOR,
            nombre='Superadministrador',
            descripcion='Gestión global sin acceso clínico',
            estado=True,
        )

        # CASO TRAMPA EXPLÍCITO: id_usuario=1 pero rol Encargado (id_rol=2)
        self.encargado_con_id_usuario_uno = self._crear_usuario(
            id_usuario=1,
            rol=self.rol_encargado,
            sede=self.sede_norte,
            documento='1001',
            nombres='Encargado',
            apellidos='IdUno',
        )

        # Administrador real de Sede Norte con id_usuario distinto de 1 (55)
        self.admin_norte = self._crear_usuario(
            id_usuario=55,
            rol=self.rol_admin,
            sede=self.sede_norte,
            documento='1002',
            nombres='Laura',
            apellidos='AdminNorte',
        )

        # Administrador real de Sede Sur con id_usuario=88
        self.admin_sur = self._crear_usuario(
            id_usuario=88,
            rol=self.rol_admin,
            sede=self.sede_sur,
            documento='1003',
            nombres='Jorge',
            apellidos='AdminSur',
        )

        self.cuidador_norte = self._crear_usuario(
            id_usuario=70,
            rol=self.rol_cuidador,
            sede=self.sede_norte,
            documento='1004',
            nombres='Marta',
            apellidos='CuidadoraNorte',
        )

        self.otro_cuidador_norte = self._crear_usuario(
            id_usuario=71,
            rol=self.rol_cuidador,
            sede=self.sede_norte,
            documento='1005',
            nombres='Pedro',
            apellidos='CuidadorDos',
        )

        self.superadmin = self._crear_usuario(
            id_usuario=4,
            rol=self.rol_superadmin,
            sede=None,
            documento='1006',
            nombres='Root',
            apellidos='Global',
        )

        self.paciente_norte_asignado = self._crear_paciente(
            id_paciente=501,
            nombre='Carmen',
            apellido='Rojas',
            documento='2001',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        self.paciente_norte_no_asignado = self._crear_paciente(
            id_paciente=502,
            nombre='Luis',
            apellido='Pardo',
            documento='2002',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        self.paciente_sur = self._crear_paciente(
            id_paciente=601,
            nombre='Rosa',
            apellido='Mendez',
            documento='2003',
            sede=self.sede_sur,
            habitacion_id=self.hab_sur.id_habitacion,
        )

        self.asignacion_vigente_norte = AsignacionPacienteCuidador.objects.create(
            id_paciente=self.paciente_norte_asignado,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo - timedelta(hours=2),
            fecha_fin=self.ahora_fijo + timedelta(hours=6),
            estado='Activo',
            observaciones='Turno diurno activo',
        )

        self.historia_norte = HistoriaClinicas.objects.create(
            fecha_apertura=self.ahora_fijo,
            antecedentes='HTA controlada',
            alergias='Ninguna conocida',
            observaciones='Estable',
            estado=True,
            id_paciente=self.paciente_norte_asignado,
        )
        self.historia_norte_otro = HistoriaClinicas.objects.create(
            fecha_apertura=self.ahora_fijo,
            antecedentes='Artrosis',
            alergias='Ibuprofeno',
            observaciones='Control mensual',
            estado=True,
            id_paciente=self.paciente_norte_no_asignado,
        )
        self.historia_sur = HistoriaClinicas.objects.create(
            fecha_apertura=self.ahora_fijo,
            antecedentes='EPOC',
            alergias='Penicilina',
            observaciones='Oxígeno basal',
            estado=True,
            id_paciente=self.paciente_sur,
        )

        self.doc_vigente_norte = DocumentosHistoriaClinica.objects.create(
            id_paciente=self.paciente_norte_asignado,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/doc_vigente.pdf',
            nombre_archivo='historia_vigente.pdf',
            descripcion='Documento actual',
            estado=True,
        )
        self.doc_historico_norte = DocumentosHistoriaClinica.objects.create(
            id_paciente=self.paciente_norte_asignado,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/doc_anterior.pdf',
            nombre_archivo='historia_anterior.pdf',
            descripcion='Documento reemplazado',
            estado=False,
        )
        self.doc_vigente_norte_otro = DocumentosHistoriaClinica.objects.create(
            id_paciente=self.paciente_norte_no_asignado,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/doc_otro_norte.pdf',
            nombre_archivo='historia_luis.pdf',
            estado=True,
        )
        self.doc_vigente_sur = DocumentosHistoriaClinica.objects.create(
            id_paciente=self.paciente_sur,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/doc_sur_actual.pdf',
            nombre_archivo='historia_sur_actual.pdf',
            estado=True,
        )
        self.doc_historico_sur = DocumentosHistoriaClinica.objects.create(
            id_paciente=self.paciente_sur,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/doc_sur_anterior.pdf',
            nombre_archivo='historia_sur_anterior.pdf',
            estado=False,
        )

    def _crear_usuario(self, id_usuario, rol, sede, documento, nombres, apellidos, estado=True):
        return Usuarios.objects.create(
            id_usuario=id_usuario,
            id_rol=rol,
            id_sede=sede,
            tipo_documento='CC',
            numero_documento=documento,
            nombres=nombres,
            apellidos=apellidos,
            correo=f'{documento}@geriapp.local',
            fecha_ingreso=self.ahora_fijo,
            estado=estado,
        )

    def _crear_paciente(self, id_paciente, nombre, apellido, documento, sede, habitacion_id):
        return Pacientes.objects.create(
            id_paciente=id_paciente,
            nombre=nombre,
            apellido=apellido,
            eps='Sura',
            sede=sede.nombre,
            fecha_ingreso=self.ahora_fijo,
            habitacion=habitacion_id,
            tipo_documento='CC',
            numero_documento=documento,
            fecha_nacimiento=date(1945, 5, 12),
            genero='F',
            cama=1,
            estado=True,
            id_sede=sede,
        )

    def _cliente_autenticado(self, usuario):
        client = APIClient()
        token = crear_token_usuario(usuario)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client


class AislamientoBaseDatosTests(SimpleTestCase):
    """Comprueba que la suite corra únicamente en SQLite en memoria sin hosts remotos."""

    def test_conexion_actual_es_sqlite_en_memoria(self):
        self.assertEqual(connection.vendor, 'sqlite')
        nombre_bd = str(connection.settings_dict.get('NAME') or '')
        self.assertTrue(
            nombre_bd == ':memory:'
            or 'mode=memory' in nombre_bd
            or nombre_bd.startswith('file:memorydb')
        )
        self.assertEqual(str(connection.settings_dict.get('HOST') or ''), '')

    def test_candado_rechaza_postgresql_o_host_remoto(self):
        with self.assertRaises(RuntimeError):
            verificar_aislamiento_bd_pruebas({
                'default': {
                    'ENGINE': 'django.db.backends.postgresql',
                    'NAME': 'geriapp',
                    'HOST': 'dpg-ejemplo.render.com',
                }
            })

        with self.assertRaises(RuntimeError):
            verificar_aislamiento_bd_pruebas({
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                    'HOST': '127.0.0.1',
                }
            })

        with self.assertRaises(RuntimeError):
            verificar_aislamiento_bd_pruebas({
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': 'db_en_disco.sqlite3',
                    'HOST': '',
                }
            })


class SeguridadPermisosHistoriaClinicaTests(BaseTablasHistoriaEnMemoriaTestCase):
    """Pruebas unitarias de Etapa 1 sobre helpers y PermisoHistoriaClinica."""

    def _construir_request(self, metodo, usuario):
        creador = getattr(self.factory, metodo.lower())
        request = creador('/api/historia_clinicas/')
        if usuario is not None:
            envuelto = (
                usuario
                if isinstance(usuario, (UsuarioAutenticado, N8NAuthenticatedUser))
                else UsuarioAutenticado(usuario)
            )
            force_authenticate(request, user=envuelto)
            request.user = envuelto
        return request

    def _evaluar_permiso(self, metodo, usuario, obj=None):
        request = self._construir_request(metodo, usuario)
        tiene_permiso = self.permiso.has_permission(request, view=None)
        if not tiene_permiso or obj is None:
            return tiene_permiso
        return self.permiso.has_object_permission(request, view=None, obj=obj)

    def test_diferencia_estricta_entre_id_usuario_e_id_rol(self):
        self.assertEqual(self.encargado_con_id_usuario_uno.id_usuario, 1)
        self.assertEqual(
            obtener_id_rol_real(UsuarioAutenticado(self.encargado_con_id_usuario_uno)),
            ROL_ENCARGADO,
        )
        self.assertFalse(
            puede_consultar_historia_paciente(
                UsuarioAutenticado(self.encargado_con_id_usuario_uno),
                self.paciente_norte_asignado,
                ahora=self.ahora_fijo,
            )
        )
        self.assertFalse(
            puede_escribir_historia_paciente(
                UsuarioAutenticado(self.encargado_con_id_usuario_uno),
                self.paciente_norte_asignado,
            )
        )
        self.assertFalse(self._evaluar_permiso('GET', self.encargado_con_id_usuario_uno))
        self.assertFalse(self._evaluar_permiso('POST', self.encargado_con_id_usuario_uno))

        self.assertEqual(self.admin_norte.id_usuario, 55)
        self.assertEqual(
            obtener_id_rol_real(UsuarioAutenticado(self.admin_norte)),
            ROL_ADMINISTRADOR,
        )
        self.assertTrue(
            puede_escribir_historia_paciente(
                UsuarioAutenticado(self.admin_norte),
                self.paciente_norte_asignado,
            )
        )

        cuidador_id_uno = Usuarios(
            id_usuario=1,
            id_rol=self.rol_cuidador,
            id_sede=self.sede_norte,
            estado=True,
        )
        self.assertEqual(obtener_id_rol_real(cuidador_id_uno), ROL_CUIDADOR)
        self.assertFalse(self._evaluar_permiso('POST', cuidador_id_uno))

    def test_matriz_cuatro_roles_lectura_escritura_e_historicos(self):
        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            # Rol 1: Administrador Norte lee, escribe y consulta históricos de su sede
            for metodo in ('GET', 'POST', 'PUT', 'PATCH'):
                self.assertTrue(
                    self._evaluar_permiso(metodo, self.admin_norte, self.historia_norte),
                    f'Admin Norte debía tener permiso en {metodo}',
                )
            self.assertTrue(
                self._evaluar_permiso('GET', self.admin_norte, self.doc_vigente_norte)
            )
            self.assertTrue(
                self._evaluar_permiso('GET', self.admin_norte, self.doc_historico_norte)
            )

            # Rol 2: Encargado bloqueado completamente (lectura, escritura, históricos, DELETE)
            self.assertEqual(
                list(
                    obtener_pacientes_consulta_historia(
                        self.encargado_con_id_usuario_uno,
                        ahora=self.ahora_fijo,
                    )
                ),
                [],
            )
            for metodo in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
                self.assertFalse(
                    self._evaluar_permiso(
                        metodo,
                        self.encargado_con_id_usuario_uno,
                        self.historia_norte,
                    ),
                    f'Encargado no debe tener acceso con {metodo}',
                )
            self.assertFalse(
                self._evaluar_permiso(
                    'GET',
                    self.encargado_con_id_usuario_uno,
                    self.doc_historico_norte,
                )
            )

            # Rol 3: Cuidador Norte solo consulta su paciente asignado vigente; no escribe ni ve históricos
            self.assertTrue(
                puede_consultar_historia_paciente(
                    self.cuidador_norte,
                    self.paciente_norte_asignado,
                    ahora=self.ahora_fijo,
                )
            )
            self.assertTrue(
                puede_consultar_historia_paciente(
                    UsuarioAutenticado(self.cuidador_norte),
                    self.paciente_norte_asignado,
                    ahora=self.ahora_fijo,
                )
            )
            self.assertTrue(
                self._evaluar_permiso('GET', self.cuidador_norte, self.historia_norte)
            )
            self.assertTrue(
                self._evaluar_permiso('GET', self.cuidador_norte, self.doc_vigente_norte)
            )
            self.assertFalse(
                puede_consultar_historia_paciente(
                    self.cuidador_norte,
                    self.paciente_norte_no_asignado,
                    ahora=self.ahora_fijo,
                )
            )
            for metodo in ('POST', 'PUT', 'PATCH'):
                self.assertFalse(
                    self._evaluar_permiso(
                        metodo,
                        self.cuidador_norte,
                        self.historia_norte,
                    )
                )
            self.assertFalse(
                self._evaluar_permiso('GET', self.cuidador_norte, self.doc_historico_norte)
            )

            # Rol 4: Superadministrador sin acceso clínico alguno
            self.assertEqual(
                list(obtener_pacientes_consulta_historia(self.superadmin, ahora=self.ahora_fijo)),
                [],
            )
            for metodo in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
                self.assertFalse(
                    self._evaluar_permiso(metodo, self.superadmin, self.historia_norte)
                )
            self.assertFalse(
                puede_consultar_documento_historico(
                    self.superadmin,
                    self.paciente_norte_asignado,
                )
            )

    def test_aislamiento_estricto_entre_administradores_y_usuarios_de_distintas_sedes(self):
        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            self.assertTrue(
                self._evaluar_permiso('GET', self.admin_sur, self.historia_sur)
            )
            self.assertTrue(
                self._evaluar_permiso('POST', self.admin_sur, self.historia_sur)
            )
            self.assertTrue(
                self._evaluar_permiso('GET', self.admin_sur, self.doc_historico_sur)
            )

            for metodo in ('GET', 'POST', 'PUT', 'PATCH'):
                self.assertFalse(
                    self._evaluar_permiso(metodo, self.admin_sur, self.historia_norte),
                    f'Admin Sur no debe acceder a Sede Norte con {metodo}',
                )
                self.assertFalse(
                    self._evaluar_permiso(metodo, self.admin_norte, self.historia_sur),
                    f'Admin Norte no debe acceder a Sede Sur con {metodo}',
                )

            self.assertFalse(
                self._evaluar_permiso('GET', self.admin_sur, self.doc_historico_norte)
            )
            self.assertFalse(
                self._evaluar_permiso('GET', self.admin_norte, self.doc_historico_sur)
            )

            AsignacionPacienteCuidador.objects.create(
                id_paciente=self.paciente_sur,
                id_usuario=self.cuidador_norte,
                fecha_inicio=self.ahora_fijo - timedelta(hours=1),
                fecha_fin=self.ahora_fijo + timedelta(hours=4),
                estado='Activo',
                observaciones='Asignación cruzada inválida',
            )
            self.assertFalse(
                puede_consultar_historia_paciente(
                    self.cuidador_norte,
                    self.paciente_sur,
                    ahora=self.ahora_fijo,
                )
            )

    def test_cuidador_con_asignacion_vencida_futura_inactiva_o_ajena(self):
        AsignacionPacienteCuidador.objects.create(
            id_paciente=self.paciente_norte_no_asignado,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo - timedelta(hours=10),
            fecha_fin=self.ahora_fijo - timedelta(minutes=1),
            estado='Activo',
            observaciones='Turno ya vencido',
        )
        paciente_futuro = self._crear_paciente(
            id_paciente=503,
            nombre='Ana',
            apellido='Futura',
            documento='2004',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        AsignacionPacienteCuidador.objects.create(
            id_paciente=paciente_futuro,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo + timedelta(minutes=30),
            fecha_fin=self.ahora_fijo + timedelta(hours=8),
            estado='Activo',
            observaciones='Turno futuro',
        )
        paciente_inactivo_asig = self._crear_paciente(
            id_paciente=504,
            nombre='Mario',
            apellido='Cerrado',
            documento='2005',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        AsignacionPacienteCuidador.objects.create(
            id_paciente=paciente_inactivo_asig,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo - timedelta(hours=2),
            fecha_fin=self.ahora_fijo + timedelta(hours=4),
            estado='Finalizado',
            observaciones='Turno cerrado',
        )

        self.assertFalse(
            puede_consultar_historia_paciente(
                self.cuidador_norte,
                self.paciente_norte_no_asignado,
                ahora=self.ahora_fijo,
            )
        )
        self.assertFalse(
            puede_consultar_historia_paciente(
                self.cuidador_norte,
                paciente_futuro,
                ahora=self.ahora_fijo,
            )
        )
        self.assertFalse(
            puede_consultar_historia_paciente(
                self.cuidador_norte,
                paciente_inactivo_asig,
                ahora=self.ahora_fijo,
            )
        )
        self.assertFalse(
            puede_consultar_historia_paciente(
                self.otro_cuidador_norte,
                self.paciente_norte_asignado,
                ahora=self.ahora_fijo,
            )
        )

    def test_usuarios_inactivos_sede_inactiva_rol_inactivo_y_n8n(self):
        admin_inactivo = self._crear_usuario(
            id_usuario=90,
            rol=self.rol_admin,
            sede=self.sede_norte,
            documento='3001',
            nombres='Admin',
            apellidos='Inactivo',
            estado=False,
        )
        admin_sede_inactiva = self._crear_usuario(
            id_usuario=91,
            rol=self.rol_admin,
            sede=self.sede_inactiva,
            documento='3002',
            nombres='Admin',
            apellidos='SedeCerrada',
            estado=True,
        )
        rol_deshabilitado = Roles.objects.create(
            id_rol=9,
            nombre='Temporal',
            descripcion='Rol inactivo',
            estado=False,
        )
        usuario_rol_inactivo = self._crear_usuario(
            id_usuario=92,
            rol=rol_deshabilitado,
            sede=self.sede_norte,
            documento='3003',
            nombres='Usuario',
            apellidos='RolInactivo',
            estado=True,
        )

        self.assertIsNone(obtener_id_rol_real(admin_inactivo))
        self.assertFalse(self._evaluar_permiso('GET', admin_inactivo, self.historia_norte))
        self.assertFalse(self._evaluar_permiso('POST', admin_inactivo, self.historia_norte))

        self.assertIsNone(obtener_id_sede_activa(admin_sede_inactiva))
        self.assertFalse(self._evaluar_permiso('GET', admin_sede_inactiva))
        self.assertFalse(self._evaluar_permiso('POST', admin_sede_inactiva))

        self.assertIsNone(obtener_id_rol_real(usuario_rol_inactivo))
        self.assertFalse(self._evaluar_permiso('GET', usuario_rol_inactivo))

        self.assertIsNone(obtener_id_rol_real(N8NAuthenticatedUser()))
        self.assertFalse(self._evaluar_permiso('GET', N8NAuthenticatedUser()))

    def test_ningun_rol_puede_eliminar_historias_ni_documentos(self):
        for usuario in (
            self.admin_norte,
            self.admin_sur,
            self.encargado_con_id_usuario_uno,
            self.cuidador_norte,
            self.superadmin,
        ):
            self.assertFalse(
                self._evaluar_permiso('DELETE', usuario, self.historia_norte)
            )
            self.assertFalse(
                self._evaluar_permiso('DELETE', usuario, self.doc_vigente_norte)
            )
            self.assertFalse(
                self._evaluar_permiso('DELETE', usuario, self.doc_historico_norte)
            )


class EndpointsIntegracionHistoriaClinicaTests(BaseTablasHistoriaEnMemoriaTestCase):
    """
    Pruebas de integración sobre los endpoints HTTP reales:
    - /api/historia_clinicas/
    - /api/documentos_historia_clinica/
    - /api/procesar-historia-pdf/<id_paciente>/
    """

    def test_cuidador_consulta_endpoints_android_con_contrato_json_intacto_y_filtrado_vigencia(self):
        HistoriaClinicas.objects.create(
            fecha_apertura=self.ahora_fijo,
            antecedentes='Registro inactivo antiguo',
            alergias='Ninguna',
            observaciones='Inactiva',
            estado=False,
            id_paciente=self.paciente_norte_asignado,
        )

        # Asignación vencida sobre el segundo paciente de Sede Norte
        AsignacionPacienteCuidador.objects.create(
            id_paciente=self.paciente_norte_no_asignado,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo - timedelta(hours=9),
            fecha_fin=self.ahora_fijo - timedelta(minutes=5),
            estado='Activo',
            observaciones='Vencida',
        )

        cliente = self._cliente_autenticado(self.cuidador_norte)

        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            # 1. Endpoint Android: GET /api/historia_clinicas/
            res_historias = cliente.get('/api/historia_clinicas/')
            self.assertEqual(res_historias.status_code, status.HTTP_200_OK)
            datos_historias = res_historias.json()
            self.assertIsInstance(datos_historias, list)
            self.assertEqual(len(datos_historias), 1)

            item_h = datos_historias[0]
            for campo_android in (
                'id_historia_clinica',
                'fecha_apertura',
                'antecedentes',
                'alergias',
                'observaciones',
                'estado',
                'id_paciente',
            ):
                self.assertIn(campo_android, item_h)
            self.assertEqual(item_h['id_historia_clinica'], self.historia_norte.id_historia_clinica)
            self.assertEqual(item_h['id_paciente'], self.paciente_norte_asignado.id_paciente)
            self.assertTrue(item_h['estado'])

            # 2. Endpoint Android: GET /api/documentos_historia_clinica/?id_paciente={id}
            res_docs = cliente.get(
                f'/api/documentos_historia_clinica/?id_paciente={self.paciente_norte_asignado.id_paciente}'
            )
            self.assertEqual(res_docs.status_code, status.HTTP_200_OK)
            datos_docs = res_docs.json()
            self.assertIsInstance(datos_docs, list)
            self.assertEqual(len(datos_docs), 1)

            item_d = datos_docs[0]
            for campo_doc_android in (
                'id_documento',
                'id_paciente',
                'archivo',
                'nombre_archivo',
                'fecha_subida',
                'descripcion',
                'estado',
            ):
                self.assertIn(campo_doc_android, item_d)
            self.assertEqual(item_d['id_documento'], self.doc_vigente_norte.id_documento)
            self.assertTrue(item_d['estado'])

            # Si consulta documentos de un paciente con asignación vencida, recibe lista vacía
            res_docs_vencido = cliente.get(
                f'/api/documentos_historia_clinica/?id_paciente={self.paciente_norte_no_asignado.id_paciente}'
            )
            self.assertEqual(res_docs_vencido.status_code, status.HTTP_200_OK)
            self.assertEqual(res_docs_vencido.json(), [])

            # Si su asignación pasa a Inactivo/Finalizado, deja de ver la historia inmediatamente
            self.asignacion_vigente_norte.estado = 'Finalizado'
            self.asignacion_vigente_norte.save(update_fields=['estado'])

            res_tras_cierre = cliente.get('/api/historia_clinicas/')
            self.assertEqual(res_tras_cierre.status_code, status.HTTP_200_OK)
            self.assertEqual(res_tras_cierre.json(), [])

    def test_encargado_y_superadmin_reciben_403_en_todos_los_endpoints_clinicos(self):
        archivo_dummy = SimpleUploadedFile(
            'prueba.pdf',
            b'%PDF-1.4 contenido ficticio',
            content_type='application/pdf',
        )

        for usuario in (self.encargado_con_id_usuario_uno, self.superadmin):
            cliente = self._cliente_autenticado(usuario)

            self.assertEqual(
                cliente.get('/api/historia_clinicas/').status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.get(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.post(
                    '/api/historia_clinicas/',
                    {
                        'fecha_apertura': self.ahora_fijo.isoformat(),
                        'antecedentes': 'Intento no autorizado',
                        'alergias': 'Ninguna',
                        'observaciones': 'Prueba',
                        'estado': True,
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.put(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                    {
                        'fecha_apertura': self.ahora_fijo.isoformat(),
                        'antecedentes': 'Intento PUT no autorizado',
                        'alergias': 'Ninguna',
                        'observaciones': 'Prueba PUT',
                        'estado': True,
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.patch(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                    {'observaciones': 'Cambio bloqueado'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.delete(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

            self.assertEqual(
                cliente.get('/api/documentos_historia_clinica/').status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.get(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.post(
                    '/api/documentos_historia_clinica/',
                    {
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                        'nombre_archivo': 'prueba.pdf',
                        'estado': True,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.put(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                    {
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                        'nombre_archivo': 'intento_put.pdf',
                        'descripcion': 'Intento PUT bloqueado',
                        'estado': True,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.patch(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                    {'descripcion': 'Intento PATCH bloqueado'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.delete(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

            archivo_dummy.seek(0)
            self.assertEqual(
                cliente.post(
                    f'/api/procesar-historia-pdf/{self.paciente_norte_asignado.id_paciente}/',
                    {'archivo': archivo_dummy},
                    format='multipart',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

    def test_cuidador_bloqueado_en_escritura_eliminacion_e_historicos_en_endpoints(self):
        cliente = self._cliente_autenticado(self.cuidador_norte)
        archivo_dummy = SimpleUploadedFile(
            'cuidador.pdf',
            b'%PDF-1.4 contenido ficticio',
            content_type='application/pdf',
        )

        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            # Escrituras bloqueadas en HistoriaClinicasViewSet
            self.assertEqual(
                cliente.post(
                    '/api/historia_clinicas/',
                    {
                        'fecha_apertura': self.ahora_fijo.isoformat(),
                        'antecedentes': 'No permitido',
                        'alergias': 'No',
                        'observaciones': 'No',
                        'estado': True,
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.put(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                    {
                        'fecha_apertura': self.ahora_fijo.isoformat(),
                        'antecedentes': 'No permitido',
                        'alergias': 'No',
                        'observaciones': 'No',
                        'estado': True,
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.patch(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                    {'observaciones': 'Modificación bloqueada'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.delete(
                    f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

            # Escrituras, DELETE e históricos bloqueados en DocumentosHistoriaClinicaViewSet
            self.assertEqual(
                cliente.post(
                    '/api/documentos_historia_clinica/',
                    {
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                        'archivo': archivo_dummy,
                        'nombre_archivo': 'cuidador.pdf',
                        'estado': True,
                    },
                    format='multipart',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.put(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                    {
                        'id_paciente': self.paciente_norte_asignado.id_paciente,
                        'nombre_archivo': 'cuidador_put.pdf',
                        'descripcion': 'Intento PUT cuidador',
                        'estado': True,
                    },
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.patch(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                    {'descripcion': 'Intento edición cuidador'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.delete(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.get(
                    f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente.get(
                    '/api/documentos_historia_clinica/?incluir_historicos=true'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

            # Endpoint ProcesarHistoriaPdfView bloqueado para cuidador
            archivo_dummy.seek(0)
            self.assertEqual(
                cliente.post(
                    f'/api/procesar-historia-pdf/{self.paciente_norte_asignado.id_paciente}/',
                    {'archivo': archivo_dummy},
                    format='multipart',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

    @patch('core.views.subir_documento')
    @patch('core.views.extraer_historia_clinica_pdf')
    def test_administrador_gestiona_solo_su_sede_y_bloquea_reasignacion_id_paciente_y_delete(
        self,
        mock_gemini,
        mock_cloudinary,
    ):
        mock_gemini.return_value = {
            'documento_legible': True,
            'motivo_ilegible': '',
            'antecedentes': 'Diabetes tipo 2 controlada.',
            'alergias': 'Sulfas.',
            'observaciones': 'Control glucémico periódico.',
            'tiene_mediciones_signos_vitales': False,
            'signos_vitales_medidos': None,
            'tiene_referencias_explicitas': True,
            'rangos_vitales': dict(RANGOS_MOCK_ETAPA_1),
        }
        mock_cloudinary.return_value = {
            'secure_url': 'https://res.cloudinary.com/test-cloud-local/raw/upload/nuevo_norte.pdf',
            'public_id': 'geriapp/documentos_historia_clinica/nuevo_norte.pdf',
        }

        cliente_norte = self._cliente_autenticado(self.admin_norte)
        cliente_sur = self._cliente_autenticado(self.admin_sur)

        # 1. Listados filtrados estrictamente por la sede de cada administrador
        res_lista_norte = cliente_norte.get('/api/historia_clinicas/')
        self.assertEqual(res_lista_norte.status_code, status.HTTP_200_OK)
        ids_pacientes_norte = {h['id_paciente'] for h in res_lista_norte.json()}
        self.assertEqual(
            ids_pacientes_norte,
            {
                self.paciente_norte_asignado.id_paciente,
                self.paciente_norte_no_asignado.id_paciente,
            },
        )
        self.assertNotIn(self.paciente_sur.id_paciente, ids_pacientes_norte)

        res_lista_sur = cliente_sur.get('/api/historia_clinicas/')
        self.assertEqual(res_lista_sur.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [h['id_paciente'] for h in res_lista_sur.json()],
            [self.paciente_sur.id_paciente],
        )

        # 2. Admin Norte puede crear y editar en su propia sede (con mocks, sin red externa)
        paciente_nuevo_norte = self._crear_paciente(
            id_paciente=509,
            nombre='Elena',
            apellido='Norte',
            documento='2099',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        res_crear_historia = cliente_norte.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'antecedentes': 'Diabetes tipo 2',
                'alergias': 'Sulfas',
                'observaciones': 'Control glucémico',
                'estado': True,
                'id_paciente': paciente_nuevo_norte.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_crear_historia.status_code, status.HTTP_201_CREATED)

        res_patch_propia = cliente_norte.patch(
            f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
            {'observaciones': 'Observación actualizada por Admin Norte'},
            format='json',
        )
        self.assertEqual(res_patch_propia.status_code, status.HTTP_200_OK)

        pdf_mock = SimpleUploadedFile(
            'historia_elena.pdf',
            b'%PDF-1.4 contenido clinico simulado',
            content_type='application/pdf',
        )
        res_subir_doc = cliente_norte.post(
            '/api/documentos_historia_clinica/',
            {
                'id_paciente': paciente_nuevo_norte.id_paciente,
                'archivo': pdf_mock,
                'nombre_archivo': 'historia_elena.pdf',
                'estado': True,
            },
            format='multipart',
        )
        self.assertEqual(res_subir_doc.status_code, status.HTTP_201_CREATED)
        mock_gemini.assert_called_once()
        mock_cloudinary.assert_called_once()

        # 3. Admin Norte bloqueado al crear o procesar para paciente de Sede Sur
        self.assertEqual(
            cliente_norte.post(
                '/api/historia_clinicas/',
                {
                    'fecha_apertura': self.ahora_fijo.isoformat(),
                    'antecedentes': 'Cruce indebido',
                    'alergias': 'No',
                    'observaciones': 'No',
                    'estado': True,
                    'id_paciente': self.paciente_sur.id_paciente,
                },
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        pdf_cruce = SimpleUploadedFile(
            'cruce.pdf',
            b'%PDF-1.4 cruce',
            content_type='application/pdf',
        )
        self.assertEqual(
            cliente_norte.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': self.paciente_sur.id_paciente,
                    'archivo': pdf_cruce,
                    'nombre_archivo': 'cruce.pdf',
                    'estado': True,
                },
                format='multipart',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        pdf_cruce.seek(0)
        self.assertEqual(
            cliente_norte.post(
                f'/api/procesar-historia-pdf/{self.paciente_sur.id_paciente}/',
                {'archivo': pdf_cruce},
                format='multipart',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        # Ni Gemini ni Cloudinary debieron invocarse en los intentos bloqueados
        self.assertEqual(mock_gemini.call_count, 1)
        self.assertEqual(mock_cloudinary.call_count, 1)

        # 4. Admin Norte bloqueado al intentar cambiar id_paciente hacia Sede Sur (o a otro paciente) en PATCH/PUT
        self.assertEqual(
            cliente_norte.patch(
                f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                {'id_paciente': self.paciente_sur.id_paciente},
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.historia_norte.refresh_from_db()
        self.assertEqual(
            self.historia_norte.id_paciente_id,
            self.paciente_norte_asignado.id_paciente,
        )

        self.assertEqual(
            cliente_norte.patch(
                f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                {'id_paciente': self.paciente_sur.id_paciente},
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.doc_vigente_norte.refresh_from_db()
        self.assertEqual(
            self.doc_vigente_norte.id_paciente_id,
            self.paciente_norte_asignado.id_paciente,
        )

        # 5. Acceso directo por ID a otra sede oculto/bloqueado
        self.assertEqual(
            cliente_norte.get(
                f'/api/historia_clinicas/{self.historia_sur.id_historia_clinica}/'
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            cliente_norte.patch(
                f'/api/historia_clinicas/{self.historia_sur.id_historia_clinica}/',
                {'observaciones': 'Intento sobre sede ajena'},
                format='json',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # 6. Documentos históricos solo visibles para el Administrador de esa misma sede
        res_docs_vigentes = cliente_norte.get(
            f'/api/documentos_historia_clinica/?id_paciente={self.paciente_norte_asignado.id_paciente}'
        )
        self.assertEqual(
            [d['id_documento'] for d in res_docs_vigentes.json()],
            [self.doc_vigente_norte.id_documento],
        )

        res_docs_con_hist = cliente_norte.get(
            f'/api/documentos_historia_clinica/?id_paciente={self.paciente_norte_asignado.id_paciente}&incluir_historicos=true'
        )
        self.assertEqual(res_docs_con_hist.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {d['id_documento'] for d in res_docs_con_hist.json()},
            {
                self.doc_vigente_norte.id_documento,
                self.doc_historico_norte.id_documento,
            },
        )
        self.assertEqual(
            cliente_norte.get(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
            ).status_code,
            status.HTTP_200_OK,
        )
        # Admin Sur no puede ver el histórico de Sede Norte
        self.assertEqual(
            cliente_sur.get(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # 7. DELETE bloqueado incluso para el propio Administrador de la sede
        self.assertEqual(
            cliente_norte.delete(
                f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/'
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            cliente_norte.delete(
                f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            cliente_norte.delete(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )


class TextosClinicosCompletosEtapa31Tests(BaseTablasHistoriaEnMemoriaTestCase):
    """
    Pruebas aisladas de Etapa 3.1 (SQLite en memoria):
    - Textos clínicos > 200 y > 5.000 caracteres sin truncado.
    - Tildes, eñes, saltos de línea y múltiples párrafos intactos.
    - Cadenas vacías (''), campos omitidos, normalización de None -> '' (nunca NULL)
      y conservación literal de negaciones médicas explícitas.
    - Captura de DataError fuera de transaction.atomic() con rollback completo.
    - Regresión de permisos por rol y sede sobre textos extensos.

    NOTA: SQLite en memoria valida únicamente la capa Django/DRF/transaccional;
    no sustituye el ALTER TABLE físico en PostgreSQL si la columna sigue en varchar(200).
    """

    def _construir_texto_extenso(self, encabezado, longitud_minima):
        parrafos = [
            f'{encabezado} — Evaluación geriátrica integral con tildes (á, é, í, ó, ú, ñ, ü).',
            (
                'Párrafo 1: Paciente adulto mayor con hipertensión arterial crónica, '
                'cardiopatía isquémica estable, dislipidemia en manejo farmacológico y '
                'seguimiento periódico por medicina interna y geriatría.'
            ),
            (
                'Párrafo 2:\n'
                '- Antecedente quirúrgico: colecistectomía laparoscópica sin complicaciones.\n'
                '- Valoración nutricional: dieta hiposódica fraccionada en cinco tomas.\n'
                '- Rehabilitación física: marcha asistida con caminador y supervisión continua.'
            ),
        ]
        bloque_base = '\n\n'.join(parrafos)
        repeticiones = (longitud_minima // len(bloque_base)) + 2
        texto = '\n\n'.join(f'[Sección {i + 1}] {bloque_base}' for i in range(repeticiones))
        self.assertGreater(len(texto), longitud_minima)
        return texto

    def test_post_patch_put_y_get_conservan_textos_mayores_a_200_y_5000_caracteres(self):
        cliente_admin = self._cliente_autenticado(self.admin_norte)
        cliente_cuidador = self._cliente_autenticado(self.cuidador_norte)

        paciente_nuevo = self._crear_paciente(
            id_paciente=520,
            nombre='Beatriz',
            apellido='Lozano',
            documento='2520',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        AsignacionPacienteCuidador.objects.create(
            id_paciente=paciente_nuevo,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo - timedelta(hours=1),
            fecha_fin=self.ahora_fijo + timedelta(hours=5),
            estado='Activo',
            observaciones='Turno activo para verificar lectura íntegra',
        )

        # 1. Crear con textos > 200 caracteres (ej. ~450) y > 5.000 caracteres (~5.600)
        antecedentes_5500 = self._construir_texto_extenso('ANTECEDENTES CLÍNICOS', 5500)
        alergias_350 = self._construir_texto_extenso('ALERGIAS MEDICAMENTOSAS Y ALIMENTARIAS', 350)
        observaciones_5800 = self._construir_texto_extenso('OBSERVACIONES Y EVOLUCIÓN', 5800)

        res_post = cliente_admin.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'antecedentes': antecedentes_5500,
                'alergias': alergias_350,
                'observaciones': observaciones_5800,
                'estado': True,
                'id_paciente': paciente_nuevo.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        creado = res_post.json()
        id_historia = creado['id_historia_clinica']

        self.assertGreater(len(creado['antecedentes']), 5500)
        self.assertGreater(len(creado['alergias']), 350)
        self.assertGreater(len(creado['observaciones']), 5800)
        self.assertEqual(creado['antecedentes'], antecedentes_5500)
        self.assertEqual(creado['alergias'], alergias_350)
        self.assertEqual(creado['observaciones'], observaciones_5800)

        historia_bd = HistoriaClinicas.objects.get(pk=id_historia)
        self.assertEqual(historia_bd.antecedentes, antecedentes_5500)
        self.assertEqual(historia_bd.alergias, alergias_350)
        self.assertEqual(historia_bd.observaciones, observaciones_5800)

        # 2. PATCH parcial de alergias a > 5.200 caracteres sin alterar antecedentes ni observaciones
        alergias_5200 = self._construir_texto_extenso('ALERGIAS ACTUALIZADAS EXTENSAS', 5200)
        res_patch = cliente_admin.patch(
            f'/api/historia_clinicas/{id_historia}/',
            {'alergias': alergias_5200},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        historia_bd.refresh_from_db()
        self.assertEqual(historia_bd.antecedentes, antecedentes_5500)
        self.assertEqual(historia_bd.alergias, alergias_5200)
        self.assertEqual(historia_bd.observaciones, observaciones_5800)

        # 2b. PUT completo con los tres campos > 5.000 caracteres y saltos de línea
        antecedentes_put_5300 = self._construir_texto_extenso('ANTECEDENTES PUT COMPLETO', 5300)
        res_put = cliente_admin.put(
            f'/api/historia_clinicas/{id_historia}/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'antecedentes': antecedentes_put_5300,
                'alergias': alergias_5200,
                'observaciones': observaciones_5800,
                'estado': True,
                'id_paciente': paciente_nuevo.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_put.status_code, status.HTTP_200_OK)
        historia_bd.refresh_from_db()
        self.assertEqual(historia_bd.antecedentes, antecedentes_put_5300)
        self.assertEqual(historia_bd.alergias, alergias_5200)
        self.assertEqual(historia_bd.observaciones, observaciones_5800)

        # 3. Cuidador asignado vigente recibe textos íntegros por GET y sigue bloqueado en PATCH (403)
        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            res_get_cuidador = cliente_cuidador.get(
                f'/api/historia_clinicas/?id_paciente={paciente_nuevo.id_paciente}'
            )
            self.assertEqual(res_get_cuidador.status_code, status.HTTP_200_OK)
            lista = res_get_cuidador.json()
            self.assertEqual(len(lista), 1)
            self.assertEqual(lista[0]['antecedentes'], antecedentes_put_5300)
            self.assertEqual(lista[0]['alergias'], alergias_5200)
            self.assertEqual(lista[0]['observaciones'], observaciones_5800)

            self.assertEqual(
                cliente_cuidador.patch(
                    f'/api/historia_clinicas/{id_historia}/',
                    {'observaciones': 'Intento no autorizado'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self._cliente_autenticado(self.encargado_con_id_usuario_uno)
                .get(f'/api/historia_clinicas/{id_historia}/')
                .status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self._cliente_autenticado(self.superadmin)
                .get(f'/api/historia_clinicas/{id_historia}/')
                .status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self._cliente_autenticado(self.admin_sur)
                .patch(
                    f'/api/historia_clinicas/{id_historia}/',
                    {'antecedentes': 'Intento desde otra sede'},
                    format='json',
                )
                .status_code,
                status.HTTP_404_NOT_FOUND,
            )

    def test_campos_vacios_negaciones_explicitas_y_prohibicion_de_null(self):
        cliente_admin = self._cliente_autenticado(self.admin_norte)
        paciente_vacio = self._crear_paciente(
            id_paciente=521,
            nombre='Camilo',
            apellido='Vega',
            documento='2521',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )

        # 1. Crear con negación médica explícita en alergias y cadenas vacías en el resto
        negacion_alergias = 'Niega alergias medicamentosas o alimentarias conocidas.'
        res_post = cliente_admin.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'antecedentes': '',
                'alergias': negacion_alergias,
                'observaciones': '',
                'estado': True,
                'id_paciente': paciente_vacio.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        datos = res_post.json()
        id_historia = datos['id_historia_clinica']

        self.assertEqual(datos['antecedentes'], '')
        self.assertEqual(datos['alergias'], negacion_alergias)
        self.assertEqual(datos['observaciones'], '')
        self.assertIsNotNone(datos['antecedentes'])
        self.assertIsNotNone(datos['observaciones'])

        # 2. Enviar None explícito o campos omitidos nunca guarda NULL en BD (normaliza a '')
        res_patch_null = cliente_admin.patch(
            f'/api/historia_clinicas/{id_historia}/',
            {
                'antecedentes': None,
                'alergias': 'Niega antecedentes alérgicos; refiere intolerancia gástrica leve al hierro.',
                'observaciones': None,
            },
            format='json',
        )
        self.assertEqual(res_patch_null.status_code, status.HTTP_200_OK)
        historia_bd = HistoriaClinicas.objects.get(pk=id_historia)
        self.assertEqual(historia_bd.antecedentes, '')
        self.assertEqual(historia_bd.observaciones, '')
        self.assertIsNotNone(historia_bd.antecedentes)
        self.assertIsNotNone(historia_bd.observaciones)

        # 3. POST omitiendo los tres campos opcionales de texto guarda '' y nunca NULL
        paciente_omitidos = self._crear_paciente(
            id_paciente=522,
            nombre='Dora',
            apellido='Pineda',
            documento='2522',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        res_omitidos = cliente_admin.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'estado': True,
                'id_paciente': paciente_omitidos.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_omitidos.status_code, status.HTTP_201_CREATED)
        historia_omitidos = HistoriaClinicas.objects.get(
            pk=res_omitidos.json()['id_historia_clinica']
        )
        self.assertEqual(historia_omitidos.antecedentes, '')
        self.assertEqual(historia_omitidos.alergias, '')
        self.assertEqual(historia_omitidos.observaciones, '')

    def test_put_y_patch_con_campos_omitidos_conservan_informacion_y_distinguen_vacio_y_null(
        self,
    ):
        cliente_admin = self._cliente_autenticado(self.admin_norte)
        paciente = self._crear_paciente(
            id_paciente=524,
            nombre='Fabiola',
            apellido='Castro',
            documento='2524',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )

        antecedentes_inicial = self._construir_texto_extenso(
            'ANTECEDENTES INICIALES PROTEGIDOS',
            5200,
        )
        alergias_inicial = 'Alergia severa documentada a penicilina y cefalosporinas.'
        observaciones_inicial = self._construir_texto_extenso(
            'OBSERVACIONES INICIALES PROTEGIDAS',
            5100,
        )

        # 1. Crear historia clínica completa inicial
        res_post = cliente_admin.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'antecedentes': antecedentes_inicial,
                'alergias': alergias_inicial,
                'observaciones': observaciones_inicial,
                'estado': True,
                'id_paciente': paciente.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        id_historia = res_post.json()['id_historia_clinica']

        # 2. PUT omitiendo antecedentes y alergias: NO debe borrarlos con ''
        observaciones_put = self._construir_texto_extenso(
            'OBSERVACIONES ACTUALIZADAS VÍA PUT',
            5300,
        )
        res_put_parcial_omitido = cliente_admin.put(
            f'/api/historia_clinicas/{id_historia}/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'observaciones': observaciones_put,
                'estado': True,
                'id_paciente': paciente.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_put_parcial_omitido.status_code, status.HTTP_200_OK)
        cuerpo_put = res_put_parcial_omitido.json()
        self.assertEqual(cuerpo_put['antecedentes'], antecedentes_inicial)
        self.assertEqual(cuerpo_put['alergias'], alergias_inicial)
        self.assertEqual(cuerpo_put['observaciones'], observaciones_put)

        historia_bd = HistoriaClinicas.objects.get(pk=id_historia)
        self.assertEqual(historia_bd.antecedentes, antecedentes_inicial)
        self.assertEqual(historia_bd.alergias, alergias_inicial)
        self.assertEqual(historia_bd.observaciones, observaciones_put)

        # 3. PATCH omitiendo antecedentes y observaciones: conserva ambos intactos
        alergias_patch = 'Alergia confirmada a penicilina, cefalosporinas y metamizol.'
        res_patch_omitido = cliente_admin.patch(
            f'/api/historia_clinicas/{id_historia}/',
            {'alergias': alergias_patch},
            format='json',
        )
        self.assertEqual(res_patch_omitido.status_code, status.HTTP_200_OK)
        historia_bd.refresh_from_db()
        self.assertEqual(historia_bd.antecedentes, antecedentes_inicial)
        self.assertEqual(historia_bd.alergias, alergias_patch)
        self.assertEqual(historia_bd.observaciones, observaciones_put)

        # 4. PUT enviando explícitamente '' en observaciones y null en alergias:
        #    sí limpia ambos a '' (nunca NULL), mientras antecedentes omitido se conserva intacto
        res_put_vacio_y_null = cliente_admin.put(
            f'/api/historia_clinicas/{id_historia}/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'alergias': None,
                'observaciones': '',
                'estado': True,
                'id_paciente': paciente.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_put_vacio_y_null.status_code, status.HTTP_200_OK)
        historia_bd.refresh_from_db()
        self.assertEqual(historia_bd.antecedentes, antecedentes_inicial)
        self.assertEqual(historia_bd.alergias, '')
        self.assertEqual(historia_bd.observaciones, '')
        self.assertIsNotNone(historia_bd.alergias)
        self.assertIsNotNone(historia_bd.observaciones)

    def test_dataerror_capturado_fuera_de_transaction_atomic_con_rollback_completo_sin_truncar(self):
        from django.db import DataError, transaction

        cliente_admin = self._cliente_autenticado(self.admin_norte)
        texto_largo = self._construir_texto_extenso('ANTECEDENTES SIN TRUNCAR', 900)

        # 1. En POST: si ocurre DataError dentro de transaction.atomic(), se revierte todo
        paciente_post_fallido = self._crear_paciente(
            id_paciente=523,
            nombre='Ernesto',
            apellido='Mora',
            documento='2523',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        conteo_inicial = HistoriaClinicas.objects.count()

        def fallo_create_con_escritura_previa(*args, **kwargs):
            # Verificamos que estamos dentro de un bloque transaction.atomic() activo
            self.assertTrue(transaction.get_connection().in_atomic_block)
            HistoriaClinicas.objects.create(
                fecha_apertura=self.ahora_fijo,
                antecedentes='Fila intermedia que debe revertirse en el rollback',
                alergias='',
                observaciones='',
                estado=True,
                id_paciente=paciente_post_fallido,
            )
            raise DataError('value too long for type character varying(200)')

        with patch.object(
            HistoriaClinicasSerializer,
            'save',
            side_effect=fallo_create_con_escritura_previa,
        ):
            res_post_err = cliente_admin.post(
                '/api/historia_clinicas/',
                {
                    'fecha_apertura': self.ahora_fijo.isoformat(),
                    'antecedentes': texto_largo,
                    'alergias': 'Niega alergias',
                    'observaciones': 'Observación extensa',
                    'estado': True,
                    'id_paciente': paciente_post_fallido.id_paciente,
                },
                format='json',
            )

        self.assertEqual(res_post_err.status_code, status.HTTP_409_CONFLICT)
        cuerpo_err = res_post_err.json()
        self.assertIn('sin truncar', cuerpo_err['detail'].lower())
        # Rollback completo comprobado: ni fila intermedia ni fila truncada a 200 caracteres
        self.assertEqual(HistoriaClinicas.objects.count(), conteo_inicial)
        self.assertFalse(
            HistoriaClinicas.objects.filter(id_paciente=paciente_post_fallido).exists()
        )

        # 2. En PATCH: escritura parcial previa dentro del bloque atómico se revierte por completo
        antecedentes_original = self.historia_norte.antecedentes
        observaciones_original = self.historia_norte.observaciones

        def fallo_update_con_mutacion_previa(*args, **kwargs):
            self.assertTrue(transaction.get_connection().in_atomic_block)
            HistoriaClinicas.objects.filter(
                pk=self.historia_norte.id_historia_clinica
            ).update(observaciones='Mutación intermedia no confirmada')
            raise DataError('value too long for type character varying(200)')

        with patch.object(
            HistoriaClinicasSerializer,
            'save',
            side_effect=fallo_update_con_mutacion_previa,
        ):
            res_patch_err = cliente_admin.patch(
                f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                {'antecedentes': texto_largo},
                format='json',
            )

        self.assertEqual(res_patch_err.status_code, status.HTTP_409_CONFLICT)
        # La conexión queda limpia fuera de transaction.atomic() y los datos previos intactos
        self.historia_norte.refresh_from_db()
        self.assertEqual(self.historia_norte.antecedentes, antecedentes_original)
        self.assertEqual(self.historia_norte.observaciones, observaciones_original)

    def test_post_sin_campos_clinicos_guarda_cadenas_vacias_y_normaliza_null_antiguo(self):
        from .views import HistoriaClinicasViewSet

        cliente_admin = self._cliente_autenticado(self.admin_norte)
        paciente = self._crear_paciente(
            id_paciente=525,
            nombre='Gustavo',
            apellido='Ríos',
            documento='2525',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )

        # 1. POST sin enviar antecedentes, alergias ni observaciones
        res_post = cliente_admin.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'estado': True,
                'id_paciente': paciente.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        cuerpo_post = res_post.json()
        id_historia = cuerpo_post['id_historia_clinica']

        # 2. Comprobar respuesta JSON: existen los tres como '' y nunca None
        for campo in ('antecedentes', 'alergias', 'observaciones'):
            self.assertIn(campo, cuerpo_post)
            self.assertIsNotNone(cuerpo_post[campo])
            self.assertEqual(cuerpo_post[campo], '')

        # 3. Comprobar valores almacenados vía ORM y consulta SQL directa (no NULL)
        historia_bd = HistoriaClinicas.objects.get(pk=id_historia)
        for campo in ('antecedentes', 'alergias', 'observaciones'):
            valor_orm = getattr(historia_bd, campo)
            self.assertIsNotNone(valor_orm)
            self.assertEqual(valor_orm, '')

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT antecedentes, alergias, observaciones '
                'FROM historia_clinicas WHERE id_historia_clinica = %s',
                [id_historia],
            )
            fila_sql = cursor.fetchone()
        self.assertEqual(fila_sql, ('', '', ''))

        # 4. Comprobar normalización de un registro antiguo con valores NULL al actualizar
        instancia_legado = HistoriaClinicas.objects.get(pk=id_historia)
        instancia_legado.antecedentes = None
        instancia_legado.alergias = None

        # Representación directa normaliza None -> ''
        datos_legado = HistoriaClinicasSerializer(instancia_legado).data
        self.assertEqual(datos_legado['antecedentes'], '')
        self.assertEqual(datos_legado['alergias'], '')

        # Al actualizar vía PATCH omitiendo antecedentes y alergias sobre la instancia legado,
        # update() normaliza los None antiguos a '' y los persiste sin error NOT NULL
        with patch.object(
            HistoriaClinicasViewSet,
            'get_object',
            return_value=instancia_legado,
        ):
            res_patch_legado = cliente_admin.patch(
                f'/api/historia_clinicas/{id_historia}/',
                {'observaciones': 'Evolución registrada sobre fila histórica'},
                format='json',
            )

        self.assertEqual(res_patch_legado.status_code, status.HTTP_200_OK)
        cuerpo_patch = res_patch_legado.json()
        self.assertEqual(cuerpo_patch['antecedentes'], '')
        self.assertEqual(cuerpo_patch['alergias'], '')
        self.assertEqual(
            cuerpo_patch['observaciones'],
            'Evolución registrada sobre fila histórica',
        )

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT antecedentes, alergias, observaciones '
                'FROM historia_clinicas WHERE id_historia_clinica = %s',
                [id_historia],
            )
            fila_actualizada = cursor.fetchone()
        self.assertEqual(
            fila_actualizada,
            ('', '', 'Evolución registrada sobre fila histórica'),
        )


class IntegracionCompletaHistoriaClinicaEtapa32Tests(BaseTablasHistoriaEnMemoriaTestCase):
    """
    Pruebas aisladas de Etapa 3.2 en SQLite `:memory:` con mocks (cero llamadas reales
    a Gemini, Cloudinary, PostgreSQL o Render).

    LIMITACIÓN DOCUMENTADA DE SQLITE EN PRUEBAS:
    - SQLite en memoria valida contratos JSON, reglas clínicas, inmutabilidad, orden de
      validación y rollback transaccional (`transaction.atomic()`), pero NO ejecuta bloqueos
      reales de fila `SELECT ... FOR UPDATE` ni demuestra contención concurrente real entre
      conexiones simultáneas en PostgreSQL.
    """

    def _construir_pdf_valido_bytes(self, num_paginas=1):
        writer = PdfWriter()
        for _ in range(num_paginas):
            writer.add_blank_page(width=595, height=842)
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def _simular_respuesta_genai(self, payload_dict, finish_reason='STOP'):
        texto = json.dumps(payload_dict, ensure_ascii=False)
        parte = SimpleNamespace(text=texto, thought=False)
        candidato = SimpleNamespace(
            finish_reason=finish_reason,
            content=SimpleNamespace(parts=[parte]),
        )
        return SimpleNamespace(
            text=texto,
            candidates=[candidato],
            prompt_feedback=SimpleNamespace(block_reason=None),
        )

    def _texto_clinico_largo(self, titulo, longitud_minima=5200):
        base = (
            f'{titulo}: Paciente geriátrico en seguimiento multidisciplinario integral, '
            'valoración funcional Barthel y Lawton, control nutricional hiposódico y '
            'vigilancia periódica por geriatría.'
        )
        repeticiones = (longitud_minima // len(base)) + 2
        resultado = '\n\n'.join(f'[{i + 1}] {base}' for i in range(repeticiones))
        self.assertGreater(len(resultado), longitud_minima)
        return resultado

    @patch('core.views.subir_documento')
    @patch('core.services.gemini_service.genai.Client')
    def test_carga_inicial_pdf_guarda_textos_largos_vacios_referencias_y_sin_alertas_por_ausencia(
        self,
        mock_genai_client,
        mock_subir_doc,
    ):
        paciente = self._crear_paciente(
            id_paciente=560,
            nombre='Herminia',
            apellido='Salazar',
            documento='2560',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        self.assertFalse(HistoriaClinicas.objects.filter(id_paciente=paciente).exists())
        self.assertFalse(
            DocumentosHistoriaClinica.objects.filter(id_paciente=paciente).exists()
        )

        antecedentes_largos = self._texto_clinico_largo(
            'ANTECEDENTES PATOLÓGICOS Y FARMACOLÓGICOS',
            5300,
        )
        observaciones_largas = self._texto_clinico_largo(
            'OBSERVACIONES Y PLAN DE CUIDADO GERIÁTRICO',
            5150,
        )
        rangos_explicitos = {
            'sistolica_min': None,
            'sistolica_max': None,
            'diastolica_min': None,
            'diastolica_max': None,
            'fc_min': None,
            'fc_max': 85.0,
            'fr_min': None,
            'fr_max': None,
            'temp_min': None,
            'temp_max': None,
            'sat_min': 88.0,
            'sat_max': 92.0,
            'resumen_condicion': 'Meta explícita EPOC: mantener SpO2 entre 88% y 92% y FC <= 85 lpm.',
        }
        payload_inicial = {
            'documento_legible': True,
            'motivo_ilegible': '',
            'antecedentes': antecedentes_largos,
            'alergias': '',
            'observaciones': observaciones_largas,
            'tiene_mediciones_signos_vitales': True,
            'signos_vitales_medidos': {
                'presion_sistolica': 132.0,
                'presion_diastolica': 78.0,
                'frecuencia_cardiaca': 74.0,
                'frecuencia_respiratoria': None,
                'temperatura': None,
                'saturacion_oxigeno': 90.0,
                'peso': 61.5,
                'detalle_medicion': 'TA 132/78 mmHg, FC 74 lpm, SpO2 90%.',
            },
            'tiene_referencias_explicitas': True,
            'rangos_vitales': rangos_explicitos,
        }

        instancia_genai = MagicMock()
        instancia_genai.models.generate_content.return_value = self._simular_respuesta_genai(
            payload_inicial
        )
        mock_genai_client.return_value = instancia_genai
        mock_subir_doc.return_value = {
            'secure_url': 'https://res.cloudinary.com/test-cloud-local/raw/upload/inicial_560.pdf',
            'public_id': 'geriapp/documentos_historia_clinica/inicial_560.pdf',
            'asset_id': '0123456789abcdef0123456789abcdef',
        }

        archivo_pdf = SimpleUploadedFile(
            'historia_inicial.pdf',
            self._construir_pdf_valido_bytes(),
            content_type='application/pdf',
        )
        cliente_admin = self._cliente_autenticado(self.admin_norte)

        with (
            patch.dict(
                'os.environ',
                {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
            ),
            patch.object(SignosVitales.objects, 'create') as mock_crear_signo,
        ):
            res = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente.id_paciente,
                    'archivo': archivo_pdf,
                    'nombre_archivo': 'historia_inicial.pdf',
                    'descripcion': 'Carga inicial completa',
                    'estado': True,
                },
                format='multipart',
            )
            mock_crear_signo.assert_not_called()

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        cuerpo = res.json()
        self.assertTrue(cuerpo['estado'])
        self.assertEqual(
            cuerpo['archivo'],
            'https://res.cloudinary.com/test-cloud-local/raw/upload/inicial_560.pdf',
        )
        self.assertNotIn('ia_error', cuerpo)
        self.assertIsNotNone(cuerpo['rangos_vitales_json'])
        self.assertEqual(cuerpo['rangos_vitales_json']['sat_min'], 88.0)
        self.assertEqual(cuerpo['rangos_vitales_json']['sat_max'], 92.0)

        historias = list(HistoriaClinicas.objects.filter(id_paciente=paciente))
        self.assertEqual(len(historias), 1)
        historia = historias[0]
        self.assertTrue(historia.estado)
        self.assertEqual(historia.antecedentes, antecedentes_largos)
        self.assertEqual(historia.alergias, '')
        self.assertIsNotNone(historia.alergias)
        self.assertEqual(historia.observaciones, observaciones_largas)
        self.assertEqual(historia.rangos_vitales_json['fc_max'], 85.0)

        # Evaluador: sin alertas por mediciones ausentes; sí alerta ante desviación real
        bitacora_mem = Bitacora(id_bitacora=1, id_paciente=paciente)
        signo_parcial_en_rango = SignosVitales(
            id_bitacora=bitacora_mem,
            presion_sistolica='',
            presion_diastolica=None,
            frecuencia_cardiaca='76',
            frecuencia_respiratoria='',
            temperatura=None,
            saturacion_oxigeno='90',
        )
        self.assertIsNone(evaluar_rangos_signos_vitales(signo_parcial_en_rango))

        signo_fuera_rango = SignosVitales(
            id_bitacora=bitacora_mem,
            frecuencia_cardiaca='94',
            saturacion_oxigeno='96',
        )
        alerta = evaluar_rangos_signos_vitales(signo_fuera_rango)
        self.assertIsNotNone(alerta)
        self.assertIn('Frecuencia cardíaca elevada', alerta)
        self.assertIn('Saturación de oxígeno elevada', alerta)

    @patch('core.views.subir_documento')
    @patch('core.services.gemini_service.genai.Client')
    def test_reemplazo_limpia_campos_vacios_conserva_negaciones_historicos_fecha_apertura_y_aisla_evaluador(
        self,
        mock_genai_client,
        mock_subir_doc,
    ):
        paciente = self._crear_paciente(
            id_paciente=561,
            nombre='Ignacio',
            apellido='Peralta',
            documento='2561',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        AsignacionPacienteCuidador.objects.create(
            id_paciente=paciente,
            id_usuario=self.cuidador_norte,
            fecha_inicio=self.ahora_fijo - timedelta(hours=1),
            fecha_fin=self.ahora_fijo + timedelta(hours=5),
            estado='Activo',
            observaciones='Turno vigente para consulta Android',
        )

        fecha_apertura_original = dt_colombia(2025, 3, 15, 9, 30, 0)
        rangos_previos = {
            'sistolica_min': 110.0,
            'sistolica_max': 135.0,
            'diastolica_min': 65.0,
            'diastolica_max': 85.0,
            'fc_min': 55.0,
            'fc_max': 85.0,
            'fr_min': 12.0,
            'fr_max': 20.0,
            'temp_min': 36.0,
            'temp_max': 37.2,
            'sat_min': 88.0,
            'sat_max': 92.0,
            'resumen_condicion': 'Meta clínica histórica previa.',
        }
        historia_inicial = HistoriaClinicas.objects.create(
            id_paciente=paciente,
            fecha_apertura=fecha_apertura_original,
            antecedentes='Antecedentes extensos de versión 1 que deben limpiarse si el nuevo PDF viene vacío.',
            alergias='Alergia previa a betalactámicos.',
            observaciones='Observaciones previas versión 1.',
            estado=True,
            rangos_vitales_json=dict(rangos_previos),
        )
        doc_inicial = DocumentosHistoriaClinica.objects.create(
            id_paciente=paciente,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/version_1.pdf',
            nombre_archivo='version_1.pdf',
            descripcion='Documento inicial',
            estado=True,
        )

        # El nuevo PDF devuelve antecedentes='', negación explícita en alergias, nuevas observaciones
        # y NO contiene referencias explícitas (rangos_vitales=None).
        payload_reemplazo = {
            'documento_legible': True,
            'motivo_ilegible': '',
            'antecedentes': '',
            'alergias': 'Niega alergias medicamentosas o alimentarias conocidas.',
            'observaciones': 'Evolución geriátrica actualizada en nueva valoración integral.',
            'tiene_mediciones_signos_vitales': False,
            'signos_vitales_medidos': None,
            'tiene_referencias_explicitas': False,
            'rangos_vitales': None,
        }
        instancia_genai = MagicMock()
        instancia_genai.models.generate_content.return_value = self._simular_respuesta_genai(
            payload_reemplazo
        )
        mock_genai_client.return_value = instancia_genai
        mock_subir_doc.return_value = {
            'secure_url': 'https://res.cloudinary.com/test-cloud-local/raw/upload/version_2.pdf',
            'public_id': 'geriapp/documentos_historia_clinica/version_2.pdf',
            'asset_id': 'abcdef0123456789abcdef0123456789',
        }

        pdf_reemplazo = SimpleUploadedFile(
            'version_2.pdf',
            self._construir_pdf_valido_bytes(),
            content_type='application/pdf',
        )
        cliente_admin = self._cliente_autenticado(self.admin_norte)

        with patch.dict(
            'os.environ',
            {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
        ):
            res = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente.id_paciente,
                    'archivo': pdf_reemplazo,
                    'nombre_archivo': 'version_2.pdf',
                    'descripcion': 'Reemplazo clínico autorizado',
                    'estado': True,
                },
                format='multipart',
            )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        cuerpo = res.json()
        self.assertIsNone(cuerpo['rangos_vitales_json'])
        self.assertTrue(cuerpo['estado'])

        # 1. El documento y la historia anteriores quedan preservados como históricos (estado=False)
        #    con todos sus textos, URL y rangos_vitales_json intactos.
        doc_inicial.refresh_from_db()
        self.assertFalse(doc_inicial.estado)
        self.assertEqual(
             str(doc_inicial.archivo),
            'https://res.cloudinary.com/test-cloud-local/raw/upload/version_1.pdf',
        )

        historia_inicial.refresh_from_db()
        self.assertFalse(historia_inicial.estado)
        self.assertEqual(
            historia_inicial.antecedentes,
            'Antecedentes extensos de versión 1 que deben limpiarse si el nuevo PDF viene vacío.',
        )
        self.assertEqual(historia_inicial.alergias, 'Alergia previa a betalactámicos.')
        self.assertEqual(historia_inicial.rangos_vitales_json, rangos_previos)

        # 2. La nueva historia vigente (estado=True) limpia antecedentes a '', conserva la negación literal,
        #    conserva fecha_apertura original y establece rangos_vitales_json=None.
        vigentes = list(HistoriaClinicas.objects.filter(id_paciente=paciente, estado=True))
        self.assertEqual(len(vigentes), 1)
        nueva_vigente = vigentes[0]
        self.assertNotEqual(
            nueva_vigente.id_historia_clinica,
            historia_inicial.id_historia_clinica,
        )
        self.assertEqual(nueva_vigente.fecha_apertura, historia_inicial.fecha_apertura)
        self.assertEqual(nueva_vigente.antecedentes, '')
        self.assertEqual(
            nueva_vigente.alergias,
            'Niega alergias medicamentosas o alimentarias conocidas.',
        )
        self.assertEqual(
            nueva_vigente.observaciones,
            'Evolución geriátrica actualizada en nueva valoración integral.',
        )
        self.assertIsNone(nueva_vigente.rangos_vitales_json)

        # 3. Evaluador de alertas: como la historia vigente tiene rangos_vitales_json=None,
        #    NUNCA utiliza los rangos de la historia histórica (estado=False).
        bitacora_mem = Bitacora(id_bitacora=2, id_paciente=paciente)
        signo_que_alertaria_con_historico = SignosVitales(
            id_bitacora=bitacora_mem,
            presion_sistolica='155',
            frecuencia_cardiaca='96',
            saturacion_oxigeno='98',
        )
        self.assertIsNone(
            evaluar_rangos_signos_vitales(signo_que_alertaria_con_historico)
        )

        # 4. Cuidador en Android ve únicamente el registro y PDF vigentes con contrato JSON intacto
        cliente_cuidador = self._cliente_autenticado(self.cuidador_norte)
        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            res_h_cuidador = cliente_cuidador.get(
                f'/api/historia_clinicas/?id_paciente={paciente.id_paciente}'
            )
            self.assertEqual(res_h_cuidador.status_code, status.HTTP_200_OK)
            lista_h = res_h_cuidador.json()
            self.assertEqual(len(lista_h), 1)
            self.assertEqual(
                lista_h[0]['id_historia_clinica'],
                nueva_vigente.id_historia_clinica,
            )
            self.assertEqual(lista_h[0]['antecedentes'], '')
            self.assertEqual(
                lista_h[0]['alergias'],
                'Niega alergias medicamentosas o alimentarias conocidas.',
            )

            res_d_cuidador = cliente_cuidador.get(
                f'/api/documentos_historia_clinica/?id_paciente={paciente.id_paciente}'
            )
            self.assertEqual(res_d_cuidador.status_code, status.HTTP_200_OK)
            lista_d = res_d_cuidador.json()
            self.assertEqual(len(lista_d), 1)
            self.assertEqual(lista_d[0]['id_documento'], cuerpo['id_documento'])
            self.assertTrue(lista_d[0]['estado'])

    @patch('core.views.subir_documento')
    @patch('core.views.extraer_historia_clinica_pdf')
    def test_anomalia_multiples_historias_vigentes_previas_normaliza_y_conserva_fecha_efectiva(
        self,
        mock_extraer,
        mock_subir_doc,
    ):
        paciente = self._crear_paciente(
            id_paciente=562,
            nombre='Jacinto',
            apellido='Olarte',
            documento='2562',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        fecha_antigua_descartada = dt_colombia(2023, 5, 10, 8, 0, 0)
        fecha_vigente_efectiva = dt_colombia(2025, 8, 22, 11, 45, 0)

        h_antigua = HistoriaClinicas.objects.create(
            id_paciente=paciente,
            fecha_apertura=fecha_antigua_descartada,
            antecedentes='Anomalía heredada 1',
            alergias='',
            observaciones='',
            estado=True,
            rangos_vitales_json={'fc_max': 75.0},
        )
        h_efectiva = HistoriaClinicas.objects.create(
            id_paciente=paciente,
            fecha_apertura=fecha_vigente_efectiva,
            antecedentes='Historia activa efectiva previa',
            alergias='Sulfa',
            observaciones='Vigente más reciente',
            estado=True,
            rangos_vitales_json={'fc_max': 88.0},
        )

        mock_extraer.return_value = {
            'documento_legible': True,
            'motivo_ilegible': '',
            'antecedentes': 'Historia consolidada tras reemplazo.',
            'alergias': '',
            'observaciones': 'Normalizada.',
            'tiene_mediciones_signos_vitales': False,
            'signos_vitales_medidos': None,
            'tiene_referencias_explicitas': False,
            'rangos_vitales': None,
        }
        mock_subir_doc.return_value = {
            'secure_url': 'https://res.cloudinary.com/test-cloud-local/raw/upload/norm_562.pdf',
            'asset_id': '11112222333344445555666677778888',
        }

        cliente_admin = self._cliente_autenticado(self.admin_norte)
        pdf_mock = SimpleUploadedFile(
            'consolidado.pdf',
            self._construir_pdf_valido_bytes(),
            content_type='application/pdf',
        )

        with self.assertLogs('core.views', level='WARNING') as capturados:
            res = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente.id_paciente,
                    'archivo': pdf_mock,
                    'nombre_archivo': 'consolidado.pdf',
                    'estado': True,
                },
                format='multipart',
            )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        h_antigua.refresh_from_db()
        h_efectiva.refresh_from_db()
        self.assertFalse(h_antigua.estado)
        self.assertFalse(h_efectiva.estado)
        self.assertEqual(h_antigua.rangos_vitales_json, {'fc_max': 75.0})
        self.assertEqual(h_efectiva.rangos_vitales_json, {'fc_max': 88.0})

        vigentes = list(HistoriaClinicas.objects.filter(id_paciente=paciente, estado=True))
        self.assertEqual(len(vigentes), 1)
        self.assertEqual(vigentes[0].fecha_apertura, h_efectiva.fecha_apertura)

        salida_logs = '\n'.join(capturados.output)
        self.assertIn('vigentes_previas=2', salida_logs)
        self.assertNotIn('562', salida_logs)
        self.assertNotIn('Jacinto', salida_logs)
        self.assertNotIn('Olarte', salida_logs)
        self.assertNotIn('consolidado.pdf', salida_logs)

    @patch('core.views.analizar_pdf_geriatrico')
    def test_consulta_historicos_sin_404_inmutabilidad_409_creacion_manual_y_procesar_pdf_intacto(
        self,
        mock_analizar_auxiliar,
    ):
        historia_historica = HistoriaClinicas.objects.create(
            id_paciente=self.paciente_norte_asignado,
            fecha_apertura=self.ahora_fijo - timedelta(days=120),
            antecedentes='Versión histórica archivada inmutable',
            alergias='Penicilina',
            observaciones='No modificable',
            estado=False,
            rangos_vitales_json={'sat_min': 90.0, 'sat_max': 95.0},
        )

        cliente_admin_norte = self._cliente_autenticado(self.admin_norte)
        cliente_admin_sur = self._cliente_autenticado(self.admin_sur)
        cliente_cuidador = self._cliente_autenticado(self.cuidador_norte)

        # 1. Admin consulta list por defecto (solo estado=True) y con ?incluir_historicos=true (ambos)
        res_default = cliente_admin_norte.get(
            f'/api/historia_clinicas/?id_paciente={self.paciente_norte_asignado.id_paciente}'
        )
        self.assertEqual(res_default.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [h['id_historia_clinica'] for h in res_default.json()],
            [self.historia_norte.id_historia_clinica],
        )

        res_con_hist = cliente_admin_norte.get(
            f'/api/historia_clinicas/?id_paciente={self.paciente_norte_asignado.id_paciente}&incluir_historicos=true'
        )
        self.assertEqual(res_con_hist.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {h['id_historia_clinica'] for h in res_con_hist.json()},
            {
                self.historia_norte.id_historia_clinica,
                historia_historica.id_historia_clinica,
            },
        )

        # 2. Admin consulta detalle GET de historia histórica sin recibir 404
        res_detalle_hist = cliente_admin_norte.get(
            f'/api/historia_clinicas/{historia_historica.id_historia_clinica}/'
        )
        self.assertEqual(res_detalle_hist.status_code, status.HTTP_200_OK)
        self.assertFalse(res_detalle_hist.json()['estado'])
        self.assertEqual(
            res_detalle_hist.json()['antecedentes'],
            'Versión histórica archivada inmutable',
        )

        # Admin de otra sede sigue recibiendo 404 sobre histórico ajeno
        self.assertEqual(
            cliente_admin_sur.get(
                f'/api/historia_clinicas/{historia_historica.id_historia_clinica}/'
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # 3. Cuidador limitado siempre a historias vigentes de pacientes asignados
        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            self.assertEqual(
                cliente_cuidador.get(
                    '/api/historia_clinicas/?incluir_historicos=true'
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                cliente_cuidador.get(
                    f'/api/historia_clinicas/{historia_historica.id_historia_clinica}/'
                ).status_code,
                status.HTTP_404_NOT_FOUND,
            )

        # 4. Inmutabilidad de historias históricas (PUT y PATCH responden 409, no 404)
        self.assertEqual(
            cliente_admin_norte.patch(
                f'/api/historia_clinicas/{historia_historica.id_historia_clinica}/',
                {'observaciones': 'Intento de edición histórica', 'estado': True},
                format='json',
            ).status_code,
            status.HTTP_409_CONFLICT,
        )
        self.assertEqual(
            cliente_admin_norte.put(
                f'/api/historia_clinicas/{historia_historica.id_historia_clinica}/',
                {
                    'fecha_apertura': self.ahora_fijo.isoformat(),
                    'antecedentes': 'Intento PUT histórico',
                    'alergias': '',
                    'observaciones': '',
                    'estado': True,
                    'id_paciente': self.paciente_norte_asignado.id_paciente,
                },
                format='json',
            ).status_code,
            status.HTTP_409_CONFLICT,
        )
        historia_historica.refresh_from_db()
        self.assertFalse(historia_historica.estado)
        self.assertEqual(
            historia_historica.antecedentes,
            'Versión histórica archivada inmutable',
        )

        # 5. Inmutabilidad de documentos históricos (PUT y PATCH responden 409)
        self.assertEqual(
            cliente_admin_norte.patch(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/',
                {'descripcion': 'Intento editar doc histórico', 'estado': True},
                format='json',
            ).status_code,
            status.HTTP_409_CONFLICT,
        )
        self.assertEqual(
            cliente_admin_norte.put(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/',
                {
                    'id_paciente': self.paciente_norte_asignado.id_paciente,
                    'nombre_archivo': 'reactivado.pdf',
                    'descripcion': 'Intento PUT doc histórico',
                    'estado': True,
                },
                format='json',
            ).status_code,
            status.HTTP_409_CONFLICT,
        )
        self.doc_historico_norte.refresh_from_db()
        self.assertFalse(self.doc_historico_norte.estado)

        # 6. Bloqueo de creación manual duplicada (409) y creación manual inactiva (400)
        conteo_previo = HistoriaClinicas.objects.filter(
            id_paciente=self.paciente_norte_asignado
        ).count()
        res_post_duplicada = cliente_admin_norte.post(
            '/api/historia_clinicas/',
            {
                'fecha_apertura': self.ahora_fijo.isoformat(),
                'antecedentes': 'Segunda historia manual no permitida',
                'alergias': '',
                'observaciones': '',
                'estado': True,
                'id_paciente': self.paciente_norte_asignado.id_paciente,
            },
            format='json',
        )
        self.assertEqual(res_post_duplicada.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            HistoriaClinicas.objects.filter(
                id_paciente=self.paciente_norte_asignado
            ).count(),
            conteo_previo,
        )
        self.historia_norte.refresh_from_db()
        self.assertTrue(self.historia_norte.estado)

        paciente_sin_h = self._crear_paciente(
            id_paciente=563,
            nombre='Leonor',
            apellido='Daza',
            documento='2563',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        self.assertEqual(
            cliente_admin_norte.post(
                '/api/historia_clinicas/',
                {
                    'fecha_apertura': self.ahora_fijo.isoformat(),
                    'antecedentes': 'Historia manual directamente inactiva',
                    'estado': False,
                    'id_paciente': paciente_sin_h.id_paciente,
                },
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        # 7. Bloqueo de desactivación manual (estado=False) en vigentes vía PUT y PATCH (400)
        self.assertEqual(
            cliente_admin_norte.patch(
                f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                {'estado': False},
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            cliente_admin_norte.put(
                f'/api/historia_clinicas/{self.historia_norte.id_historia_clinica}/',
                {
                    'fecha_apertura': self.ahora_fijo.isoformat(),
                    'antecedentes': 'Intento desactivar historia vigente',
                    'alergias': '',
                    'observaciones': '',
                    'estado': False,
                    'id_paciente': self.paciente_norte_asignado.id_paciente,
                },
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.historia_norte.refresh_from_db()
        self.assertTrue(self.historia_norte.estado)

        self.assertEqual(
            cliente_admin_norte.patch(
                f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                {'estado': False},
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            cliente_admin_norte.put(
                f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/',
                {
                    'id_paciente': self.paciente_norte_asignado.id_paciente,
                    'nombre_archivo': 'vigente.pdf',
                    'descripcion': 'Intento desactivar vigente',
                    'estado': False,
                },
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.doc_vigente_norte.refresh_from_db()
        self.assertTrue(self.doc_vigente_norte.estado)

        # 8. ProcesarHistoriaPdfView se mantiene intacto fuera de esta integración
        mock_analizar_auxiliar.return_value = dict(RANGOS_MOCK_ETAPA_1)
        pdf_aux = SimpleUploadedFile(
            'auxiliar.pdf',
            self._construir_pdf_valido_bytes(),
            content_type='application/pdf',
        )
        res_aux = cliente_admin_norte.post(
            f'/api/procesar-historia-pdf/{self.paciente_norte_asignado.id_paciente}/',
            {'archivo': pdf_aux},
            format='multipart',
        )
        self.assertEqual(res_aux.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(res_aux.json().keys()),
            {'id_paciente', 'id_historia_clinica', 'rangos_vitales_json'},
        )

    @patch('core.views.eliminar_imagen')
    @patch('core.views.subir_documento')
    @patch('core.services.gemini_service.genai.Client')
    def test_errores_gemini_cloudinary_y_rollback_bd_preservan_vigente_y_emiten_logs_opacos(
        self,
        mock_genai_client,
        mock_subir_doc,
        mock_eliminar_cloud,
    ):
        paciente_privado = self._crear_paciente(
            id_paciente=588,
            nombre='ValeriaConfidencial',
            apellido='ApellidoSecreto',
            documento='99887766',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        historia_previa = HistoriaClinicas.objects.create(
            id_paciente=paciente_privado,
            fecha_apertura=dt_colombia(2025, 2, 10, 8, 0, 0),
            antecedentes='Antecedente clínico protegido original',
            alergias='Alergia protegida original',
            observaciones='Observación protegida original',
            estado=True,
            rangos_vitales_json=dict(RANGOS_MOCK_ETAPA_1),
        )
        doc_previo = DocumentosHistoriaClinica.objects.create(
            id_paciente=paciente_privado,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/protegido_original.pdf',
            nombre_archivo='protegido_original.pdf',
            descripcion='PDF vigente protegido',
            estado=True,
        )

        cliente_admin = self._cliente_autenticado(self.admin_norte)

        # 1. Archivo no PDF -> 400 sin llamar a Gemini ni Cloudinary
        archivo_txt = SimpleUploadedFile(
            'nota_valeria_confidencial.txt',
            b'Contenido texto plano no permitido',
            content_type='text/plain',
        )
        res_no_pdf = cliente_admin.post(
            '/api/documentos_historia_clinica/',
            {
                'id_paciente': paciente_privado.id_paciente,
                'archivo': archivo_txt,
                'nombre_archivo': 'nota_valeria_confidencial.txt',
                'estado': True,
            },
            format='multipart',
        )
        self.assertEqual(res_no_pdf.status_code, status.HTTP_400_BAD_REQUEST)
        mock_genai_client.assert_not_called()
        mock_subir_doc.assert_not_called()

        # 2. PDF ilegible (documento_legible=False) -> 400 sin subir a Cloudinary
        instancia_genai = MagicMock()
        mock_genai_client.return_value = instancia_genai
        instancia_genai.models.generate_content.return_value = self._simular_respuesta_genai({
            'documento_legible': False,
            'motivo_ilegible': 'Escaneo completamente en blanco.',
            'antecedentes': '',
            'alergias': '',
            'observaciones': '',
            'tiene_mediciones_signos_vitales': False,
            'signos_vitales_medidos': None,
            'tiene_referencias_explicitas': False,
            'rangos_vitales': None,
        })

        with patch.dict(
            'os.environ',
            {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
        ):
            res_ilegible = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente_privado.id_paciente,
                    'archivo': SimpleUploadedFile(
                        'ilegible_valeria.pdf',
                        self._construir_pdf_valido_bytes(),
                        content_type='application/pdf',
                    ),
                    'nombre_archivo': 'ilegible_valeria.pdf',
                    'estado': True,
                },
                format='multipart',
            )
        self.assertEqual(res_ilegible.status_code, status.HTTP_400_BAD_REQUEST)
        mock_subir_doc.assert_not_called()

        # 3. Respuesta truncada/incompleta de Gemini -> 502 sin subir a Cloudinary
        instancia_genai.models.generate_content.return_value = SimpleNamespace(
            text='{"documento_legible": true, "antecedentes": "Truncado...',
            candidates=[
                SimpleNamespace(
                    finish_reason='MAX_TOKENS',
                    content=SimpleNamespace(parts=[]),
                )
            ],
            prompt_feedback=SimpleNamespace(block_reason=None),
        )
        with patch.dict(
            'os.environ',
            {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
        ):
            res_truncado = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente_privado.id_paciente,
                    'archivo': SimpleUploadedFile(
                        'truncado_valeria.pdf',
                        self._construir_pdf_valido_bytes(),
                        content_type='application/pdf',
                    ),
                    'nombre_archivo': 'truncado_valeria.pdf',
                    'estado': True,
                },
                format='multipart',
            )
        self.assertEqual(res_truncado.status_code, status.HTTP_502_BAD_GATEWAY)
        mock_subir_doc.assert_not_called()

        # 4. Fallo de Cloudinary tras extracción válida -> 502, historia y PDF previos intactos
        payload_valido_sensible = {
            'documento_legible': True,
            'motivo_ilegible': '',
            'antecedentes': 'Texto clínico sensible que no debe filtrarse en logs',
            'alergias': 'Alergia sensible confidencial',
            'observaciones': 'Observación confidencial',
            'tiene_mediciones_signos_vitales': False,
            'signos_vitales_medidos': None,
            'tiene_referencias_explicitas': False,
            'rangos_vitales': None,
        }
        instancia_genai.models.generate_content.return_value = self._simular_respuesta_genai(
            payload_valido_sensible
        )
        mock_subir_doc.side_effect = RuntimeError(
            'Error de red con archivo historia_ValeriaConfidencial_99887766.pdf'
        )

        with (
            patch.dict(
                'os.environ',
                {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
            ),
            self.assertLogs('core.views', level='ERROR') as logs_cloud,
        ):
            res_cloud_err = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente_privado.id_paciente,
                    'archivo': SimpleUploadedFile(
                        'historia_ValeriaConfidencial.pdf',
                        self._construir_pdf_valido_bytes(),
                        content_type='application/pdf',
                    ),
                    'nombre_archivo': 'historia_ValeriaConfidencial.pdf',
                    'estado': True,
                },
                format='multipart',
            )
        self.assertEqual(res_cloud_err.status_code, status.HTTP_502_BAD_GATEWAY)

        # 5. Fallos simulados de persistencia en BD (DataError -> 409 y DatabaseError -> 500)
        #    después de subida a Cloudinary: rollback total en BD, cero eliminaciones en Cloudinary
        #    y logs estrictamente opacos sin PII ni textos clínicos.
        mock_subir_doc.side_effect = None
        mock_subir_doc.return_value = {
            'secure_url': 'https://res.cloudinary.com/test-cloud-local/raw/upload/ValeriaConfidencial_99887766.pdf',
            'public_id': 'geriapp/documentos_historia_clinica/ValeriaConfidencial_99887766',
            'asset_id': 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
        }

        with (
            patch.dict(
                'os.environ',
                {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
            ),
            patch.object(
                HistoriaClinicas.objects,
                'create',
                side_effect=DataError('value too long for Valeriaconfidencial'),
            ),
            self.assertLogs('core.views', level='ERROR') as logs_data_err,
        ):
            res_data_err = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente_privado.id_paciente,
                    'archivo': SimpleUploadedFile(
                        'historia_ValeriaConfidencial.pdf',
                        self._construir_pdf_valido_bytes(),
                        content_type='application/pdf',
                    ),
                    'nombre_archivo': 'historia_ValeriaConfidencial.pdf',
                    'estado': True,
                },
                format='multipart',
            )
        self.assertEqual(res_data_err.status_code, status.HTTP_409_CONFLICT)

        with (
            patch.dict(
                'os.environ',
                {'GEMINI_API_KEY': 'clave-ficticia-test', 'GEMINI_MODEL': 'gemini-3.8-flash'},
            ),
            patch.object(
                HistoriaClinicas.objects,
                'create',
                side_effect=DatabaseError('connection lost for patient 588 ValeriaConfidencial'),
            ),
            self.assertLogs('core.views', level='ERROR') as logs_db_err,
        ):
            res_db_err = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente_privado.id_paciente,
                    'archivo': SimpleUploadedFile(
                        'historia_ValeriaConfidencial.pdf',
                        self._construir_pdf_valido_bytes(),
                        content_type='application/pdf',
                    ),
                    'nombre_archivo': 'historia_ValeriaConfidencial.pdf',
                    'estado': True,
                },
                format='multipart',
            )
        self.assertEqual(res_db_err.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Rollback completo verificado: historia y PDF originales siguen vigentes e intactos
        mock_eliminar_cloud.assert_not_called()
        historia_previa.refresh_from_db()
        doc_previo.refresh_from_db()
        self.assertTrue(historia_previa.estado)
        self.assertEqual(
            historia_previa.antecedentes,
            'Antecedente clínico protegido original',
        )
        self.assertEqual(historia_previa.rangos_vitales_json, RANGOS_MOCK_ETAPA_1)
        self.assertTrue(doc_previo.estado)
        self.assertEqual(
            HistoriaClinicas.objects.filter(id_paciente=paciente_privado).count(),
            1,
        )
        self.assertEqual(
            DocumentosHistoriaClinica.objects.filter(id_paciente=paciente_privado).count(),
            1,
        )

        # Verificación estricta de privacidad en logs: solo identificadores técnicos opacos
        todos_los_logs = '\n'.join(
            logs_cloud.output + logs_data_err.output + logs_db_err.output
        )
        self.assertIn('op=', todos_los_logs)
        self.assertIn('a1b2c3d4e5f60718293a4b5c6d7e8f90', todos_los_logs)
        for dato_prohibido in (
            '588',
            'ValeriaConfidencial',
            'Valeriaconfidencial',
            'ApellidoSecreto',
            '99887766',
            'historia_ValeriaConfidencial.pdf',
            'public_id',
            'secure_url',
            'Texto clínico sensible',
            'Alergia sensible confidencial',
            'Observación confidencial',
        ):
            self.assertNotIn(dato_prohibido, todos_los_logs)

    @patch('core.views.subir_documento')
    @patch('core.views.extraer_historia_clinica_pdf')
    def test_importacion_transaction_y_recorrido_real_atomico_en_create_reemplazo_y_perform_create(
        self,
        mock_extraer,
        mock_subir_doc,
    ):
        from django.db import transaction as django_transaction

        from . import views as core_views
        from .serializers import DocumentosHistoriaClinicaSerializer
        from .views import _reemplazar_documento_e_historia_atomico

        # 1. Comprobar que transaction está importado en el módulo core.views
        self.assertTrue(hasattr(core_views, 'transaction'))
        self.assertIs(core_views.transaction, django_transaction)

        cliente_admin = self._cliente_autenticado(self.admin_norte)

        # 2. Recorrer HistoriaClinicasViewSet.perform_create() verificando bloque atómico activo
        paciente_manual = self._crear_paciente(
            id_paciente=591,
            nombre='Mateo',
            apellido='Rincón',
            documento='2591',
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        estados_atomicos_perform_create = []
        save_original = HistoriaClinicasSerializer.save

        def _espiar_save_historia(instancia_serializer, *args, **kwargs):
            estados_atomicos_perform_create.append(connection.in_atomic_block)
            return save_original(instancia_serializer, *args, **kwargs)

        with patch.object(
            HistoriaClinicasSerializer,
            'save',
            autospec=True,
            side_effect=_espiar_save_historia,
        ):
            res_manual = cliente_admin.post(
                '/api/historia_clinicas/',
                {
                    'fecha_apertura': self.ahora_fijo.isoformat(),
                    'antecedentes': 'Creada por perform_create en bloque atómico',
                    'alergias': 'Ninguna',
                    'observaciones': 'Verificación atómica real',
                    'estado': True,
                    'id_paciente': paciente_manual.id_paciente,
                },
                format='json',
            )
        self.assertEqual(res_manual.status_code, status.HTTP_201_CREATED)
        self.assertEqual(estados_atomicos_perform_create, [True])

        # 3. Recorrer DocumentosHistoriaClinicaViewSet.create() -> _reemplazar_documento_e_historia_atomico()
        mock_extraer.return_value = {
            'documento_legible': True,
            'motivo_ilegible': '',
            'antecedentes': 'Extraído en create() dentro de transaction.atomic()',
            'alergias': 'Niega alergias.',
            'observaciones': 'Reemplazo vía endpoint real.',
            'tiene_mediciones_signos_vitales': False,
            'signos_vitales_medidos': None,
            'tiene_referencias_explicitas': False,
            'rangos_vitales': None,
        }
        mock_subir_doc.return_value = {
            'secure_url': 'https://res.cloudinary.com/test-cloud-local/raw/upload/atomico_591.pdf',
            'asset_id': 'fedcba9876543210fedcba9876543210',
        }

        estados_atomicos_reemplazo = []
        create_orm_original = HistoriaClinicas.objects.create

        def _espiar_create_historia(*args, **kwargs):
            estados_atomicos_reemplazo.append(connection.in_atomic_block)
            return create_orm_original(*args, **kwargs)

        pdf_1 = SimpleUploadedFile(
            'atomico_1.pdf',
            self._construir_pdf_valido_bytes(),
            content_type='application/pdf',
        )
        with patch.object(
            HistoriaClinicas.objects,
            'create',
            side_effect=_espiar_create_historia,
        ):
            res_doc = cliente_admin.post(
                '/api/documentos_historia_clinica/',
                {
                    'id_paciente': paciente_manual.id_paciente,
                    'archivo': pdf_1,
                    'nombre_archivo': 'atomico_1.pdf',
                    'estado': True,
                },
                format='multipart',
            )
        self.assertEqual(res_doc.status_code, status.HTTP_201_CREATED)
        self.assertEqual(estados_atomicos_reemplazo, [True])

        # 4. Invocación directa a _reemplazar_documento_e_historia_atomico() comprobando atomicidad
        pdf_2 = SimpleUploadedFile(
            'atomico_2.pdf',
            self._construir_pdf_valido_bytes(),
            content_type='application/pdf',
        )
        serializer_doc = DocumentosHistoriaClinicaSerializer(
            data={
                'id_paciente': paciente_manual.id_paciente,
                'archivo': pdf_2,
                'nombre_archivo': 'atomico_2.pdf',
                'estado': True,
            }
        )
        self.assertTrue(serializer_doc.is_valid(), serializer_doc.errors)

        with patch.object(
            HistoriaClinicas.objects,
            'create',
            side_effect=_espiar_create_historia,
        ):
            doc_directo, hist_directa = _reemplazar_documento_e_historia_atomico(
                paciente=paciente_manual,
                serializer_documento=serializer_doc,
                url_cloudinary='https://res.cloudinary.com/test-cloud-local/raw/upload/atomico_directo.pdf',
                datos_clinicos={
                    'antecedentes': 'Reemplazo directo atómico',
                    'alergias': '',
                    'observaciones': 'Versión 3 vigente',
                    'rangos_vitales_json': None,
                },
                operacion_id='00112233445566778899aabbccddeeff',
            )

        self.assertEqual(estados_atomicos_reemplazo, [True, True])
        self.assertTrue(doc_directo.estado)
        self.assertTrue(hist_directa.estado)
        self.assertEqual(
            HistoriaClinicas.objects.filter(
                id_paciente=paciente_manual,
                estado=True,
            ).count(),
            1,
        )
        self.assertEqual(
            DocumentosHistoriaClinica.objects.filter(
                id_paciente=paciente_manual,
                estado=True,
            ).count(),
            1,
        )

    def test_acceso_directo_detalle_documentos_historicos_y_vigentes_en_los_cuatro_roles(
        self,
    ):
        doc_historico_no_asignado = DocumentosHistoriaClinica.objects.create(
            id_paciente=self.paciente_norte_no_asignado,
            archivo='https://res.cloudinary.com/test-cloud-local/raw/upload/hist_no_asignado.pdf',
            nombre_archivo='hist_no_asignado.pdf',
            descripcion='Histórico de paciente no asignado al cuidador',
            estado=False,
        )

        cliente_admin_norte = self._cliente_autenticado(self.admin_norte)
        cliente_admin_sur = self._cliente_autenticado(self.admin_sur)
        cliente_cuidador = self._cliente_autenticado(self.cuidador_norte)
        cliente_encargado = self._cliente_autenticado(self.encargado_con_id_usuario_uno)
        cliente_superadmin = self._cliente_autenticado(self.superadmin)

        with patch('django.utils.timezone.now', return_value=self.ahora_fijo):
            # 1. Administrador: puede consultar documento histórico de su sede (200 OK),
            #    pero no el de otra sede (404 Not Found).
            res_admin_hist = cliente_admin_norte.get(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
            )
            self.assertEqual(res_admin_hist.status_code, status.HTTP_200_OK)
            self.assertEqual(
                res_admin_hist.json()['id_documento'],
                self.doc_historico_norte.id_documento,
            )
            self.assertFalse(res_admin_hist.json()['estado'])

            self.assertEqual(
                cliente_admin_sur.get(
                    f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
                ).status_code,
                status.HTTP_404_NOT_FOUND,
            )

            # 2. Cuidador: bloqueado al consultar por ID un documento histórico tanto de paciente
            #    asignado vigente (403 por PermisoHistoriaClinica.has_object_permission) como de
            #    paciente no asignado (404 por get_queryset).
            res_cuidador_hist_asignado = cliente_cuidador.get(
                f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
            )
            self.assertIn(
                res_cuidador_hist_asignado.status_code,
                (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
            )
            self.assertEqual(
                res_cuidador_hist_asignado.status_code,
                status.HTTP_403_FORBIDDEN,
            )

            res_cuidador_hist_no_asignado = cliente_cuidador.get(
                f'/api/documentos_historia_clinica/{doc_historico_no_asignado.id_documento}/'
            )
            self.assertEqual(
                res_cuidador_hist_no_asignado.status_code,
                status.HTTP_404_NOT_FOUND,
            )

            # 3. Cuidador: sí puede consultar por detalle el documento vigente de su paciente
            #    con asignación vigente (200 OK), y deja de verlo si la asignación vence (404).
            res_cuidador_vigente = cliente_cuidador.get(
                f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
            )
            self.assertEqual(res_cuidador_vigente.status_code, status.HTTP_200_OK)
            self.assertTrue(res_cuidador_vigente.json()['estado'])
            self.assertEqual(
                res_cuidador_vigente.json()['id_documento'],
                self.doc_vigente_norte.id_documento,
            )

            self.assertEqual(
                cliente_cuidador.get(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte_otro.id_documento}/'
                ).status_code,
                status.HTTP_404_NOT_FOUND,
            )

            # 4. Encargado y Superadministrador: continúan sin acceso clínico (403 Forbidden).
            for cliente_sin_acceso in (cliente_encargado, cliente_superadmin):
                self.assertEqual(
                    cliente_sin_acceso.get(
                        f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    cliente_sin_acceso.get(
                        f'/api/documentos_historia_clinica/{self.doc_historico_norte.id_documento}/'
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

            # Al vencer la asignación del cuidador, tampoco puede consultar por detalle el vigente
            self.asignacion_vigente_norte.fecha_fin = self.ahora_fijo - timedelta(minutes=1)
            self.asignacion_vigente_norte.save(update_fields=['fecha_fin'])
            self.assertEqual(
                cliente_cuidador.get(
                    f'/api/documentos_historia_clinica/{self.doc_vigente_norte.id_documento}/'
                ).status_code,
                status.HTTP_404_NOT_FOUND,
            )