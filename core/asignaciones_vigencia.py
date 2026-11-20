from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import AsignacionPacienteCuidador, AsignacionTurnoUsuario

ZONA_COLOMBIA = ZoneInfo("America/Bogota")


def _asegurar_aware(valor=None):
    """Convierte un datetime naive a zona horaria de Colombia o devuelve timezone.now()."""
    if valor is None:
        return timezone.now()

    if timezone.is_naive(valor):
        return timezone.make_aware(valor, ZONA_COLOMBIA)

    return valor


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


def _resolver_bloque_de_asignacion(asignacion):
    """
    Calcula el (inicio_bloque, fin_bloque) en America/Bogota para una asignación dada.
    Si tiene id_grupo_asignacion, usa min(fecha) y max(fecha) del grupo para ese cuidador.
    """
    turno = asignacion.id_turno
    if not turno or not turno.hora_inicio or not turno.hora_fin:
        return None

    id_grupo = (asignacion.id_grupo_asignacion or "").strip()

    if not id_grupo:
        return _calcular_rango_con_turno(
            asignacion.fecha,
            asignacion.fecha,
            turno,
        )

    fechas_grupo = list(
        AsignacionTurnoUsuario.objects
        .filter(
            id_usuario_id=asignacion.id_usuario_id,
            id_grupo_asignacion=id_grupo,
        )
        .exclude(estado__iexact="Inactivo")
        .values_list("fecha", flat=True)
    )

    if not fechas_grupo:
        return _calcular_rango_con_turno(
            asignacion.fecha,
            asignacion.fecha,
            turno,
        )

    return _calcular_rango_con_turno(
        min(fechas_grupo),
        max(fechas_grupo),
        turno,
    )


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

    candidatas = list(
        AsignacionTurnoUsuario.objects
        .select_related("id_turno")
        .filter(
            id_usuario_id=id_usuario,
            id_turno__isnull=False,
            id_turno__estado=True,
        )
        .exclude(estado__iexact="Finalizado")
        .exclude(estado__iexact="Inactivo")
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
            return _resolver_bloque_de_asignacion(asignacion)

    # 2. Turno programado para hoy que aún no termina (llegada anticipada).
    for asignacion in candidatas:
        if asignacion.fecha != hoy:
            continue

        rango_dia = _calcular_rango_con_turno(
            asignacion.fecha,
            asignacion.fecha,
            asignacion.id_turno,
        )
        if rango_dia and ahora_col <= rango_dia[1]:
            return _resolver_bloque_de_asignacion(asignacion)

    # 3. Bloque multi-día (id_grupo_asignacion) que cubre el momento actual
    # aunque la jornada del día ya haya cerrado o todavía esté entre días del bloque.
    grupos_revisados = set()
    for asignacion in candidatas:
        id_grupo = (asignacion.id_grupo_asignacion or "").strip()
        if not id_grupo or id_grupo in grupos_revisados:
            continue

        grupos_revisados.add(id_grupo)
        rango_bloque = _resolver_bloque_de_asignacion(asignacion)
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
    en curso o ya cerrados).
    """
    qs = queryset if queryset is not None else AsignacionPacienteCuidador.objects.all()
    inicio_aware = _asegurar_aware(inicio)
    fin_aware = _asegurar_aware(fin)

    return qs.filter(
        id_usuario_id=id_usuario,
        fecha_inicio__lte=fin_aware,
        fecha_fin__gte=inicio_aware,
    )


def es_ultimo_dia_pendiente_grupo(asignacion):
    """
    Indica si la asignación de turno cerrada es el último día pendiente de su
    id_grupo_asignacion (o si no pertenece a ningún grupo).
    """
    id_grupo = (asignacion.id_grupo_asignacion or "").strip()

    if not id_grupo:
        return True

    quedan_dias_futuros = (
        AsignacionTurnoUsuario.objects
        .filter(
            id_usuario_id=asignacion.id_usuario_id,
            id_grupo_asignacion=id_grupo,
            fecha__gt=asignacion.fecha,
        )
        .exclude(id_asignacion_turno_usuario=asignacion.id_asignacion_turno_usuario)
        .exclude(estado__iexact="Finalizado")
        .exclude(estado__iexact="Inactivo")
        .exists()
    )

    return not quedan_dias_futuros
