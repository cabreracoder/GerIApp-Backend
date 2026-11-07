import cv2
import numpy as np
import threading
import time
import queue
from ultralytics import YOLO
import os
from dotenv import load_dotenv
load_dotenv()

from conexion_backend import (
    enviar_evento_geriapp,
    subir_imagen_cloudinary,
    registrar_evidencia_geriapp,
    obtener_camaras_activas,
    obtener_pacientes_activos,
)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from transmision_livekit import TransmisionLiveKit


# ============================================================
# CAPTURA DE CÁMARAS MEDIANTE ÍNDICES DE OPENCV
# ============================================================

ANCHO_CAMARA = 640
ALTO_CAMARA = 480
FPS_CAMARA = 30

# Índices comprobados en este computador:
# 0 = cámara integrada del portátil (EXCLUIDA)
# 1 = cámara externa JALTECH 1
# 2 = cámara externa JALTECH 2
#
# La clave es el ID de cámara registrado en GerIApp.
# El valor es el índice físico que utiliza OpenCV.
INDICES_CAMARAS = {
    1: 1,
    2: 2,
}


def abrir_camara_opencv(indice):
    """Abre una cámara física usando su índice de OpenCV (Windows)."""
    indice = int(indice)

    if indice == 0:
        raise ValueError(
            "El índice 0 está reservado para la cámara integrada."
        )

    camara = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

    if not camara.isOpened():
        camara.release()
        return None

    camara.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAMARA)
    camara.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAMARA)
    camara.set(cv2.CAP_PROP_FPS, FPS_CAMARA)

    return camara


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

MODELO_YOLO = "yolo11n-pose.pt"
FPS_YOLO = 10
TAMANO_YOLO = 640
CONFIANZA_DETECCION = 0.50
CONFIANZA_MINIMA_PUNTO = 0.40
FRAMES_ESTABILIDAD = 8
MAX_SIN_PERSONA = 25
DURACION_AVISO_LEVANTAMIENTO = 2
TIEMPO_MAXIMO_DESCONOCIDO = 3.0

CAMARAS_CONFIG = {}

TIPO_PACIENTE_SENTADO = 2
TIPO_LEVANTAMIENTO_COMPLETO = 4


# ============================================================
# CONTROL GLOBAL Y COLA DE EVENTOS
# ============================================================

ejecutando = threading.Event()
ejecutando.set()

cola_eventos = queue.Queue()


# ============================================================
# ESTADO INDEPENDIENTE PARA CADA CÁMARA
# ============================================================

def crear_estado():
    return {
        "camara": None,
        "frame": None,
        "frame_mostrar": None,
        "frame_lock": threading.Lock(),
        "activa": False,

        "postura_actual": "DESCONOCIDO",
        "postura_candidata": "DESCONOCIDO",
        "ultima_postura_valida": "DESCONOCIDO",
        "postura_anterior": "DESCONOCIDO",

        "contador_postura": 0,
        "contador_sin_persona": 0,
        "ultima_confianza": 0.0,
        "ultimo_frame_valido": time.time(),
        "persona_detectada": False,

        "levantamiento_en_proceso": False,
        "levantamiento_detectado": False,
        "tipo_alerta_levantamiento": "",

        "contador_levantamientos": 0,
        "tiempo_levantamiento": 0,

        "ultimo_procesamiento": 0,
    }


estados = {}


# ============================================================
# SERVIDOR LOCAL PARA TRANSMITIR LAS CÁMARAS
# ============================================================

HOST_VIDEO = "0.0.0.0"
PUERTO_VIDEO = 8081


class ServidorVideoHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        ruta = urlparse(self.path)

        if ruta.path != "/video":
            self.send_error(404, "Ruta no encontrada")
            return

        parametros = parse_qs(ruta.query)
        nombre = parametros.get("camara", [None])[0]

        if nombre not in estados:
            self.send_error(404, "Cámara no encontrada")
            return

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "multipart/x-mixed-replace; boundary=fotograma",
        )
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        try:
            while ejecutando.is_set():
                estado = estados.get(nombre)

                if estado is None:
                    break

                with estado["frame_lock"]:
                    frame = estado["frame_mostrar"]

                    if frame is not None:
                        frame = frame.copy()

                if frame is None:
                    time.sleep(0.1)
                    continue

                correcto, imagen_jpg = cv2.imencode(
                    ".jpg",
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 55],
                )

                if not correcto:
                    time.sleep(0.1)
                    continue

                self.wfile.write(b"--fotograma\r\n")
                self.wfile.write(
                    b"Content-Type: image/jpeg\r\n\r\n"
                )
                self.wfile.write(imagen_jpg.tobytes())
                self.wfile.write(b"\r\n")

                time.sleep(0.1)

        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, formato, *argumentos):
        pass


# ============================================================
# FUNCIONES PARA CALCULAR ÁNGULOS
# ============================================================

def calcular_angulo(a, b, c):
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    c = np.array(c, dtype=np.float32)

    ba = a - b
    bc = c - b

    producto = np.dot(ba, bc)
    magnitud = np.linalg.norm(ba) * np.linalg.norm(bc)

    if magnitud == 0:
        return 0

    coseno = producto / magnitud
    coseno = np.clip(coseno, -1.0, 1.0)

    return np.degrees(np.arccos(coseno))


# ============================================================
# VALIDACIÓN DE PUNTOS DEL CUERPO
# ============================================================

def punto_visible(confianzas, indice):
    return (
        confianzas is not None
        and len(confianzas) > indice
        and float(confianzas[indice]) >= CONFIANZA_MINIMA_PUNTO
    )


def cuerpo_valido(keypoints, confianzas):
    """
    Valida hombros, caderas y al menos una pierna completa.
    Esta validación general permite continuar evaluando
    ACOSTADA y SENTADA.
    """

    if (
        keypoints is None
        or confianzas is None
        or len(keypoints) < 17
        or len(confianzas) < 17
    ):
        return False

    hombros = (
        punto_visible(confianzas, 5)
        or punto_visible(confianzas, 6)
    )

    caderas = (
        punto_visible(confianzas, 11)
        or punto_visible(confianzas, 12)
    )

    pierna_izq = all(
        punto_visible(confianzas, i)
        for i in (11, 13, 15)
    )

    pierna_der = all(
        punto_visible(confianzas, i)
        for i in (12, 14, 16)
    )

    return hombros and caderas and (
        pierna_izq or pierna_der
    )


def confianza_cuerpo(confianzas):
    """Promedio de confianza de los puntos importantes."""

    if confianzas is None or len(confianzas) < 17:
        return 0.0

    indices = [5, 6, 11, 12, 13, 14, 15, 16]

    valores = [
        float(confianzas[i])
        for i in indices
        if float(confianzas[i]) >= CONFIANZA_MINIMA_PUNTO
    ]

    return float(np.mean(valores)) if valores else 0.0


def punto_medio(puntos, confianzas, a, b):
    disponibles = []

    if punto_visible(confianzas, a):
        disponibles.append(puntos[a])

    if punto_visible(confianzas, b):
        disponibles.append(puntos[b])

    if not disponibles:
        return None

    return np.mean(disponibles, axis=0)


def angulo_respecto_vertical(origen, destino):
    """
    Devuelve:
    0 grados = segmento vertical.
    90 grados = segmento horizontal.
    """

    vector = (
        np.asarray(destino, dtype=np.float32)
        - np.asarray(origen, dtype=np.float32)
    )

    return abs(
        float(
            np.degrees(
                np.arctan2(vector[0], vector[1])
            )
        )
    )


# ============================================================
# DETECCIÓN DE POSTURAS
# ============================================================

def detectar_postura(puntos, confianzas, caja=None):
    """
    Clasifica ACOSTADA, SENTADA o DE PIE.

    DE PIE:
    - Cabeza visible.
    - Ambos hombros visibles.
    - Ambas caderas visibles.
    - Ambas rodillas visibles.
    - Ambos tobillos visibles.
    - Tronco vertical.
    - Ambas piernas verticales.
    - Ambas rodillas extendidas.
    - Caja de detección vertical.

    Las condiciones estrictas solamente se aplican a DE PIE.
    """

    hombros = punto_medio(
        puntos, confianzas, 5, 6
    )

    caderas = punto_medio(
        puntos, confianzas, 11, 12
    )

    if hombros is None or caderas is None:
        return "DESCONOCIDO"

    angulo_tronco = angulo_respecto_vertical(
        hombros, caderas
    )

    angulos_rodilla = []
    angulos_pierna = []

    # Evaluar las dos piernas.
    for cadera, rodilla, tobillo in (
        (11, 13, 15),
        (12, 14, 16),
    ):

        if all(
            punto_visible(confianzas, i)
            for i in (cadera, rodilla, tobillo)
        ):

            ang_rodilla = calcular_angulo(
                puntos[cadera],
                puntos[rodilla],
                puntos[tobillo],
            )

            ang_pierna = angulo_respecto_vertical(
                puntos[cadera],
                puntos[tobillo],
            )

            angulos_rodilla.append(ang_rodilla)
            angulos_pierna.append(ang_pierna)

    # --------------------------------------------------------
    # VALIDAR PROPORCIÓN DE LA CAJA
    # --------------------------------------------------------

    caja_vertical = False

    if caja is not None:

        x1, y1, x2, y2 = map(float, caja)

        ancho = max(1.0, x2 - x1)
        alto = max(1.0, y2 - y1)

        caja_vertical = alto / ancho >= 1.15

    # --------------------------------------------------------
    # VALIDAR CUERPO COMPLETO
    # --------------------------------------------------------

    # COCO:
    # 0-4: cabeza
    # 5-6: hombros
    # 11-12: caderas
    # 13-14: rodillas
    # 15-16: tobillos

    cabeza_visible = any(
        punto_visible(confianzas, i)
        for i in range(5)
    )

    cuerpo_completo = (
        cabeza_visible
        and all(
            punto_visible(confianzas, i)
            for i in (
                5, 6,
                11, 12,
                13, 14,
                15, 16,
            )
        )
    )

    # --------------------------------------------------------
    # DETECTAR DE PIE
    # --------------------------------------------------------

    if (
        cuerpo_completo
        and caja_vertical
        and len(angulos_pierna) == 2
        and len(angulos_rodilla) == 2
    ):

        ambas_piernas_verticales = all(
            angulo <= 38
            for angulo in angulos_pierna
        )

        ambas_rodillas_extendidas = all(
            angulo >= 145
            for angulo in angulos_rodilla
        )

        tronco_vertical = angulo_tronco <= 38

        if (
            tronco_vertical
            and ambas_piernas_verticales
            and ambas_rodillas_extendidas
        ):
            return "DE PIE"

    # --------------------------------------------------------
    # DETECTAR ACOSTADA
    # --------------------------------------------------------

    if (
        angulo_tronco >= 55
        and angulos_pierna
        and max(angulos_pierna) >= 50
    ):
        return "ACOSTADA"

    # --------------------------------------------------------
    # DETECTAR SENTADA
    # --------------------------------------------------------

    if angulos_rodilla and (
        min(angulos_rodilla) < 145
        or (
            angulo_tronco >= 35
            and angulo_tronco < 75
        )
    ):
        return "SENTADA"

    return "DESCONOCIDO"


# ============================================================
# SELECCIONAR PERSONA DETECTADA
# ============================================================

def seleccionar_persona(resultado):
    """Selecciona la persona detectada con mayor área y confianza."""

    if (
        resultado.boxes is None
        or resultado.keypoints is None
    ):
        return None

    candidatos = []

    cantidad = min(
        len(resultado.boxes),
        len(resultado.keypoints),
    )

    for i in range(cantidad):

        box = resultado.boxes.xyxy[i].cpu().numpy()

        x1, y1, x2, y2 = box

        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)

        conf_det = (
            float(resultado.boxes.conf[i].item())
            if resultado.boxes.conf is not None
            else 0.0
        )

        puntuacion = area * max(conf_det, 0.01)

        candidatos.append((puntuacion, i))

    if not candidatos:
        return None

    return max(
        candidatos,
        key=lambda x: x[0]
    )[1]


# ============================================================
# CAPTURA INDEPENDIENTE DE CADA CÁMARA
# ============================================================

def capturar_camara(nombre):

    estado = estados[nombre]
    camara = estado["camara"]

    while ejecutando.is_set():

        correcto, imagen = camara.read()

        if not correcto:

            estado["activa"] = False
            time.sleep(0.1)
            continue

        estado["activa"] = True

        with estado["frame_lock"]:
            estado["frame"] = imagen.copy()


# ============================================================
# REGISTRAR EVENTO Y CONSERVAR SU IMAGEN
# ============================================================

def registrar_evento(
    nombre,
    tipo_evento,
    imagen,
    confianza=None,
):

    config = CAMARAS_CONFIG[nombre]

    if config["id_paciente"] is None:

        print(
            f"[{nombre}] Evento no registrado: "
            "no hay un paciente identificado de forma segura."
        )

        return

    evento = {
        "nombre_camara": nombre,
        "id_camara": config["id_camara"],
        "id_habitacion": config["id_habitacion"],
        "id_paciente": config["id_paciente"],
        "id_tipo_evento": tipo_evento,
        "confianza": round(
            float(
                confianza
                if confianza is not None
                else 0.0
            ) * 100,
            2,
        ),
        "imagen": imagen.copy(),
    }

    cola_eventos.put(evento)

    print(
        f"[{nombre}] Evento tipo {tipo_evento} agregado a la cola. "
        f"ID GerIApp: {config['id_camara']}"
    )


# ============================================================
# ENVÍO DE EVENTOS Y EVIDENCIAS
# ============================================================

def enviar_eventos_backend():

    while True:

        evento = cola_eventos.get()

        try:

            if evento is None:
                return

            nombre = evento["nombre_camara"]

            print(
                f"[{nombre}] Enviando evento "
                f"{evento['id_tipo_evento']} a GerIApp..."
            )

            resultado = enviar_evento_geriapp(
                id_camara=evento["id_camara"],
                id_habitacion=evento["id_habitacion"],
                id_paciente=evento["id_paciente"],
                id_tipo_evento=evento["id_tipo_evento"],
                confianza=evento["confianza"],
            )

            if not resultado:

                print(
                    f"[{nombre}] No se confirmó el registro "
                    "del evento."
                )

                continue

            id_evento = (
                resultado.get("id_evento")
                or resultado.get("id")
            )

            if id_evento is None:

                print(
                    f"[{nombre}] El backend no devolvió el ID "
                    "del evento. No se registrará la evidencia."
                )

                continue

            print(
                f"[{nombre}] Evento registrado. ID: {id_evento}"
            )

            imagen_evento = evento["imagen"]

            correcto, imagen_codificada = cv2.imencode(
                ".jpg",
                imagen_evento,
                [int(cv2.IMWRITE_JPEG_QUALITY), 85],
            )

            if not correcto:

                print(
                    f"[{nombre}] No se pudo codificar la imagen."
                )

                continue

            resultado_imagen = subir_imagen_cloudinary(
                imagen_codificada.tobytes()
            )

            if not resultado_imagen:

                print(
                    f"[{nombre}] El evento existe, pero falló "
                    "la subida de la imagen."
                )

                continue

            url_imagen = resultado_imagen.get("url")
            public_id = resultado_imagen.get("public_id")

            if not url_imagen or not public_id:

                print(
                    f"[{nombre}] Faltan url o public_id "
                    "en la respuesta de Cloudinary."
                )

                continue

            evidencia = registrar_evidencia_geriapp(
                id_evento=id_evento,
                url=url_imagen,
                public_id=public_id,
            )

            if evidencia:

                print(
                    f"[{nombre}] Evidencia registrada "
                    f"para el evento {id_evento}."
                )

            else:

                print(
                    f"[{nombre}] No se confirmó el registro "
                    "de la evidencia."
                )

        except Exception as error:

            print(
                "Error procesando evento:",
                error,
            )

        finally:
            cola_eventos.task_done()


# ============================================================
# ACTUALIZAR LA POSTURA DE UNA CÁMARA
# ============================================================

def actualizar_postura(
    nombre,
    postura_detectada,
    imagen,
    confianza=0.0,
):

    estado = estados[nombre]

    if postura_detectada == "SIN PERSONA":

        estado["contador_sin_persona"] += 1
        estado["contador_postura"] = 0
        estado["postura_candidata"] = "SIN PERSONA"

        if estado["contador_sin_persona"] >= MAX_SIN_PERSONA:

            anterior = estado["ultima_postura_valida"]

            estado["postura_actual"] = "SIN PERSONA"
            estado["ultima_postura_valida"] = "SIN PERSONA"
            estado["postura_anterior"] = anterior
            estado["levantamiento_en_proceso"] = False

        return

    estado["contador_sin_persona"] = 0

    if postura_detectada == "DESCONOCIDO":

        if (
            time.time() - estado["ultimo_frame_valido"]
            > TIEMPO_MAXIMO_DESCONOCIDO
        ):

            estado["postura_actual"] = "DESCONOCIDO"

        estado["contador_postura"] = 0
        estado["postura_candidata"] = "DESCONOCIDO"

        return

    estado["ultimo_frame_valido"] = time.time()
    estado["ultima_confianza"] = confianza

    if postura_detectada == estado["postura_candidata"]:

        estado["contador_postura"] += 1

    else:

        estado["postura_candidata"] = postura_detectada
        estado["contador_postura"] = 1

    if estado["contador_postura"] < FRAMES_ESTABILIDAD:
        return

    if postura_detectada == estado["ultima_postura_valida"]:

        estado["postura_actual"] = postura_detectada
        return

    anterior = estado["ultima_postura_valida"]

    estado["postura_anterior"] = anterior
    estado["ultima_postura_valida"] = postura_detectada
    estado["postura_actual"] = postura_detectada
    estado["contador_postura"] = 0

    if postura_detectada == "ACOSTADA":

        estado["levantamiento_en_proceso"] = False

        print(
            f"[{nombre}] Postura ACOSTADA confirmada."
        )

    elif (
        anterior == "ACOSTADA"
        and postura_detectada == "SENTADA"
    ):

        estado["levantamiento_en_proceso"] = True
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "INICIO"
        estado["tiempo_levantamiento"] = time.time()

        registrar_evento(
            nombre,
            TIPO_PACIENTE_SENTADO,
            imagen,
            confianza,
        )

        print(
            f"[{nombre}] ACOSTADA -> SENTADA: inicio confirmado."
        )

    elif (
        anterior == "SENTADA"
        and postura_detectada == "ACOSTADA"
    ):

        estado["levantamiento_en_proceso"] = False

        print(
            f"[{nombre}] Regresó a ACOSTADA; "
            "levantamiento cancelado."
        )

    elif (
        postura_detectada == "DE PIE"
        and anterior in ("ACOSTADA", "SENTADA")
    ):

        estado["levantamiento_en_proceso"] = False
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "COMPLETADO"
        estado["tiempo_levantamiento"] = time.time()
        estado["contador_levantamientos"] += 1

        registrar_evento(
            nombre,
            TIPO_LEVANTAMIENTO_COMPLETO,
            imagen,
            confianza,
        )

        print(
            f"[{nombre}] {anterior} -> DE PIE: "
            "levantamiento completado."
        )


# ============================================================
# PROCESAR UNA IMAGEN CON YOLO POSE
# ============================================================

transmisor_livekit = None


def procesar_camara(nombre, modelo):

    estado = estados[nombre]
    ahora = time.time()

    if (
        ahora - estado["ultimo_procesamiento"]
        < 1 / FPS_YOLO
    ):
        return

    estado["ultimo_procesamiento"] = ahora

    with estado["frame_lock"]:

        if estado["frame"] is None:
            return

        frame = estado["frame"].copy()

    resultados = modelo.predict(
        source=frame,
        verbose=False,
        conf=CONFIANZA_DETECCION,
        imgsz=TAMANO_YOLO,
    )

    resultado = resultados[0]

    frame_mostrar = resultado.plot()

    postura_detectada = "SIN PERSONA"
    confianza = 0.0

    indice = seleccionar_persona(resultado)

    if indice is not None:

        estado["persona_detectada"] = True

        puntos = (
            resultado.keypoints.xy[indice]
            .cpu()
            .numpy()
        )

        confianzas = (
            resultado.keypoints.conf[indice].cpu().numpy()
            if resultado.keypoints.conf is not None
            else None
        )

        if cuerpo_valido(puntos, confianzas):

            caja_persona = (
                resultado.boxes.xyxy[indice]
                .cpu()
                .numpy()
            )

            postura_detectada = detectar_postura(
                puntos,
                confianzas,
                caja_persona,
            )

            confianza = confianza_cuerpo(confianzas)

        else:

            postura_detectada = "DESCONOCIDO"

    else:

        estado["persona_detectada"] = False

    actualizar_postura(
        nombre,
        postura_detectada,
        frame,
        confianza,
    )

    if (
        estado["levantamiento_detectado"]
        and time.time() - estado["tiempo_levantamiento"]
        >= DURACION_AVISO_LEVANTAMIENTO
    ):

        estado["levantamiento_detectado"] = False
        estado["tipo_alerta_levantamiento"] = ""

    postura_actual = estado["postura_actual"]

    if estado["levantamiento_detectado"]:

        texto_levantamiento = (
            estado["tipo_alerta_levantamiento"]
        )

    elif estado["levantamiento_en_proceso"]:

        texto_levantamiento = "EN PROCESO"

    else:

        texto_levantamiento = "NO"

    color_alerta = (
        (0, 0, 255)
        if estado["levantamiento_detectado"]
        else (255, 255, 255)
    )

    lineas = [
        (
            f"{nombre} | ID: "
            f"{CAMARAS_CONFIG[nombre]['id_camara']}",
            30, 0.7, (0, 255, 0)
        ),
        (
            f"POSTURA: {postura_actual}",
            65, 0.9, (0, 255, 0)
        ),
        (
            f"DETECTANDO: {postura_detectada}",
            100, 0.7, (255, 255, 0)
        ),
        (
            f"CONFIRMACION: "
            f"{estado['contador_postura']}/{FRAMES_ESTABILIDAD}",
            135, 0.65, (255, 255, 255)
        ),
        (
            f"CONFIANZA: {confianza * 100:.1f}%",
            170, 0.65, (255, 255, 255)
        ),
        (
            f"LEVANTAMIENTO: {texto_levantamiento}",
            205, 0.65, color_alerta
        ),
        (
            f"TOTAL: {estado['contador_levantamientos']}",
            240, 0.65, (0, 165, 255)
        ),
    ]

    for texto, y, escala, color in lineas:

        cv2.putText(
            frame_mostrar,
            texto,
            (25, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            escala,
            color,
            2,
            cv2.LINE_AA,
        )

    with estado["frame_lock"]:
        estado["frame_mostrar"] = frame_mostrar.copy()

    if transmisor_livekit is not None:

        transmisor_livekit.publicar_frame(
            CAMARAS_CONFIG[nombre]["id_camara"],
            frame_mostrar,
        )

    cv2.imshow(nombre, frame_mostrar)


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    hilos_captura = []
    hilo_backend = None

    try:

        print("=" * 55)

        print(
            "GERIAPP - YOLO POSE: "
            "ACOSTADA / SENTADA / DE PIE"
        )

        print("=" * 55)

        # ----------------------------------------------------
        # CONSULTAR CÁMARAS ACTIVAS
        # ----------------------------------------------------

        print(
            "\nConsultando cámaras activas en GerIApp..."
        )

        camaras_backend = obtener_camaras_activas()

        if not camaras_backend:

            raise RuntimeError(
                "GerIApp no tiene cámaras activas para procesar."
            )

        # ----------------------------------------------------
        # CONSULTAR PACIENTES ACTIVOS
        # ----------------------------------------------------

        pacientes_backend = obtener_pacientes_activos()

        pacientes_por_habitacion = {}

        for paciente in pacientes_backend:

            id_habitacion = (
                paciente.get("id_habitacion")
                or paciente.get("habitacion")
            )

            id_paciente = (
                paciente.get("id_paciente")
                or paciente.get("id")
            )

            if isinstance(id_habitacion, dict):

                id_habitacion = (
                    id_habitacion.get("id_habitacion")
                    or id_habitacion.get("id")
                )

            if (
                id_habitacion is not None
                and id_paciente is not None
            ):

                pacientes_por_habitacion.setdefault(
                    int(id_habitacion),
                    [],
                ).append(int(id_paciente))

        CAMARAS_CONFIG.clear()

        camaras_validas = [
            camara
            for camara in camaras_backend
            if camara.get("estado") is True
            and camara.get("id_habitacion") is not None
        ]

        print("\nAsignación de cámaras físicas:")
        print("- OpenCV índice 0: cámara integrada EXCLUIDA")
        print("- OpenCV índice 1: cámara externa JALTECH 1")
        print("- OpenCV índice 2: cámara externa JALTECH 2")

        # ----------------------------------------------------
        # CONFIGURAR CÁMARAS
        # ----------------------------------------------------

        for camara_api in camaras_validas:

            id_camara = camara_api.get("id_camara")
            id_habitacion = camara_api.get("id_habitacion")

            try:

                id_camara_int = int(id_camara)

            except (TypeError, ValueError):

                print(
                    f"[AVISO] ID de cámara inválido: {id_camara}"
                )

                continue

            indice_opencv = INDICES_CAMARAS.get(
                id_camara_int
            )

            if indice_opencv is None:

                print(
                    f"[AVISO] Cámara GerIApp {id_camara}: "
                    "no tiene índice OpenCV configurado."
                )

                continue

            prueba = abrir_camara_opencv(
                indice_opencv
            )

            disponible = False

            if prueba is not None:

                try:

                    correcto, frame_prueba = prueba.read()

                    disponible = (
                        correcto
                        and frame_prueba is not None
                    )

                finally:

                    prueba.release()

            if not disponible:

                print(
                    f"[AVISO] Cámara GerIApp {id_camara}: "
                    f"OpenCV índice {indice_opencv} "
                    "no entregó una imagen."
                )

                continue

            nombre = (
                camara_api.get("nombre")
                or f"Cámara {id_camara}"
            )

            pacientes_habitacion = (
                pacientes_por_habitacion.get(
                    int(id_habitacion),
                    [],
                )
            )

            id_paciente = (
                pacientes_habitacion[0]
                if len(pacientes_habitacion) == 1
                else None
            )

            CAMARAS_CONFIG[nombre] = {

                "indice_opencv": indice_opencv,
                "id_camara": id_camara,
                "id_habitacion": id_habitacion,
                "id_paciente": id_paciente,

            }

            print(
                f"[CONFIG] {nombre} | "
                f"GerIApp ID: {id_camara} | "
                f"OpenCV índice: {indice_opencv} | "
                f"Habitación: {id_habitacion} | "
                f"Paciente: {id_paciente}"
            )

            if id_paciente is None:

                print(
                    f"[AVISO] {nombre}: hay "
                    f"{len(pacientes_habitacion)} pacientes "
                    "activos en la habitación. "
                    "No se registrarán eventos hasta resolver "
                    "su asociación."
                )

        if not CAMARAS_CONFIG:

            raise RuntimeError(
                "No se encontraron cámaras externas configurables."
            )

        # ----------------------------------------------------
        # CREAR ESTADOS
        # ----------------------------------------------------

        estados.clear()

        estados.update({
            nombre: crear_estado()
            for nombre in CAMARAS_CONFIG
        })

        # ----------------------------------------------------
        # INICIAR SERVIDOR LOCAL DE VIDEO
        # ----------------------------------------------------

        servidor_video = ThreadingHTTPServer(
            (HOST_VIDEO, PUERTO_VIDEO),
            ServidorVideoHandler,
        )

        hilo_video = threading.Thread(
            target=servidor_video.serve_forever,
            daemon=True,
        )

        hilo_video.start()

        print(
            f"\nServidor de video local iniciado en "
            f"http://{HOST_VIDEO}:{PUERTO_VIDEO}"
        )

        print("\nCámaras configuradas para YOLO:")

        for nombre, config in CAMARAS_CONFIG.items():

            print(
                f"- {nombre} | "
                f"GerIApp ID: {config['id_camara']} | "
                f"Habitación: {config['id_habitacion']} | "
                f"Paciente: {config['id_paciente']} | "
                f"OpenCV índice: {config['indice_opencv']}"
            )

        # ----------------------------------------------------
        # ABRIR CÁMARAS
        # ----------------------------------------------------

        for nombre, config in CAMARAS_CONFIG.items():

            indice_opencv = config["indice_opencv"]

            camara = abrir_camara_opencv(
                indice_opencv
            )

            if camara is None:

                print(
                    f"[{nombre}] No se pudo abrir "
                    f"OpenCV índice {indice_opencv}."
                )

                continue

            correcto, primer_frame = camara.read()

            if (
                not correcto
                or primer_frame is None
            ):

                camara.release()

                print(
                    f"[{nombre}] OpenCV índice "
                    f"{indice_opencv} abrió, "
                    "pero no entregó imágenes."
                )

                continue

            estados[nombre]["camara"] = camara

            estados[nombre]["frame"] = (
                primer_frame.copy()
            )

            print(
                f"[{nombre}] Conectada | "
                f"OpenCV índice {indice_opencv} | "
                f"GerIApp ID {config['id_camara']}"
            )

        activas = [
            nombre
            for nombre in CAMARAS_CONFIG
            if estados[nombre]["camara"] is not None
        ]

        if not activas:

            raise RuntimeError(
                "No se pudo abrir ninguna cámara."
            )

        # ----------------------------------------------------
        # CARGAR YOLO
        # ----------------------------------------------------

        print("\nCargando YOLO Pose...")

        modelo = YOLO(MODELO_YOLO)

        print(
            "YOLO Pose cargado correctamente."
        )

        # ----------------------------------------------------
        # INICIAR LIVEKIT
        # ----------------------------------------------------

        global transmisor_livekit

        transmisor_livekit = TransmisionLiveKit()

        for nombre in activas:

            config = CAMARAS_CONFIG[nombre]

            transmisor_livekit.iniciar_camara(
                config["id_camara"],
                config["id_habitacion"],
            )

        print(
            "[LiveKit] Todas las cámaras activas están conectadas."
        )

        # ----------------------------------------------------
        # INICIAR HILOS DE CAPTURA
        # ----------------------------------------------------

        for nombre in activas:

            hilo = threading.Thread(
                target=capturar_camara,
                args=(nombre,),
                daemon=True,
            )

            hilo.start()

            hilos_captura.append(hilo)

        # ----------------------------------------------------
        # INICIAR HILO DEL BACKEND
        # ----------------------------------------------------

        hilo_backend = threading.Thread(
            target=enviar_eventos_backend,
            daemon=True,
        )

        hilo_backend.start()

        print(
            "\nDetección iniciada sin delimitar la cama. "
            "Presiona Q para salir."
        )

        # ----------------------------------------------------
        # BUCLE PRINCIPAL
        # ----------------------------------------------------

        while ejecutando.is_set():

            for nombre in activas:

                procesar_camara(
                    nombre,
                    modelo,
                )

            if cv2.waitKey(1) & 0xFF == ord("q"):

                break

    except KeyboardInterrupt:

        print(
            "Cierre solicitado desde el teclado."
        )

    except Exception as error:

        print(
            "Error en el programa:",
            error,
        )

    finally:

        ejecutando.clear()

        # ----------------------------------------------------
        # CERRAR LIVEKIT
        # ----------------------------------------------------

        if transmisor_livekit is not None:

            try:

                transmisor_livekit.cerrar()

            except Exception as error:

                print(
                    f"[LiveKit] Error al cerrar: {error}"
                )

        # ----------------------------------------------------
        # CERRAR SERVIDOR DE VIDEO
        # ----------------------------------------------------

        if "servidor_video" in locals():

            servidor_video.shutdown()
            servidor_video.server_close()

        if "hilo_video" in locals():

            hilo_video.join(timeout=3)

        # ----------------------------------------------------
        # LIBERAR CÁMARAS
        # ----------------------------------------------------

        for estado in estados.values():

            camara = estado["camara"]

            if camara is not None:

                camara.release()

        # ----------------------------------------------------
        # CERRAR HILOS
        # ----------------------------------------------------

        for hilo in hilos_captura:

            hilo.join(timeout=3)

        if hilo_backend is not None:

            cola_eventos.put(None)

            hilo_backend.join(timeout=30)

            if hilo_backend.is_alive():

                print(
                    "Advertencia: el hilo del backend "
                    "sigue activo."
                )

        cv2.destroyAllWindows()

        print(
            "\nPrograma detenido."
        )

        for nombre, estado in estados.items():

            print(
                f"{nombre}: levantamientos detectados = "
                f"{estado['contador_levantamientos']}"
            )


if __name__ == "__main__":
    main()