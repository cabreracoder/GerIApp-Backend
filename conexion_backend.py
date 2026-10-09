
import requests
from datetime import datetime, timezone

# ============================================================
# CONFIGURACIÓN DEL BACKEND DE GERIAPP
# ============================================================

API_URL = "https://geriapp-backend.onrender.com/api/eventos_ia/"

# Sesión reutilizable para realizar peticiones HTTP.
sesion = requests.Session()


# ============================================================
# FUNCIÓN PARA ENVIAR EVENTOS A GERIAPP
# ============================================================

def enviar_evento_geriapp(
    id_camara,
    id_habitacion,
    id_paciente,
    id_tipo_evento,
    confianza,
    estado="detectado"
):
    """
    Envía un evento de inteligencia artificial a GerIApp.

    Retorna True si el servidor responde con HTTP 2xx.
    Retorna False si ocurre un error HTTP o de conexión.
    """

    # Construir los datos del evento.
    evento = {
        "confianza": round(float(confianza), 2),
        "fecha_hora": datetime.now(timezone.utc).isoformat(),
        "estado": estado,
        "id_camara": id_camara,
        "id_habitacion": id_habitacion,
        "id_paciente": id_paciente,
        "id_tipo_evento": id_tipo_evento
    }

    try:
        # Enviar el evento al backend.
        respuesta = sesion.post(
            API_URL,
            json=evento,
            timeout=(5, 15)
        )

        # Comprobar si el servidor aceptó la petición.
        if 200 <= respuesta.status_code < 300:
            print("Evento enviado correctamente a GerIApp.")
            print("Código HTTP:", respuesta.status_code)
            print("Respuesta:", respuesta.text)
            return True

        print("El backend respondió con un error.")
        print("Código HTTP:", respuesta.status_code)
        print("Respuesta:", respuesta.text[:500])
        return False

    except requests.exceptions.RequestException as error:
        print("No se pudo confirmar el envío del evento.")
        print("Detalle:", error)
        return False