import os
import requests
import base64
import numpy as np

from datetime import datetime, timezone

from reconocimiento_facial.cifrado import descifrar_embedding


# ============================================================
# CONFIGURACIÓN DEL BACKEND DE GERIAPP
# ============================================================

BASE_URL = "https://geriapp-backend.onrender.com/api"

API_LOGIN = f"{BASE_URL}/usuarios/login/"
API_CAMARAS = f"{BASE_URL}/camaras/"
API_URL = f"{BASE_URL}/eventos_ia/"
API_SUBIR_IMAGEN = f"{BASE_URL}/subir-imagen/"
API_EVIDENCIAS = f"{BASE_URL}/evidencias_ia/"
API_PLANTILLAS = f"{BASE_URL}/registros_faciales/plantillas/"

sesion = requests.Session()
autenticado = False


# ============================================================
# AUTENTICACIÓN
# ============================================================

def autenticar_geriapp():
    """
    Inicia sesión en GerIApp y guarda el token Bearer
    en la sesión HTTP para las siguientes peticiones.
    """

    global autenticado

    correo = os.getenv("GERIAPP_CORREO")
    contrasena = os.getenv("GERIAPP_CONTRASENA")

    if not correo or not contrasena:
        raise RuntimeError(
            "Faltan las variables de entorno "
            "GERIAPP_CORREO y/o GERIAPP_CONTRASENA."
        )

    try:
        respuesta = sesion.post(
            API_LOGIN,
            json={
                "correo": correo,
                "contrasena": contrasena
            },
            timeout=(5, 20)
        )

        if not respuesta.ok:
            raise RuntimeError(
                f"Falló el inicio de sesión. "
                f"HTTP {respuesta.status_code}: "
                f"{respuesta.text[:300]}"
            )

        datos = respuesta.json()
        token = datos.get("token")

        if not token:
            raise RuntimeError(
                "El inicio de sesión no devolvió un token."
            )

        sesion.headers.update({
            "Authorization": f"Bearer {token}"
        })

        autenticado = True
        print("Autenticación con GerIApp exitosa.")

    except (requests.exceptions.RequestException, ValueError) as error:
        autenticado = False
        raise RuntimeError(
            f"No fue posible autenticar con GerIApp: {error}"
        ) from error


def asegurar_autenticacion():
    """Autentica antes de utilizar los endpoints protegidos."""

    if not autenticado:
        autenticar_geriapp()


# ============================================================
# CONSULTAR CÁMARAS ACTIVAS DESDE GERIAPP
# ============================================================

def obtener_camaras_activas():
    """
    Consulta las cámaras registradas en el backend
    y devuelve únicamente las que estén activas.
    """

    asegurar_autenticacion()

    try:
        respuesta = sesion.get(
            API_CAMARAS,
            timeout=(5, 20)
        )

        if respuesta.status_code == 401:
            # Renovar el token mediante un nuevo inicio de sesión.
            autenticar_geriapp()
            respuesta = sesion.get(
                API_CAMARAS,
                timeout=(5, 20)
            )

        respuesta.raise_for_status()
        datos = respuesta.json()

        # Admite una lista directa o una respuesta paginada.
        if isinstance(datos, dict):
            datos = datos.get("results", [])

        if not isinstance(datos, list):
            raise RuntimeError(
                "La respuesta de cámaras no tiene el formato esperado."
            )

        activas = [
            camara for camara in datos
            if camara.get("estado") is True
        ]

        print(
            f"Cámaras recibidas: {len(datos)} | "
            f"Cámaras activas: {len(activas)}"
        )

        return activas

    except (requests.exceptions.RequestException, ValueError) as error:
        raise RuntimeError(
            f"No se pudieron consultar las cámaras: {error}"
        ) from error


# ============================================================
# CONSULTAR PACIENTES ACTIVOS DESDE GERIAPP
# ============================================================

def obtener_pacientes_activos():
    """Consulta los pacientes activos registrados en GerIApp."""

    asegurar_autenticacion()

    try:
        respuesta = sesion.get(
            f"{BASE_URL}/pacientes/",
            timeout=(5, 20)
        )

        if respuesta.status_code == 401:
            autenticar_geriapp()
            respuesta = sesion.get(
                f"{BASE_URL}/pacientes/",
                timeout=(5, 20)
            )

        respuesta.raise_for_status()
        datos = respuesta.json()

        if isinstance(datos, dict):
            datos = datos.get("results", [])

        if not isinstance(datos, list):
            raise RuntimeError(
                "La respuesta de pacientes no tiene el formato esperado."
            )

        return [
            paciente for paciente in datos
            if paciente.get("estado") is True
        ]

    except (requests.exceptions.RequestException, ValueError) as error:
        raise RuntimeError(
            f"No se pudieron consultar los pacientes: {error}"
        ) from error

# ============================================================
# OBTENER NOMBRE DE LOS PACIENTES
# ============================================================

def obtener_nombre_paciente(paciente):
    """
    Obtiene el nombre completo del paciente desde
    la información recibida del backend.
    """

    nombres = (
        paciente.get("nombres")
        or paciente.get("nombre")
        or paciente.get("primer_nombre")
        or ""
    )

    apellidos = (
        paciente.get("apellidos")
        or paciente.get("apellido")
        or paciente.get("primer_apellido")
        or ""
    )

    nombre_completo = f"{nombres} {apellidos}".strip()

    # Intentar obtener el nombre desde un objeto relacionado.
    if not nombre_completo:
        usuario = paciente.get("usuario", {})

        if isinstance(usuario, dict):
            nombre_completo = (
                usuario.get("nombre_completo")
                or usuario.get("nombre")
                or ""
            )

    return nombre_completo or f"Paciente {paciente.get('id_paciente', '')}"


# ============================================================
# CONSULTAR Y DESCIFRAR PLANTILLAS FACIALES POR CÁMARA
# ============================================================

def obtener_plantillas_faciales(id_camara):
    """
    Consulta las plantillas faciales asociadas a una cámara.

    Descifra los embeddings y relaciona cada plantilla
    con el nombre del paciente correspondiente.
    """

    asegurar_autenticacion()

    try:
        # Obtener pacientes activos
        pacientes = obtener_pacientes_activos()

        # Crear un diccionario para relacionar ID y nombre
        pacientes_por_id = {}

        for paciente in pacientes:
            id_paciente = paciente.get("id_paciente") or paciente.get("id")

            if id_paciente is not None:
                pacientes_por_id[str(id_paciente)] = (
                    obtener_nombre_paciente(paciente)
                )

        respuesta = sesion.get(
            API_PLANTILLAS,
            params={"id_camara": id_camara},
            timeout=(5, 30)
        )

        if respuesta.status_code == 401:
            autenticar_geriapp()

            respuesta = sesion.get(
                API_PLANTILLAS,
                params={"id_camara": id_camara},
                timeout=(5, 30)
            )

        respuesta.raise_for_status()

        datos = respuesta.json()

        if not isinstance(datos, dict):
            raise RuntimeError(
                "La respuesta de plantillas no tiene el formato esperado."
            )

        registros = datos.get("plantillas", [])

        if not isinstance(registros, list):
            raise RuntimeError(
                "El listado de plantillas tiene un formato inválido."
            )

        plantillas_descifradas = []

        for registro in registros:

            try:
                id_paciente = registro.get("id_paciente")
                id_registro = registro.get("id_registro_facial")

                # Obtener nombre del paciente
                nombre_paciente = pacientes_por_id.get(
                    str(id_paciente),
                    f"Paciente {id_paciente}"
                )

                embedding_base64 = registro.get(
                    "embedding_cifrado"
                )

                if not embedding_base64:
                    print(
                        f"Plantilla del registro {id_registro} "
                        "sin embedding."
                    )
                    continue

                # Decodificar Base64
                embedding_cifrado = base64.b64decode(
                    embedding_base64,
                    validate=True
                )

                # Descifrar embedding
                embedding_bytes = descifrar_embedding(
                    embedding_cifrado
                )

                # Convertir a vector NumPy
                embedding = np.frombuffer(
                    embedding_bytes,
                    dtype=np.float32
                ).copy()

                # Validar dimensiones
                if embedding.shape != (128,):
                    print(
                        f"Dimensiones incorrectas en el registro "
                        f"{id_registro}: {embedding.shape}"
                    )
                    continue

                # Validar valores numéricos
                if not np.all(np.isfinite(embedding)):
                    print(
                        f"Embedding inválido en el registro "
                        f"{id_registro}."
                    )
                    continue

                # Guardar plantilla con ID y nombre
                plantillas_descifradas.append({
                    "id_registro_facial": id_registro,
                    "id_paciente": id_paciente,
                    "nombre_paciente": nombre_paciente,
                    "embedding": embedding
                })

                print(
                    f"Plantilla cargada: {nombre_paciente}"
                )

            except (ValueError, TypeError) as error:
                print(
                    f"No se pudo procesar la plantilla "
                    f"{registro.get('id_registro_facial')}: {error}"
                )
                continue

        print(
            f"Cámara {id_camara}: "
            f"{len(plantillas_descifradas)} plantillas "
            "faciales descifradas correctamente."
        )

        return plantillas_descifradas

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            f"No se pudieron consultar las plantillas faciales "
            f"de la cámara {id_camara}: {error}"
        ) from error

# ============================================================
# ENVIAR EVENTOS A GERIAPP
# ============================================================

def enviar_evento_geriapp(
    id_camara,
    id_habitacion,
    id_paciente,
    id_tipo_evento,
    confianza,
    estado="detectado"
):
    """Envía un evento y devuelve los datos recibidos."""

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
        asegurar_autenticacion()

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
            return datos_evento

        print("El backend respondió con un error.")
        print("Código HTTP:", respuesta.status_code)
        print("Respuesta:", respuesta.text[:500])
        return None

    except (requests.exceptions.RequestException, ValueError, RuntimeError) as error:
        print("No se pudo confirmar el envío del evento.")
        print("Detalle:", error)
        return None


# ============================================================
# SUBIR IMAGEN A CLOUDINARY MEDIANTE EL BACKEND
# ============================================================

def subir_imagen_cloudinary(imagen):
    """Envía los bytes de la evidencia al backend."""

    try:
        asegurar_autenticacion()

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

    except (requests.exceptions.RequestException, ValueError, RuntimeError) as error:
        print("No se pudo subir la imagen.")
        print("Detalle:", error)
        return None


# ============================================================
# REGISTRAR EVIDENCIA EN GERIAPP
# ============================================================

def registrar_evidencia_geriapp(id_evento, url, public_id):
    """Registra en la base de datos la evidencia del evento."""

    evidencia = {
        "tipo": "imagen",
        "url": url,
        "public_id": public_id,
        "fecha_hora": datetime.now(timezone.utc).isoformat(),
        "id_evento": id_evento
    }

    try:
        asegurar_autenticacion()

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

    except (requests.exceptions.RequestException, ValueError, RuntimeError) as error:
        print("No se pudo registrar la evidencia.")
        print("Detalle:", error)
        return None
