import requests
from datetime import datetime, timezone

# ============================================================
# CONFIGURACIÓN
# ============================================================

API_URL = "https://geriapp-backend.onrender.com/api/eventos_ia/"

# ============================================================
# FECHA Y HORA ACTUAL
# ============================================================

fecha_hora_actual = datetime.now(timezone.utc).isoformat()

# ============================================================
# DATOS DEL EVENTO DE PRUEBA
# ============================================================

evento = {
    "confianza": 95.00,
    "fecha_hora": fecha_hora_actual,
    "estado": "detectado",
    "id_camara": 1,
    "id_habitacion": 1,
    "id_paciente": 24,
    "id_tipo_evento": 4
}

# ============================================================
# ENVIAR EVENTO AL BACKEND
# ============================================================

try:

    respuesta = requests.post(
        API_URL,
        json=evento,
        timeout=30
    )

    print("Código de respuesta:", respuesta.status_code)

    print("Respuesta del servidor:")
    print(respuesta.text)

except requests.exceptions.RequestException as error:

    print("Error al conectar con el backend:")
    print(error)