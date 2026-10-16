import requests
from datetime import datetime, timezone

# ============================================================
# CONFIGURACIÓN DEL BACKEND DE GERIAPP
# ============================================================

API_URL = "https://geriapp-backend.onrender.com/api/eventos_ia/"
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
    Envía un evento a GerIApp.

    Si el registro es exitoso, devuelve los datos del evento,
    incluido id_evento.
    Si falla, devuelve None.
    """

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
        respuesta = sesion.post(
            API_URL,
            json=evento,
            timeout=(5, 15)
        )

        if 200 <= respuesta.status_code < 300:
            datos_evento = respuesta.json()

            print("Evento enviado correctamente a GerIApp.")
            print("Código HTTP:", respuesta.status_code)
            print("Respuesta:", respuesta.text)

            # Devolver los datos para recuperar id_evento.
            return datos_evento

        print("El backend respondió con un error.")
        print("Código HTTP:", respuesta.status_code)
        print("Respuesta:", respuesta.text[:500])
        return None

    except (requests.exceptions.RequestException, ValueError) as error:
        print("No se pudo confirmar el envío del evento.")
        print("Detalle:", error)
        return None

# ============================================================
# CONFIGURACIÓN DE EVIDENCIAS
# ============================================================

API_SUBIR_IMAGEN = "https://geriapp-backend.onrender.com/api/subir-imagen/"
API_EVIDENCIAS = "https://geriapp-backend.onrender.com/api/evidencias_ia/"


# ============================================================
# FUNCIÓN PARA SUBIR UNA IMAGEN A CLOUDINARY
# ============================================================

def subir_imagen_cloudinary(imagen):
    """
    Recibe una imagen en bytes y la envía al backend.
    El backend la almacena en Cloudinary y devuelve su URL.
    """

    try:
        archivos = {
            "imagen": ("evidencia.jpg", imagen, "image/jpeg")
        }

        respuesta = sesion.post(
            API_SUBIR_IMAGEN,
            files=archivos,
            timeout=(5, 30)
        )

        if respuesta.status_code == 201:
            datos = respuesta.json()
            print("Imagen subida correctamente a Cloudinary.")
            print("URL:", datos.get("url"))
            return datos

        print("Error al subir la imagen.")
        print("Código HTTP:", respuesta.status_code)
        print("Respuesta:", respuesta.text[:500])
        return None

    except (requests.exceptions.RequestException, ValueError) as error:
        print("No se pudo subir la imagen.")
        print("Detalle:", error)
        return None


# ============================================================
# FUNCIÓN PARA REGISTRAR LA EVIDENCIA EN GERIAPP
# ============================================================

def registrar_evidencia_geriapp(id_evento, url, public_id):
    """
    Registra en la base de datos la imagen asociada al evento.
    """

    evidencia = {
        "tipo": "imagen",
        "url": url,
        "public_id": public_id,
        "fecha_hora": datetime.now(timezone.utc).isoformat(),
        "id_evento": id_evento
    }

    try:
        respuesta = sesion.post(
            API_EVIDENCIAS,
            json=evidencia,
            timeout=(5, 15)
        )

        if respuesta.status_code == 201:
            print("Evidencia registrada correctamente en GerIApp.")
            print("Respuesta:", respuesta.text)
            return respuesta.json()

        print("Error al registrar la evidencia.")
        print("Código HTTP:", respuesta.status_code)
        print("Respuesta:", respuesta.text[:500])
        return None

    except (requests.exceptions.RequestException, ValueError) as error:
        print("No se pudo registrar la evidencia.")
        print("Detalle:", error)
        return None

