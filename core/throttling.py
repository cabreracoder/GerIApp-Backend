import hashlib
import math

from django.db import connection
from django.utils import timezone

from rest_framework.throttling import BaseThrottle
from rest_framework.response import Response
from rest_framework import status


# ==========================================
# CONFIGURACIÓN
# ==========================================

MAX_INTENTOS_FALLIDOS = 5

TIEMPO_VENTANA = 15 * 60

TIEMPO_BLOQUEO = 15 * 60


# ==========================================
# IDENTIFICACIÓN DE LA IP
# ==========================================

def obtener_identificador_ip(request):

    identificador = BaseThrottle().get_ident(request)

    return hashlib.sha256(
        identificador.encode('utf-8')
    ).hexdigest()

# ==========================================
# CONSULTAR SI UNA IP ESTÁ BLOQUEADA
# ==========================================

class LoginFacialThrottle(BaseThrottle):

    def __init__(self):
        self.tiempo_restante = None

    def allow_request(self, request, view):

        identificador = obtener_identificador_ip(request)

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT bloqueado_hasta
                FROM control_intentos_login_facial
                WHERE identificador = %s
                """,
                [identificador]
            )

            resultado = cursor.fetchone()

        if not resultado:
            return True

        bloqueado_hasta = resultado[0]

        if bloqueado_hasta is None:
            return True

        ahora = timezone.now()

        if bloqueado_hasta > ahora:

            self.tiempo_restante = max(
                1,
                math.ceil(
                    (bloqueado_hasta - ahora).total_seconds()
                )
            )

            return False

        return True

    def wait(self):

        return self.tiempo_restante


# ==========================================
# REGISTRAR INTENTO FALLIDO
# ==========================================

def registrar_fallo_login_facial(request):

    identificador = obtener_identificador_ip(request)

    with connection.cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO control_intentos_login_facial AS actual (
                identificador,
                intentos,
                inicio_ventana,
                bloqueado_hasta,
                actualizado_en
            )
            VALUES (
                %s,
                1,
                CURRENT_TIMESTAMP,
                NULL,
                CURRENT_TIMESTAMP
            )

            ON CONFLICT (identificador)

            DO UPDATE SET

                intentos = CASE

                    WHEN actual.bloqueado_hasta IS NOT NULL
                         AND actual.bloqueado_hasta > CURRENT_TIMESTAMP
                    THEN actual.intentos

                    WHEN actual.inicio_ventana <=
                         CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                         OR (
                             actual.bloqueado_hasta IS NOT NULL
                             AND actual.bloqueado_hasta <= CURRENT_TIMESTAMP
                         )
                    THEN 1

                    ELSE actual.intentos + 1

                END,

                inicio_ventana = CASE

                    WHEN actual.bloqueado_hasta IS NOT NULL
                         AND actual.bloqueado_hasta > CURRENT_TIMESTAMP
                    THEN actual.inicio_ventana

                    WHEN actual.inicio_ventana <=
                         CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                         OR (
                             actual.bloqueado_hasta IS NOT NULL
                             AND actual.bloqueado_hasta <= CURRENT_TIMESTAMP
                         )
                    THEN CURRENT_TIMESTAMP

                    ELSE actual.inicio_ventana

                END,

                bloqueado_hasta = CASE

                    WHEN actual.bloqueado_hasta IS NOT NULL
                         AND actual.bloqueado_hasta > CURRENT_TIMESTAMP
                    THEN actual.bloqueado_hasta

                    WHEN actual.inicio_ventana <=
                         CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                         OR (
                             actual.bloqueado_hasta IS NOT NULL
                             AND actual.bloqueado_hasta <= CURRENT_TIMESTAMP
                         )
                    THEN NULL

                    WHEN actual.intentos + 1 >= %s
                    THEN CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')

                    ELSE NULL

                END,

                actualizado_en = CURRENT_TIMESTAMP

            RETURNING intentos, bloqueado_hasta
            """,
            [
                identificador,
                TIEMPO_VENTANA,
                TIEMPO_VENTANA,
                TIEMPO_VENTANA,
                MAX_INTENTOS_FALLIDOS,
                TIEMPO_BLOQUEO
            ]
        )

        resultado = cursor.fetchone()

    intentos = resultado[0]
    bloqueado_hasta = resultado[1]

    # ======================================
    # SE ALCANZÓ EL LÍMITE
    # ======================================

    if bloqueado_hasta is not None:

        ahora = timezone.now()

        tiempo_restante = max(
            1,
            math.ceil(
                (bloqueado_hasta - ahora).total_seconds()
            )
        )

        if tiempo_restante > 0:

            return Response(
                {
                    'error': (
                        'Has superado el número máximo de intentos '
                        'de reconocimiento facial.'
                    ),
                    'mensaje': (
                        'Tu acceso está bloqueado temporalmente. '
                        'Intenta nuevamente después de 15 minutos.'
                    ),
                    'intentos_permitidos': MAX_INTENTOS_FALLIDOS,
                    'tiempo_bloqueo_segundos': tiempo_restante
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={
                    'Retry-After': str(tiempo_restante)
                }
            )

    # ======================================
    # INTENTOS RESTANTES
    # ======================================

    return Response(
        {
            'error': 'No fue posible validar la identidad.',
            'intentos_restantes': max(
                0,
                MAX_INTENTOS_FALLIDOS - intentos
            )
        },
        status=status.HTTP_401_UNAUTHORIZED
    )