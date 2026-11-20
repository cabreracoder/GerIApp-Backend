import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import F, Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from .models import AsignacionPacienteCuidador, AsignacionTurnoUsuario

logger = logging.getLogger(__name__)

ZONA_COLOMBIA = ZoneInfo("America/Bogota")
MARGEN_LLEGADA_ANTICIPADA = timedelta(hours=1)
TOLERANCIA_COMPARACION = timedelta(minutes=1)

# Estados que invalidan una fila para formar parte del rango de un bloque.
ESTADOS_TURNO_EXCLUIDOS_BLOQUE = (
    "inactivo",
    "inactiva",
    "cancelado",
    "cancelada",
    "anulado",
    "anulada",
)

# Estados que ya no están pendientes de ejecución/cierre.
ESTADOS_TURNO_NO_PENDIENTES = ESTADOS_TURNO_EXCLUIDOS_BLOQUE + (
    "finalizado",
    "finalizada",
    "completado",
    "completada",
)


def asegurar_aware_colombia(valor=None):
    """Convierte un datetime naive a zona horaria de Colombia o devuelve timezone.now()."""
    if valor is None:
        return timezone.now()

    if timezone.is_naive(valor):
        return timezone.make_aware(valor, ZONA_COLOMBIA)

    return valor


_asegurar_aware = asegurar_aware_colombia


def _normalizar_grupo(id_grupo):
    return (id_grupo or "").strip()


def _calcular_rango_con_turno(fecha_inicio, fecha_fin, turno):
    """Calcula (inicio, fin) aware en America/Bogota aplicando cruce de medianoche."""
    if not fecha_inicio or not fecha_fin or not turno:
        return None

    hora_inicio = turno.hora_inicio
    hora_fin = turno.hora_fin

    if not hora_inicio or not hora_fin:
        return None

    inicio_dt = timezone.make_aware(
        datetime.combine(fecha_inicio, hora_inicio),
        ZONA_COLOMBIA,
    )

    fecha_fin_real = (
        fecha_fin + timedelta(days=1)
        if hora_fin <= hora_inicio
        else fecha_fin
    )

    fin_dt = timezone.make_aware(
        datetime.combine(fecha_fin_real, hora_fin),
        ZONA_COLOMBIA,
    )

    return inicio_dt, fin_dt


def resolver_rango_bloque_asignacion(asignacion):
    """
    Calcula el (inicio_bloque, fin_bloque) en America/Bogota para una asignación dada.
    - Si tiene id_grupo_asignacion, usa min(fecha) y max(fecha) del grupo para ese cuidador,
      excluyendo filas inactivas/canceladas/anuladas (pero conservando filas Finalizado
      para mantener estable el inicio del bloque durante los días siguientes).
    - Si no tiene id_grupo_asignacion, usa únicamente la fecha de esa fila individual.
    """
    if not asignacion or not asignacion.fecha:
        return None

    turno = asignacion.id_turno if asignacion.id_turno_id else None
    id_grupo = _normalizar_grupo(asignacion.id_grupo_asignacion)

    if id_grupo and asignacion.id_usuario_id:
        fechas_grupo = [
            fecha
            for fecha in (
                AsignacionTurnoUsuario.objects
                .filter(id_usuario_id=asignacion.id_usuario_id)
                .annotate(
                    _grupo_limpio=Trim("id_grupo_asignacion"),
                    _estado_limpio=Lower(Trim("estado")),
                )
                .filter(_grupo_limpio=id_grupo)
                .exclude(_estado_limpio__in=ESTADOS_TURNO_EXCLUIDOS_BLOQUE)
                .values_list("fecha", flat=True)
            )
            if fecha is not None
        ]

        if fechas_grupo:
            fecha_min = min(fechas_grupo)
            fecha_max = max(fechas_grupo)
        else:
            fecha_min = asignacion.fecha
            fecha_max = asignacion.fecha
    else:
        fecha_min = asignacion.fecha
        fecha_max = asignacion.fecha

    if turno and turno.hora_inicio and turno.hora_fin:
        return _calcular_rango_con_turno(fecha_min, fecha_max, turno)

    # Respaldo defensivo cuando el turno no tiene hora_fin configurada.
    hora_inicio = (
        turno.hora_inicio
        if (turno and turno.hora_inicio)
        else time(0, 0, 0)
    )
    inicio_dt = timezone.make_aware(
        datetime.combine(fecha_min, hora_inicio),
        ZONA_COLOMBIA,
    )
    fin_dt = timezone.make_aware(
        datetime.combine(fecha_max, time(23, 59, 59)),
        ZONA_COLOMBIA,
    )
    return inicio_dt, fin_dt


_resolver_bloque_de_asignacion = resolver_rango_bloque_asignacion


def obtener_rango_bloque_turno_usuario(id_usuario, ahora=None):
    """
    Busca el turno activo/no finalizado actual del cuidador y devuelve
    (inicio_bloque, fin_bloque) en America/Bogota.

    - Si tiene id_grupo_asignacion: min(fecha) + hora_inicio hasta
      max(fecha) + hora_fin (+1 día si hora_fin <= hora_inicio).
    - Si no tiene grupo: usa la fecha de esa fila individual.
    - Devuelve None si el cuidador no tiene un turno vigente.
    """
    if not id_usuario:
        return None

    ahora_col = _asegurar_aware(ahora).astimezone(ZONA_COLOMBIA)
    hoy = ahora_col.date()
    ayer = hoy - timedelta(days=1)
    manana = hoy + timedelta(days=1)

    candidatas = list(
        AsignacionTurnoUsuario.objects
        .select_related("id_turno")
        .annotate(_estado_limpio=Lower(Trim("estado")))
        .filter(
            id_usuario_id=id_usuario,
            id_turno__isnull=False,
            id_turno__estado=True,
        )
        .exclude(_estado_limpio__in=ESTADOS_TURNO_NO_PENDIENTES)
        .order_by("fecha", "id_asignacion_turno_usuario")
    )

    if not candidatas:
        return None

    # 1. Turno cuya jornada diaria contiene exactamente el momento actual.
    for asignacion in candidatas:
        if asignacion.fecha not in (ayer, hoy):
            continue

        rango_dia = _calcular_rango_con_turno(
            asignacion.fecha,
            asignacion.fecha,
            asignacion.id_turno,
        )
        if rango_dia and rango_dia[0] <= ahora_col <= rango_dia[1]:
            return resolver_rango_bloque_asignacion(asignacion)

    # 2. Turno próximo que inicia en los siguientes 60 minutos (incluye cruce de medianoche).
    for asignacion in candidatas:
        if asignacion.fecha not in (hoy, manana):
            continue

        rango_dia = _calcular_rango_con_turno(
            asignacion.fecha,
            asignacion.fecha,
            asignacion.id_turno,
        )
        if (
            rango_dia
            and ahora_col < rango_dia[0]
            and (rango_dia[0] - ahora_col) <= MARGEN_LLEGADA_ANTICIPADA
        ):
            return resolver_rango_bloque_asignacion(asignacion)

    # 3. Turno programado para hoy que aún no termina (llegada anticipada del día).
    for asignacion in candidatas:
        if asignacion.fecha != hoy:
            continue

        rango_dia = _calcular_rango_con_turno(
            asignacion.fecha,
            asignacion.fecha,
            asignacion.id_turno,
        )
        if rango_dia and ahora_col <= rango_dia[1]:
            return resolver_rango_bloque_asignacion(asignacion)

    # 4. Bloque multi-día (id_grupo_asignacion) que cubre el momento actual
    # aunque la jornada del día ya haya cerrado o todavía esté entre días del bloque.
    grupos_revisados = set()
    for asignacion in candidatas:
        id_grupo = _normalizar_grupo(asignacion.id_grupo_asignacion)
        if not id_grupo or id_grupo in grupos_revisados:
            continue

        grupos_revisados.add(id_grupo)
        rango_bloque = resolver_rango_bloque_asignacion(asignacion)
        if rango_bloque and rango_bloque[0] <= ahora_col <= rango_bloque[1]:
            return rango_bloque

    return None


def filtrar_asignaciones_vigentes(queryset=None, ahora=None):
    """
    Filtra asignaciones paciente-cuidador activas y vigentes en el instante dado:
    estado == 'Activo' y fecha_inicio <= ahora <= fecha_fin.
    """
    qs = queryset if queryset is not None else AsignacionPacienteCuidador.objects.all()
    ahora_aware = _asegurar_aware(ahora)

    return qs.filter(
        estado__iexact="Activo",
        fecha_inicio__lte=ahora_aware,
        fecha_fin__gte=ahora_aware,
    )


def filtrar_asignaciones_en_rango(id_usuario, inicio, fin, queryset=None):
    """
    Filtra asignaciones paciente-cuidador de un cuidador cuyo periodo se solapa
    con [inicio, fin], sin exigir estado Activo (útil para resúmenes de turno
    en curso o ya cerrados). Evita mezclar turnos consecutivos en el límite exacto.
    """
    qs = queryset if queryset is not None else AsignacionPacienteCuidador.objects.all()
    inicio_aware = _asegurar_aware(inicio)
    fin_aware = _asegurar_aware(fin)

    if inicio_aware > fin_aware:
        return qs.none()

    if inicio_aware == fin_aware:
        return qs.filter(
            id_usuario_id=id_usuario,
            fecha_inicio__lte=fin_aware,
            fecha_fin__gte=inicio_aware,
        )

    return qs.filter(id_usuario_id=id_usuario).filter(
        Q(fecha_inicio__lt=fin_aware, fecha_fin__gt=inicio_aware)
        | Q(
            fecha_inicio=F("fecha_fin"),
            fecha_inicio__gte=inicio_aware,
            fecha_inicio__lte=fin_aware,
        )
    )


def es_ultimo_dia_pendiente_grupo(asignacion):
    """
    Indica si la asignación de turno cerrada es el último día pendiente de su
    id_grupo_asignacion (o un turno individual antiguo sin id_grupo_asignacion).
    """
    if not asignacion or not asignacion.id_usuario_id or not asignacion.fecha:
        return False

    id_grupo = _normalizar_grupo(asignacion.id_grupo_asignacion)

    if not id_grupo:
        return True

    quedan_dias_futuros = (
        AsignacionTurnoUsuario.objects
        .filter(
            id_usuario_id=asignacion.id_usuario_id,
            fecha__gt=asignacion.fecha,
        )
        .annotate(
            _grupo_limpio=Trim("id_grupo_asignacion"),
            _estado_limpio=Lower(Trim("estado")),
        )
        .filter(_grupo_limpio=id_grupo)
        .exclude(id_asignacion_turno_usuario=asignacion.id_asignacion_turno_usuario)
        .exclude(_estado_limpio__in=ESTADOS_TURNO_NO_PENDIENTES)
        .exists()
    )

    return not quedan_dias_futuros


def asignacion_paciente_pertenece_a_bloque(
    asignacion_paciente,
    inicio_bloque,
    fin_bloque,
):
    """
    Determina si una AsignacionPacienteCuidador corresponde al bloque de turno
    [inicio_bloque, fin_bloque], evitando afectar asignaciones de bloques pasados,
    bloques futuros o turnos adyacentes de otro bloque.
    """
    if (
        not asignacion_paciente
        or asignacion_paciente.fecha_inicio is None
        or asignacion_paciente.fecha_fin is None
    ):
        return False

    inicio_asig = _asegurar_aware(asignacion_paciente.fecha_inicio)
    fin_asig = _asegurar_aware(asignacion_paciente.fecha_fin)
    inicio_b = _asegurar_aware(inicio_bloque)
    fin_b = _asegurar_aware(fin_bloque)

    if inicio_asig > fin_asig or inicio_b > fin_b:
        return False

    # Compatibilidad con registros antiguos puntuales (fecha_inicio == fecha_fin).
    if inicio_asig == fin_asig:
        return (inicio_b - MARGEN_LLEGADA_ANTICIPADA) <= inicio_asig <= fin_b

    # 1. Coincide con la fecha/hora de cierre del bloque (incluye selección
    #    anticipada el primer día o pacientes añadidos en días intermedios).
    mismo_fin = abs(fin_asig - fin_b) <= TOLERANCIA_COMPARACION
    if (
        mismo_fin
        and inicio_asig <= fin_b
        and fin_asig > (inicio_b + TOLERANCIA_COMPARACION)
    ):
        return True

    # 2. Contenido dentro del bloque (con margen de llegada anticipada),
    #    sin invadir bloques pasados ni bloques futuros.
    inicio_dentro = (
        inicio_asig >= (inicio_b - MARGEN_LLEGADA_ANTICIPADA - TOLERANCIA_COMPARACION)
        and inicio_asig < (fin_b - TOLERANCIA_COMPARACION)
    )
    fin_dentro = (
        fin_asig > (inicio_b + TOLERANCIA_COMPARACION)
        and fin_asig <= (fin_b + TOLERANCIA_COMPARACION)
    )

    return inicio_dentro and fin_dentro


def finalizar_asignaciones_del_bloque(asignacion, fecha_cierre, queryset=None):
    """
    Desactiva únicamente las asignaciones activas de pacientes del cuidador
    que pertenecen al bloque de turno que está finalizando, acotando fecha_fin
    dentro de [fecha_inicio, fecha_fin] para no corromper rangos históricos ni futuros.
    """
    if not asignacion or not asignacion.id_usuario_id:
        return 0

    rango_bloque = resolver_rango_bloque_asignacion(asignacion)
    if not rango_bloque:
        logger.warning(
            "No se pudo resolver el rango del bloque para asignación %s "
            "(usuario=%s, grupo=%s). No se desactivan asignaciones de pacientes.",
            asignacion.id_asignacion_turno_usuario,
            asignacion.id_usuario_id,
            asignacion.id_grupo_asignacion,
        )
        return 0

    inicio_bloque, fin_bloque = rango_bloque
    cierre_aware = _asegurar_aware(fecha_cierre)

    qs_base = (
        queryset
        if queryset is not None
        else AsignacionPacienteCuidador.objects.all()
    )
    activas_usuario = list(
        qs_base.filter(
            id_usuario_id=asignacion.id_usuario_id,
            estado__iexact="Activo",
        )
    )

    desactivadas = 0
    for asignacion_paciente in activas_usuario:
        if not asignacion_paciente_pertenece_a_bloque(
            asignacion_paciente,
            inicio_bloque,
            fin_bloque,
        ):
            continue

        inicio_asig = _asegurar_aware(asignacion_paciente.fecha_inicio)
        fin_asig = _asegurar_aware(asignacion_paciente.fecha_fin)
        nueva_fecha_fin = max(inicio_asig, min(fin_asig, cierre_aware))

        asignacion_paciente.estado = "Inactivo"
        asignacion_paciente.fecha_fin = nueva_fecha_fin
        asignacion_paciente.save(update_fields=["estado", "fecha_fin"])
        desactivadas += 1

    return desactivadas
