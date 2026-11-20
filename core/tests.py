from datetime import date, datetime, time
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .asignaciones_vigencia import (
    ZONA_COLOMBIA,
    asignacion_paciente_pertenece_a_bloque,
    es_ultimo_dia_pendiente_grupo,
    filtrar_asignaciones_en_rango,
    filtrar_asignaciones_vigentes,
    finalizar_asignaciones_del_bloque,
    obtener_rango_bloque_turno_usuario,
    resolver_rango_bloque_asignacion,
)
from .consumers import cuidador_puede_ver_paciente
from .models import (
    AsignacionPacienteCuidador,
    AsignacionTurnoUsuario,
    CierreTurno,
    Pacientes,
    Roles,
    Sedes,
    Turnos,
    Usuarios,
)
from .permissions import ROL_CUIDADOR
from .serializers import (
    AsignacionPacienteCuidadorSerializer,
    AsignacionTurnoUsuarioSerializer,
)
from .views import CierreTurnoViewSet

MODELOS_TEST = [
    Sedes,
    Roles,
    Usuarios,
    Pacientes,
    Turnos,
    AsignacionTurnoUsuario,
    AsignacionPacienteCuidador,
    CierreTurno,
]


def dt_col(anio, mes, dia, hora=0, minuto=0, segundo=0):
    return datetime(anio, mes, dia, hora, minuto, segundo, tzinfo=ZONA_COLOMBIA)


class VigenciaAsignacionesBloqueTurnoTests(TestCase):
    """
    Pruebas de vigencia de asignaciones por bloque de turno sobre tablas
    aisladas (SQLite en memoria en ejecución de pruebas).
    """

    @classmethod
    def setUpClass(cls):
        cls._managed_original = {}
        cls._tablas_creadas = []
        tablas_existentes = set(connection.introspection.table_names())
        with connection.schema_editor() as editor:
            for modelo in MODELOS_TEST:
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
        self.rol_cuidador = Roles.objects.create(
            id_rol=ROL_CUIDADOR,
            nombre="Cuidador",
            descripcion="Cuidador de turno",
            estado=True,
        )
        self.cuidador_1 = Usuarios.objects.create(
            id_rol=self.rol_cuidador,
            tipo_documento="CC",
            numero_documento="10001",
            nombres="Angela",
            apellidos="Perez",
            correo="angela@test.local",
            fecha_ingreso=dt_col(2026, 1, 1, 8, 0),
            estado=True,
        )
        self.cuidador_2 = Usuarios.objects.create(
            id_rol=self.rol_cuidador,
            tipo_documento="CC",
            numero_documento="10002",
            nombres="Carlos",
            apellidos="Lopez",
            correo="carlos@test.local",
            fecha_ingreso=dt_col(2026, 1, 1, 8, 0),
            estado=True,
        )
        self.paciente_1 = self._crear_paciente("Maria", "Gomez", "20001")
        self.paciente_2 = self._crear_paciente("Jose", "Diaz", "20002")
        self.paciente_3 = self._crear_paciente("Elena", "Ruiz", "20003")
        self.paciente_4 = self._crear_paciente("Pedro", "Silva", "20004")

        self.turno_diurno = Turnos.objects.create(
            hora_inicio=time(7, 0, 0),
            hora_fin=time(19, 0, 0),
            estado=True,
            nombre="Diurno",
            descripcion="Turno diurno 12h",
        )
        self.turno_nocturno = Turnos.objects.create(
            hora_inicio=time(19, 0, 0),
            hora_fin=time(7, 0, 0),
            estado=True,
            nombre="Nocturno",
            descripcion="Turno nocturno 12h",
        )

    def _crear_paciente(self, nombre, apellido, documento):
        return Pacientes.objects.create(
            nombre=nombre,
            apellido=apellido,
            eps="EPS Test",
            sede="Principal",
            fecha_ingreso=dt_col(2026, 1, 1, 8, 0),
            habitacion=101,
            tipo_documento="CC",
            numero_documento=documento,
            fecha_nacimiento=date(1945, 5, 10),
            genero="F",
            cama=1,
            estado=True,
        )

    def _ejecutar_cierre_api(self, id_asignacion, momento_cierre, observaciones="Cierre OK"):
        request = self.factory.post(
            "/api/cierre_turno/",
            {
                "id_asignacion_turno_usuario": id_asignacion,
                "observaciones": observaciones,
            },
            format="json",
        )
        usuario_auth = SimpleNamespace(
            is_authenticated=True,
            usuario=self.cuidador_1,
            id_usuario=self.cuidador_1.id_usuario,
        )
        force_authenticate(request, user=usuario_auth)
        vista = CierreTurnoViewSet.as_view({"post": "create"})
        with patch("core.views.timezone.now", return_value=momento_cierre):
            return vista(request)

    def test_bloque_dos_dias_y_varios_dias_conserva_en_dia1_e_intermedio_y_cierra_en_ultimo_dia(self):
        grupo_3 = "GRP-3-DIAS"
        dia_1 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 23),
            estado="Asignado",
            id_grupo_asignacion=grupo_3,
        )
        dia_2 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 24),
            estado="Asignado",
            id_grupo_asignacion=grupo_3,
        )
        dia_3 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 25),
            estado="Asignado",
            id_grupo_asignacion=grupo_3,
        )

        # Rango completo del bloque de 3 días en America/Bogota.
        rango = obtener_rango_bloque_turno_usuario(
            self.cuidador_1.id_usuario,
            ahora=dt_col(2026, 11, 23, 8, 0),
        )
        self.assertEqual(rango, (dt_col(2026, 11, 23, 7, 0), dt_col(2026, 11, 25, 19, 0)))

        ap_1 = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 25, 19, 0),
            estado="Activo",
            observaciones="Bloque 3 días",
        )
        ap_2 = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_2,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 25, 19, 0),
            estado="Activo",
            observaciones="Bloque 3 días",
        )

        # Cierre del primer día -> conservar pacientes activos.
        resp_1 = self._ejecutar_cierre_api(
            dia_1.id_asignacion_turno_usuario,
            dt_col(2026, 11, 23, 18, 55),
        )
        self.assertEqual(resp_1.status_code, 201)
        dia_1.refresh_from_db()
        ap_1.refresh_from_db()
        ap_2.refresh_from_db()
        self.assertEqual(dia_1.estado, "Finalizado")
        self.assertEqual(ap_1.estado, "Activo")
        self.assertEqual(ap_2.estado, "Activo")
        self.assertEqual(ap_1.fecha_fin, dt_col(2026, 11, 25, 19, 0))

        # Entre día 1 y día 2 siguen vigentes.
        vigentes_noche = set(
            filtrar_asignaciones_vigentes(ahora=dt_col(2026, 11, 23, 21, 0))
            .filter(id_usuario=self.cuidador_1)
            .values_list("id_paciente_id", flat=True)
        )
        self.assertEqual(vigentes_noche, {self.paciente_1.id_paciente, self.paciente_2.id_paciente})

        # Cierre de día intermedio (día 2) -> conservar pacientes activos.
        resp_2 = self._ejecutar_cierre_api(
            dia_2.id_asignacion_turno_usuario,
            dt_col(2026, 11, 24, 18, 55),
        )
        self.assertEqual(resp_2.status_code, 201)
        ap_1.refresh_from_db()
        ap_2.refresh_from_db()
        self.assertEqual(ap_1.estado, "Activo")
        self.assertEqual(ap_2.estado, "Activo")

        # Cierre del último día (día 3) -> finalizar asignaciones del bloque.
        cierre_final = dt_col(2026, 11, 25, 18, 55)
        resp_3 = self._ejecutar_cierre_api(
            dia_3.id_asignacion_turno_usuario,
            cierre_final,
        )
        self.assertEqual(resp_3.status_code, 201)
        ap_1.refresh_from_db()
        ap_2.refresh_from_db()
        self.assertEqual(ap_1.estado, "Inactivo")
        self.assertEqual(ap_2.estado, "Inactivo")
        self.assertEqual(ap_1.fecha_fin, cierre_final)
        self.assertEqual(ap_2.fecha_fin, cierre_final)

        # Ya no aparecen como vigentes después del cierre del último día.
        self.assertFalse(
            filtrar_asignaciones_vigentes(ahora=dt_col(2026, 11, 25, 18, 56))
            .filter(id_usuario=self.cuidador_1)
            .exists()
        )

        # Nuevo bloque de 2 días permite nuevas asignaciones de forma limpia.
        grupo_2 = "GRP-2-DIAS"
        b2_d1 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 26),
            estado="Asignado",
            id_grupo_asignacion=grupo_2,
        )
        b2_d2 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 27),
            estado="Asignado",
            id_grupo_asignacion=grupo_2,
        )
        rango_b2 = obtener_rango_bloque_turno_usuario(
            self.cuidador_1.id_usuario,
            ahora=dt_col(2026, 11, 26, 7, 15),
        )
        self.assertEqual(rango_b2, (dt_col(2026, 11, 26, 7, 0), dt_col(2026, 11, 27, 19, 0)))
        self.assertFalse(es_ultimo_dia_pendiente_grupo(b2_d1))
        self.assertTrue(es_ultimo_dia_pendiente_grupo(b2_d2))

    def test_cierre_ultimo_dia_no_afecta_otros_bloques_pasados_futuros_ni_otro_cuidador(self):
        # Bloque 1 actual (Mon-Tue)
        AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 23),
            estado="Finalizado",
            id_grupo_asignacion="GRP-B1",
        )
        b1_d2 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 24),
            estado="Asignado",
            id_grupo_asignacion="GRP-B1",
        )
        # Bloque 2 futuro del mismo cuidador (Thu-Fri)
        AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 26),
            estado="Asignado",
            id_grupo_asignacion="GRP-B2",
        )
        AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 27),
            estado="Asignado",
            id_grupo_asignacion="GRP-B2",
        )

        ap_bloque_1 = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 24, 19, 0),
            estado="Activo",
            observaciones="Bloque 1",
        )
        ap_bloque_2_futuro = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_2,
            fecha_inicio=dt_col(2026, 11, 26, 7, 0),
            fecha_fin=dt_col(2026, 11, 27, 19, 0),
            estado="Activo",
            observaciones="Bloque 2 futuro",
        )
        ap_bloque_0_pasado = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_3,
            fecha_inicio=dt_col(2026, 11, 10, 7, 0),
            fecha_fin=dt_col(2026, 11, 12, 19, 0),
            estado="Activo",
            observaciones="Bloque 0 pasado sin inactivar",
        )
        ap_adyacente_nocturno = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_4,
            fecha_inicio=dt_col(2026, 11, 24, 18, 30),
            fecha_fin=dt_col(2026, 11, 26, 7, 0),
            estado="Activo",
            observaciones="Turno nocturno adyacente seleccionado anticipadamente",
        )
        ap_otro_cuidador = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_2,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 24, 19, 0),
            estado="Activo",
            observaciones="Otro cuidador mismo rango",
        )

        cierre_momento = dt_col(2026, 11, 24, 18, 55)
        resp = self._ejecutar_cierre_api(
            b1_d2.id_asignacion_turno_usuario,
            cierre_momento,
        )
        self.assertEqual(resp.status_code, 201)

        ap_bloque_1.refresh_from_db()
        ap_bloque_2_futuro.refresh_from_db()
        ap_bloque_0_pasado.refresh_from_db()
        ap_adyacente_nocturno.refresh_from_db()
        ap_otro_cuidador.refresh_from_db()

        # Solo el bloque 1 que finalizó fue desactivado.
        self.assertEqual(ap_bloque_1.estado, "Inactivo")
        self.assertEqual(ap_bloque_1.fecha_fin, cierre_momento)

        # Bloque futuro, bloque pasado, turno adyacente y otro cuidador permanecen intactos.
        self.assertEqual(ap_bloque_2_futuro.estado, "Activo")
        self.assertEqual(ap_bloque_2_futuro.fecha_inicio, dt_col(2026, 11, 26, 7, 0))
        self.assertEqual(ap_bloque_2_futuro.fecha_fin, dt_col(2026, 11, 27, 19, 0))

        self.assertEqual(ap_bloque_0_pasado.estado, "Activo")
        self.assertEqual(ap_bloque_0_pasado.fecha_fin, dt_col(2026, 11, 12, 19, 0))

        self.assertEqual(ap_adyacente_nocturno.estado, "Activo")
        self.assertEqual(ap_adyacente_nocturno.fecha_fin, dt_col(2026, 11, 26, 7, 0))

        self.assertEqual(ap_otro_cuidador.estado, "Activo")
        self.assertEqual(ap_otro_cuidador.fecha_fin, dt_col(2026, 11, 24, 19, 0))

    def test_asignaciones_sin_id_grupo_compatibilidad_antiguas_y_proteccion_multidia_y_futuras(self):
        sin_grupo = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 23),
            estado="Asignado",
            id_grupo_asignacion=None,
        )

        # Asignación del mismo día individual (debe finalizarse).
        ap_dia = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 23, 19, 0),
            estado="Activo",
            observaciones="Turno individual",
        )
        # Registro legado puntual (fecha_inicio == fecha_fin dentro del turno).
        ap_legado_puntual = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_2,
            fecha_inicio=dt_col(2026, 11, 23, 8, 30),
            fecha_fin=dt_col(2026, 11, 23, 8, 30),
            estado="Activo",
            observaciones="Registro antiguo puntual",
        )
        # Asignación multi-día que se extiende a días futuros (NO debe desactivarse al cerrar 1 día sin grupo).
        ap_multidia = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_3,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 25, 19, 0),
            estado="Activo",
            observaciones="Cubre varios días",
        )
        # Asignación futura (NO debe desactivarse).
        ap_futura = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_4,
            fecha_inicio=dt_col(2026, 11, 26, 7, 0),
            fecha_fin=dt_col(2026, 11, 28, 19, 0),
            estado="Activo",
            observaciones="Bloque futuro",
        )

        cierre_dt = dt_col(2026, 11, 23, 18, 55)
        resp = self._ejecutar_cierre_api(sin_grupo.id_asignacion_turno_usuario, cierre_dt)
        self.assertEqual(resp.status_code, 201)

        ap_dia.refresh_from_db()
        ap_legado_puntual.refresh_from_db()
        ap_multidia.refresh_from_db()
        ap_futura.refresh_from_db()

        self.assertEqual(ap_dia.estado, "Inactivo")
        self.assertEqual(ap_dia.fecha_fin, cierre_dt)

        self.assertEqual(ap_legado_puntual.estado, "Inactivo")
        self.assertEqual(ap_legado_puntual.fecha_fin, dt_col(2026, 11, 23, 8, 30))

        self.assertEqual(ap_multidia.estado, "Activo")
        self.assertEqual(ap_multidia.fecha_fin, dt_col(2026, 11, 25, 19, 0))

        self.assertEqual(ap_futura.estado, "Activo")
        self.assertEqual(ap_futura.fecha_fin, dt_col(2026, 11, 28, 19, 0))

    def test_turnos_nocturnos_cruzan_medianoche_y_zona_horaria_colombia(self):
        grupo_noche = "  GRP-NOCHE-1  "
        n1 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_nocturno,
            fecha=date(2026, 11, 23),
            estado="Asignado",
            id_grupo_asignacion=grupo_noche,
        )
        n2 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_nocturno,
            fecha=date(2026, 11, 24),
            estado="Asignado",
            id_grupo_asignacion="GRP-NOCHE-1",
        )

        # 02:00 hora Colombia del 24 nov = 07:00 UTC del 24 nov (en medio de la noche 1).
        en_madrugada_utc = datetime(2026, 11, 24, 7, 0, tzinfo=dt_timezone.utc)
        rango = obtener_rango_bloque_turno_usuario(
            self.cuidador_1.id_usuario,
            ahora=en_madrugada_utc,
        )
        self.assertEqual(rango, (dt_col(2026, 11, 23, 19, 0), dt_col(2026, 11, 25, 7, 0)))

        ap_noche = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 19, 0),
            fecha_fin=dt_col(2026, 11, 25, 7, 0),
            estado="Activo",
            observaciones="Bloque nocturno",
        )

        # Cierre de la noche 1 (24 nov 06:55 COL) -> conserva pacientes (noche 2 pendiente).
        resp_n1 = self._ejecutar_cierre_api(
            n1.id_asignacion_turno_usuario,
            dt_col(2026, 11, 24, 6, 55),
        )
        self.assertEqual(resp_n1.status_code, 201)
        ap_noche.refresh_from_db()
        self.assertEqual(ap_noche.estado, "Activo")

        # Cierre de la noche 2 (25 nov 06:55 COL) -> último día, finaliza asignación nocturna.
        cierre_n2 = dt_col(2026, 11, 25, 6, 55)
        resp_n2 = self._ejecutar_cierre_api(
            n2.id_asignacion_turno_usuario,
            cierre_n2,
        )
        self.assertEqual(resp_n2.status_code, 201)
        ap_noche.refresh_from_db()
        self.assertEqual(ap_noche.estado, "Inactivo")
        self.assertEqual(ap_noche.fecha_fin, cierre_n2)

    def test_estados_cancelado_y_cierre_tardio_no_extiende_fecha_fin(self):
        d1 = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 23),
            estado="Asignado",
            id_grupo_asignacion="GRP-CANCEL",
        )
        # Día 2 fue cancelado: día 1 es realmente el último día pendiente.
        AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 24),
            estado="Cancelado",
            id_grupo_asignacion="GRP-CANCEL",
        )

        self.assertEqual(
            resolver_rango_bloque_asignacion(d1),
            (dt_col(2026, 11, 23, 7, 0), dt_col(2026, 11, 23, 19, 0)),
        )
        self.assertTrue(es_ultimo_dia_pendiente_grupo(d1))

        ap = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 23, 19, 0),
            estado="Activo",
            observaciones="Cierre tardío",
        )

        # Cierre registrado al día siguiente (24 nov 09:00) -> no debe extender fecha_fin más allá de 23 nov 19:00.
        desactivadas = finalizar_asignaciones_del_bloque(
            asignacion=d1,
            fecha_cierre=dt_col(2026, 11, 24, 9, 0),
        )
        self.assertEqual(desactivadas, 1)
        ap.refresh_from_db()
        self.assertEqual(ap.estado, "Inactivo")
        self.assertEqual(ap.fecha_fin, dt_col(2026, 11, 23, 19, 0))

    def test_llegada_anticipada_cruzando_medianoche_y_filtrar_en_rango_sin_mezclar_limites(self):
        turno_madrugada = Turnos.objects.create(
            hora_inicio=time(0, 15, 0),
            hora_fin=time(8, 15, 0),
            estado=True,
            nombre="Madrugada",
            descripcion="Inicia 00:15",
        )
        AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=turno_madrugada,
            fecha=date(2026, 11, 24),
            estado="Asignado",
            id_grupo_asignacion="GRP-MAD",
        )

        # 23 nov 23:45 COL (30 min antes del turno del 24 nov 00:15).
        rango = obtener_rango_bloque_turno_usuario(
            self.cuidador_1.id_usuario,
            ahora=dt_col(2026, 11, 23, 23, 45),
        )
        self.assertEqual(rango, (dt_col(2026, 11, 24, 0, 15), dt_col(2026, 11, 24, 8, 15)))

        # Dos asignaciones consecutivas con límite exacto en 19:00:00 no deben mezclarse.
        ap_diurna = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=dt_col(2026, 11, 23, 7, 0),
            fecha_fin=dt_col(2026, 11, 23, 19, 0),
            estado="Inactivo",
            observaciones="Diurna",
        )
        ap_nocturna = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_2,
            fecha_inicio=dt_col(2026, 11, 23, 19, 0),
            fecha_fin=dt_col(2026, 11, 24, 7, 0),
            estado="Activo",
            observaciones="Nocturna",
        )

        en_nocturno = list(
            filtrar_asignaciones_en_rango(
                id_usuario=self.cuidador_1.id_usuario,
                inicio=dt_col(2026, 11, 23, 19, 0),
                fin=dt_col(2026, 11, 24, 7, 0),
            ).values_list("id_asignacion", flat=True)
        )
        self.assertEqual(en_nocturno, [ap_nocturna.id_asignacion])
        self.assertNotIn(ap_diurna.id_asignacion, en_nocturno)

    def test_serializers_y_consumer_websocket_coherencia_colombia(self):
        # Serializer de turno expone id_grupo_asignacion tal como lo consume Android.
        turno_asig = AsignacionTurnoUsuario.objects.create(
            id_usuario=self.cuidador_1,
            id_turno=self.turno_diurno,
            fecha=date(2026, 11, 23),
            estado="Asignado",
            id_grupo_asignacion="GRP-SERIAL",
        )
        datos_turno = AsignacionTurnoUsuarioSerializer(turno_asig).data
        self.assertEqual(datos_turno["id_grupo_asignacion"], "GRP-SERIAL")
        self.assertEqual(datos_turno["fecha"], "2026-11-23")

        # Validación de fechas en Colombia (naive vs aware -05:00).
        ser_valido = AsignacionPacienteCuidadorSerializer(
            data={
                "id_usuario": self.cuidador_1.id_usuario,
                "id_paciente": self.paciente_1.id_paciente,
                "fecha_inicio": "2026-11-23T07:00:00",
                "fecha_fin": "2026-11-23T08:00:00-05:00",
                "estado": "Activo",
                "observaciones": "Rango válido en Colombia",
            }
        )
        self.assertTrue(ser_valido.is_valid(), ser_valido.errors)

        ser_invalido = AsignacionPacienteCuidadorSerializer(
            data={
                "id_usuario": self.cuidador_1.id_usuario,
                "id_paciente": self.paciente_1.id_paciente,
                "fecha_inicio": "2026-11-23T19:00:00-05:00",
                "fecha_fin": "2026-11-23T07:00:00-05:00",
                "estado": "Activo",
                "observaciones": "Rango invertido",
            }
        )
        self.assertFalse(ser_invalido.is_valid())
        self.assertIn("fecha_fin", ser_invalido.errors)

        # Consumer WebSocket autoriza solo cuando la asignación está vigente.
        ahora_real = timezone.now()
        ap_ws = AsignacionPacienteCuidador.objects.create(
            id_usuario=self.cuidador_1,
            id_paciente=self.paciente_1,
            fecha_inicio=ahora_real - timezone.timedelta(hours=1),
            fecha_fin=ahora_real + timezone.timedelta(hours=2),
            estado="Activo",
            observaciones="Vigente WS",
        )
        usuario_ws = SimpleNamespace(is_authenticated=True, usuario=self.cuidador_1)
        self.assertTrue(
            async_to_sync(cuidador_puede_ver_paciente)(
                usuario_ws,
                self.paciente_1.id_paciente,
            )
        )

        # Al vencer o inactivar, el consumer deniega acceso.
        ap_ws.estado = "Inactivo"
        ap_ws.save(update_fields=["estado"])
        self.assertFalse(
            async_to_sync(cuidador_puede_ver_paciente)(
                usuario_ws,
                self.paciente_1.id_paciente,
            )
        )

    def test_asignacion_paciente_pertenece_a_bloque_helper_directo(self):
        inicio_b = dt_col(2026, 11, 23, 7, 0)
        fin_b = dt_col(2026, 11, 25, 19, 0)

        mismo = SimpleNamespace(fecha_inicio=dt_col(2026, 11, 23, 6, 30), fecha_fin=fin_b)
        futuro = SimpleNamespace(
            fecha_inicio=dt_col(2026, 11, 26, 7, 0),
            fecha_fin=dt_col(2026, 11, 28, 19, 0),
        )
        pasado = SimpleNamespace(
            fecha_inicio=dt_col(2026, 11, 10, 7, 0),
            fecha_fin=dt_col(2026, 11, 12, 19, 0),
        )
        self.assertTrue(asignacion_paciente_pertenece_a_bloque(mismo, inicio_b, fin_b))
        self.assertFalse(asignacion_paciente_pertenece_a_bloque(futuro, inicio_b, fin_b))
        self.assertFalse(asignacion_paciente_pertenece_a_bloque(pasado, inicio_b, fin_b))
