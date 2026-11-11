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
    obtener_plantillas_faciales,
)

from reconocimiento_facial.reconocedor import ReconocedorFacial

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
CONFIANZA_MINIMA_CUERPO = 0.35
INTERVALO_MAXIMO_ESTABILIDAD = 0.35
TIEMPO_MAXIMO_PERDIDA_CUERPO = 3.0
DURACION_AVISO_LEVANTAMIENTO = 2
TIEMPO_MAXIMO_DESCONOCIDO = 3.0

# Reconocimiento facial: valores iniciales sujetos a validación en campo.
FPS_RECONOCIMIENTO_FACIAL = 1
UMBRAL_SIMILITUD_FACIAL = 0.55
COINCIDENCIAS_FACIALES_REQUERIDAS = 3
TIEMPO_RETENCION_IDENTIDAD = 8.0
MARGEN_AMBIGUEDAD_FACIAL = 0.08

# Si YOLO no detecta ninguna persona durante este intervalo,
# se considera que la habitación quedó sin personas y se inicia
# un nuevo ciclo de identificación desde cero.
TIEMPO_AUSENCIA_PARA_REINICIAR = 2.0
# Si siguen apareciendo acompañantes, pero no se consigue asociar ningún
# cuerpo al paciente identificado, también se invalida el ciclo anterior.
TIEMPO_MAXIMO_SIN_ASOCIACION_PACIENTE = 3.0

# Cuando no hay paciente identificado, acelerar los intentos faciales
# para que una persona que ingresa pueda ser reconocida sin esperar 1 s.
INTERVALO_RECONOCIMIENTO_SIN_IDENTIDAD = 0.35

CAMARAS_CONFIG = {}
reconocedor_facial = None

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
        "ultimo_frame_candidato": 0.0,
        "contador_sin_persona": 0,
        "ultima_confianza": 0.0,
        "ultimo_frame_valido": time.time(),
        "persona_detectada": False,
        "inicio_sin_personas": None,
        "inicio_sin_asociacion_paciente": None,
        "reinicio_por_ausencia_realizado": False,

        "levantamiento_en_proceso": False,
        "levantamiento_detectado": False,
        "tipo_alerta_levantamiento": "",

        "contador_levantamientos": 0,
        "tiempo_levantamiento": 0,

        "ultimo_procesamiento": 0,

        # Estado independiente del reconocimiento facial.
        "ultimo_procesamiento_facial": 0,
        "candidato_id_paciente": None,
        "contador_coincidencias_facial": 0,
        "ultima_coincidencia_facial": 0.0,
        "ultima_similitud_facial": 0.0,
        "estado_reconocimiento_facial": "SIN INICIAR",
        "rostro_paciente_bbox": None,
        "ultima_deteccion_rostro_paciente": 0.0,
        # Última detección de cualquier rostro, reconocido o no.
        "ultima_deteccion_rostro": 0.0,

        # Seguimiento corporal independiente por cámara.
        "bbox_cuerpo_paciente": None,
        "ultima_deteccion_cuerpo_paciente": 0.0,
        "metodo_asociacion_cuerpo": "SIN ASOCIAR",
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

    # Para ACOSTADA no exigimos una pierna completa: las cobijas,
    # el ángulo lateral y la oclusión suelen ocultar rodillas/tobillos.
    # Basta con detectar al menos un hombro y una cadera.
    return hombros and caderas


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

    # ACOSTADA: priorizar la orientación del tronco y la geometría
    # horizontal de la detección. No exigir rodillas ni tobillos visibles.
    caja_horizontal = False
    if caja is not None:
        x1, y1, x2, y2 = map(float, caja)
        ancho = max(1.0, x2 - x1)
        alto = max(1.0, y2 - y1)
        caja_horizontal = ancho / alto >= 1.20

    hombros_visibles = (
        punto_visible(confianzas, 5)
        or punto_visible(confianzas, 6)
    )
    caderas_visibles = (
        punto_visible(confianzas, 11)
        or punto_visible(confianzas, 12)
    )

    if (
        angulo_tronco >= 55
        and caja_horizontal
        and hombros_visibles
        and caderas_visibles
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

def seleccionar_persona_asociada(resultado, bbox_rostro):
    """
    Selecciona exclusivamente el cuerpo que contiene
    el centro del rostro del paciente reconocido.

    Si no existe una asociación única, devuelve None.
    """

    if (
        bbox_rostro is None
        or resultado.boxes is None
        or resultado.keypoints is None
    ):
        return None

    x1_rostro, y1_rostro, x2_rostro, y2_rostro = bbox_rostro

    centro_x = (x1_rostro + x2_rostro) / 2
    centro_y = (y1_rostro + y2_rostro) / 2

    candidatos = []

    cantidad = min(
        len(resultado.boxes),
        len(resultado.keypoints)
    )

    for i in range(cantidad):

        x1, y1, x2, y2 = (
            resultado.boxes.xyxy[i].cpu().numpy()
        )

        # Comprobar si el centro del rostro está
        # dentro de la detección corporal.

        if (
            x1 <= centro_x <= x2
            and y1 <= centro_y <= y2
        ):
            candidatos.append(i)

    # No existe asociación.
    if len(candidatos) == 0:
        return None

    # Asociación ambigua: no elegir arbitrariamente.
    if len(candidatos) > 1:
        return None

    return candidatos[0]


def calcular_iou(caja_a, caja_b):
    """Calcula IoU entre dos cajas [x1, y1, x2, y2]."""
    ax1, ay1, ax2, ay2 = map(float, caja_a)
    bx1, by1, bx2, by2 = map(float, caja_b)

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def seleccionar_cuerpo_por_seguimiento(resultado, estado, ahora):
    """
    Sigue el cuerpo previamente asociado al paciente cuando el rostro
    deja de verse. Usa continuidad espacial por cámara y rechaza
    asociaciones débiles o ambiguas; nunca elige simplemente el mayor cuerpo.
    """
    caja_anterior = estado.get("bbox_cuerpo_paciente")
    ultima_deteccion = estado.get("ultima_deteccion_cuerpo_paciente", 0.0)

    if (
        caja_anterior is None
        or ultima_deteccion <= 0
        or ahora - ultima_deteccion > TIEMPO_MAXIMO_PERDIDA_CUERPO
        or resultado.boxes is None
        or resultado.keypoints is None
    ):
        return None

    ax1, ay1, ax2, ay2 = map(float, caja_anterior)
    centro_anterior = np.array([(ax1 + ax2) / 2, (ay1 + ay2) / 2])
    diagonal = max(1.0, float(np.hypot(ax2 - ax1, ay2 - ay1)))

    candidatos = []
    cantidad = min(len(resultado.boxes), len(resultado.keypoints))

    for indice in range(cantidad):
        caja = resultado.boxes.xyxy[indice].cpu().numpy().astype(float)
        x1, y1, x2, y2 = caja
        centro = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
        distancia = float(np.linalg.norm(centro - centro_anterior)) / diagonal
        iou = calcular_iou(caja_anterior, caja)

        # Al pasar de sentado a acostado la caja puede cambiar mucho
        # de forma y perder IoU. Permitimos mayor desplazamiento del centro,
        # pero seguimos exigiendo proximidad respecto al tamaño anterior.
        if iou < 0.01 and distancia > 0.65:
            continue

        puntuacion_distancia = max(0.0, 1.0 - distancia / 0.65)
        puntuacion = 0.45 * iou + 0.55 * puntuacion_distancia
        candidatos.append((puntuacion, indice, caja, iou, distancia))

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: item[0], reverse=True)

    # Si dos personas pueden corresponder al mismo seguimiento, no adivinar.
    if len(candidatos) > 1:
        if candidatos[0][0] - candidatos[1][0] < 0.12:
            return None

    mejor = candidatos[0]
    if mejor[0] < 0.25:
        return None

    return mejor[1]

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
# RECONOCIMIENTO FACIAL POR CÁMARA
# ============================================================

def limpiar_identidad_camara(nombre, motivo):
    """Retira la identidad asociada cuando ya no es confiable."""

    estado = estados[nombre]
    config = CAMARAS_CONFIG[nombre]

    config["id_paciente"] = None

    estado["candidato_id_paciente"] = None
    estado["contador_coincidencias_facial"] = 0
    estado["ultima_similitud_facial"] = 0.0
    estado["estado_reconocimiento_facial"] = motivo

    estado["rostro_paciente_bbox"] = None
    estado["ultima_deteccion_rostro_paciente"] = 0.0
    estado["bbox_cuerpo_paciente"] = None
    estado["ultima_deteccion_cuerpo_paciente"] = 0.0
    estado["metodo_asociacion_cuerpo"] = "SIN ASOCIAR"


def reiniciar_ciclo_camara(nombre, motivo="AUSENCIA DE PERSONAS"):
    """Reinicia la identidad y el ciclo de posturas de una cámara.

    Conserva el contador histórico de levantamientos, la cámara y la
    transmisión. Elimina toda asociación activa para que la siguiente
    persona deba ser reconocida desde cero.
    """
    estado = estados[nombre]

    limpiar_identidad_camara(nombre, "SIN INICIAR - NUEVO CICLO")

    estado["ultima_coincidencia_facial"] = 0.0
    estado["ultimo_procesamiento_facial"] = 0.0
    estado["ultima_deteccion_rostro"] = 0.0
    estado["ultima_similitud_facial"] = 0.0
    estado["candidato_id_paciente"] = None
    estado["contador_coincidencias_facial"] = 0

    estado["postura_actual"] = "SIN PERSONA"
    estado["postura_candidata"] = "DESCONOCIDO"
    estado["ultima_postura_valida"] = "SIN PERSONA"
    estado["postura_anterior"] = "DESCONOCIDO"
    estado["contador_postura"] = 0
    estado["ultimo_frame_candidato"] = 0.0
    estado["contador_sin_persona"] = 0
    estado["ultima_confianza"] = 0.0
    estado["ultimo_frame_valido"] = time.time()

    estado["levantamiento_en_proceso"] = False
    estado["levantamiento_detectado"] = False
    estado["tipo_alerta_levantamiento"] = ""
    estado["tiempo_levantamiento"] = 0

    estado["persona_detectada"] = False
    estado["inicio_sin_asociacion_paciente"] = None
    estado["estado_reconocimiento_facial"] = "SIN PERSONA - ESPERANDO INGRESO"

    print(
        f"[{nombre}] Ciclo reiniciado: {motivo}. "
        "La próxima persona deberá identificarse nuevamente."
    )


def actualizar_identidad_facial(nombre, frame):
    """
    Reconoce múltiples rostros por cámara.

    - Procesa todos los rostros detectados.
    - Compara cada embedding contra las plantillas disponibles.
    - Permite identificar un paciente aunque haya acompañantes.
    - Si aparecen varios pacientes registrados, evita asignar
      una identidad ambigua.
    - Requiere coincidencias consecutivas para confirmar.
    - Conserva temporalmente la última identidad si no hay rostros.
    """

    estado = estados[nombre]
    config = CAMARAS_CONFIG[nombre]
    ahora = time.time()

    if reconocedor_facial is None:
        config["id_paciente"] = None
        estado["rostro_paciente_bbox"] = None
        estado["ultima_deteccion_rostro_paciente"] = 0.0
        estado["estado_reconocimiento_facial"] = "RECONOCEDOR NO DISPONIBLE"
        return

    plantillas = config.get("plantillas_faciales", [])

    if not plantillas:
        config["id_paciente"] = None
        estado["rostro_paciente_bbox"] = None
        estado["ultima_deteccion_rostro_paciente"] = 0.0
        estado["estado_reconocimiento_facial"] = "SIN PLANTILLAS"

    # Al no existir una identidad confirmada, buscar rostros con mayor
    # frecuencia. Una vez identificado el paciente, volver al FPS normal.
    intervalo_facial = (
        INTERVALO_RECONOCIMIENTO_SIN_IDENTIDAD
        if config.get("id_paciente") is None
        else 1 / FPS_RECONOCIMIENTO_FACIAL
    )
    if (
        ahora - estado["ultimo_procesamiento_facial"]
        < intervalo_facial
    ):
        return

    estado["ultimo_procesamiento_facial"] = ahora

    correcto, imagen_jpg = cv2.imencode(".jpg", frame)

    if not correcto:
        estado["rostro_paciente_bbox"] = None
        estado["ultima_deteccion_rostro_paciente"] = 0.0
        estado["estado_reconocimiento_facial"] = (
            "ERROR AL CODIFICAR IMAGEN"
        )
        return

    try:
        rostros = reconocedor_facial.procesar_imagen(
            imagen_jpg.tobytes()
        )

        # Segundo intento con imagen ampliada: puede ayudar cuando el rostro
        # ocupa pocos píxeles. Las coordenadas se convierten de vuelta al
        # tamaño original para mantener la asociación con YOLO.
        if not rostros:
            escala = 1.5
            frame_ampliado = cv2.resize(
                frame,
                None,
                fx=escala,
                fy=escala,
                interpolation=cv2.INTER_CUBIC,
            )
            correcto_ampliado, jpg_ampliado = cv2.imencode(
                ".jpg", frame_ampliado
            )
            if correcto_ampliado:
                rostros_ampliados = reconocedor_facial.procesar_imagen(
                    jpg_ampliado.tobytes()
                )
                rostros = rostros_ampliados or []
                for rostro in rostros:
                    for clave in ("x", "y", "ancho", "alto"):
                        if rostro.get(clave) is not None:
                            rostro[clave] = int(round(
                                float(rostro[clave]) / escala
                            ))

    except Exception as error:

        # No utilizar coordenadas antiguas si falla el reconocimiento.
        estado["rostro_paciente_bbox"] = None
        estado["ultima_deteccion_rostro_paciente"] = 0.0

        estado["estado_reconocimiento_facial"] = (
            "ERROR DE RECONOCIMIENTO"
        )

        if (
            config["id_paciente"] is not None
            and ahora - estado["ultima_coincidencia_facial"]
            > TIEMPO_RETENCION_IDENTIDAD
        ):
            limpiar_identidad_camara(
                nombre,
                "IDENTIDAD VENCIDA"
            )

        print(
            f"[{nombre}] Error en reconocimiento facial: {error}"
        )
        return

    # Registrar presencia facial independientemente de que el rostro
    # pertenezca a un paciente registrado o pueda asociarse a un cuerpo.
    if len(rostros) > 0:
        estado["ultima_deteccion_rostro"] = ahora

    # ==================================================
    # 1. CUANDO NO SE DETECTAN ROSTROS
    # ==================================================

    if len(rostros) == 0:

        # Limpiar las coordenadas del último rostro detectado.
        # La identidad puede conservarse temporalmente, pero no
        # se debe asociar un cuerpo usando un rostro antiguo.
        estado["rostro_paciente_bbox"] = None
        estado["ultima_deteccion_rostro_paciente"] = 0.0

        estado["candidato_id_paciente"] = None
        estado["contador_coincidencias_facial"] = 0

        seguimiento_corporal_reciente = (
            estado.get("bbox_cuerpo_paciente") is not None
            and estado.get("ultima_deteccion_cuerpo_paciente", 0.0) > 0
            and ahora - estado["ultima_deteccion_cuerpo_paciente"]
            <= TIEMPO_MAXIMO_PERDIDA_CUERPO
        )

        retencion_facial_vigente = (
            ahora - estado["ultima_coincidencia_facial"]
            <= TIEMPO_RETENCION_IDENTIDAD
        )

        if (
            config["id_paciente"] is not None
            and (retencion_facial_vigente or seguimiento_corporal_reciente)
        ):

            estado["estado_reconocimiento_facial"] = (
                "IDENTIDAD CONSERVADA POR SEGUIMIENTO CORPORAL"
                if seguimiento_corporal_reciente and not retencion_facial_vigente
                else "IDENTIDAD CONSERVADA TEMPORALMENTE"
            )

        else:

            limpiar_identidad_camara(
                nombre,
                "ROSTRO NO DETECTADO"
            )

        return

    # ==================================================
    # 2. COMPARAR TODOS LOS ROSTROS DETECTADOS
    # ==================================================

    pacientes_reconocidos = {}

    rostros_ambiguos = 0

    for rostro in rostros:

        embedding_capturado = np.asarray(
            rostro.get("embedding"),
            dtype=np.float32
        )

        if (
            embedding_capturado.shape != (128,)
            or not np.all(np.isfinite(embedding_capturado))
        ):
            continue

        mejores_por_paciente = {}

        # Comparar el rostro actual con todas las plantillas.
        for plantilla in plantillas:

            id_paciente = plantilla.get("id_paciente")

            embedding_registrado = np.asarray(
                plantilla.get("embedding"),
                dtype=np.float32
            )

            if (
                id_paciente is None
                or embedding_registrado.shape != (128,)
                or not np.all(np.isfinite(embedding_registrado))
            ):
                continue

            similitud = float(
                np.dot(
                    embedding_capturado,
                    embedding_registrado
                )
            )

            if (
                id_paciente not in mejores_por_paciente
                or similitud > mejores_por_paciente[id_paciente]
            ):
                mejores_por_paciente[id_paciente] = similitud

        if not mejores_por_paciente:
            continue

        ordenados = sorted(
            mejores_por_paciente.items(),
            key=lambda elemento: elemento[1],
            reverse=True
        )

        mejor_id, mejor_similitud = ordenados[0]

        # Descartar rostros que no superen el umbral.
        if mejor_similitud < UMBRAL_SIMILITUD_FACIAL:
            continue

        # Comprobar si la identidad de este rostro es ambigua.
        if (
            len(ordenados) > 1
            and ordenados[0][1] - ordenados[1][1]
            < MARGEN_AMBIGUEDAD_FACIAL
        ):

            rostros_ambiguos += 1

            print(
                f"[{nombre}] Rostro {rostro.get('indice')} "
                "con identidad ambigua."
            )

            continue

        # Guardar el paciente reconocido.
        # Si hay varias detecciones asociadas al mismo paciente,
        # conservar la que tenga mayor similitud.
        if (
            mejor_id not in pacientes_reconocidos
            or mejor_similitud
            > pacientes_reconocidos[mejor_id]["similitud"]
        ):

            pacientes_reconocidos[mejor_id] = {
                "similitud": mejor_similitud,
                "rostro": rostro
            }

    # ==================================================
    # 3. EVALUAR LOS PACIENTES RECONOCIDOS
    # ==================================================

    if len(pacientes_reconocidos) == 0:

        estado["candidato_id_paciente"] = None
        estado["contador_coincidencias_facial"] = 0

        # Si solo aparecen rostros de acompañantes/no registrados, no
        # borrar inmediatamente la identidad ya confirmada del paciente.
        # Se conserva únicamente dentro de la ventana de retención facial
        # o mientras el cuerpo previamente asociado siga siendo seguido.
        seguimiento_corporal_reciente = (
            estado.get("bbox_cuerpo_paciente") is not None
            and estado.get("ultima_deteccion_cuerpo_paciente", 0.0) > 0
            and ahora - estado["ultima_deteccion_cuerpo_paciente"]
            <= TIEMPO_MAXIMO_PERDIDA_CUERPO
        )
        retencion_facial_vigente = (
            config.get("id_paciente") is not None
            and ahora - estado["ultima_coincidencia_facial"]
            <= TIEMPO_RETENCION_IDENTIDAD
        )

        if config.get("id_paciente") is not None and (
            seguimiento_corporal_reciente or retencion_facial_vigente
        ):
            estado["estado_reconocimiento_facial"] = (
                "ROSTRO NO RECONOCIDO; IDENTIDAD RETENIDA"
            )
            return

        limpiar_identidad_camara(
            nombre,
            "NINGUN PACIENTE RECONOCIDO"
        )
        return

    # Si se reconocen dos o más pacientes distintos,
    # no se asigna ninguna identidad a la cámara.
    if len(pacientes_reconocidos) > 1:

        estado["candidato_id_paciente"] = None
        estado["contador_coincidencias_facial"] = 0

        limpiar_identidad_camara(
            nombre,
            "VARIOS PACIENTES RECONOCIDOS"
        )

        print(
            f"[{nombre}] Se reconocieron varios pacientes "
            "en el mismo fotograma."
        )

        return

    # ==================================================
    # 4. OBTENER EL ÚNICO PACIENTE RECONOCIDO
    # ==================================================

    mejor_id, datos_reconocimiento = next(
        iter(pacientes_reconocidos.items())
    )

    mejor_similitud = datos_reconocimiento["similitud"]

    rostro_identificado = datos_reconocimiento["rostro"]

    estado["ultima_similitud_facial"] = mejor_similitud

    # Renovar tiempo de coincidencia.
    estado["ultima_coincidencia_facial"] = ahora

    # ==================================================
    # 5. VALIDAR COINCIDENCIAS CONSECUTIVAS
    # ==================================================

    if estado["candidato_id_paciente"] == mejor_id:

        estado["contador_coincidencias_facial"] += 1

    else:

        estado["candidato_id_paciente"] = mejor_id
        estado["contador_coincidencias_facial"] = 1

    # Evitar conservar la identidad de otro paciente.
    if (
        config["id_paciente"] is not None
        and config["id_paciente"] != mejor_id
    ):

        config["id_paciente"] = None

    # ==================================================
    # 6. CONFIRMAR IDENTIDAD
    # ==================================================

    if (
        estado["contador_coincidencias_facial"]
        >= COINCIDENCIAS_FACIALES_REQUERIDAS
    ):

        era_otro = config["id_paciente"] != mejor_id

        config["id_paciente"] = mejor_id

        # Guardar el recuadro facial solamente cuando la identidad
        # ya está confirmada. Si se está validando otro paciente,
        # no se habilita la asociación con YOLO.
        x = rostro_identificado.get("x")
        y = rostro_identificado.get("y")
        ancho = rostro_identificado.get("ancho")
        alto = rostro_identificado.get("alto")

        if all(
            valor is not None
            for valor in (x, y, ancho, alto)
        ):
            estado["rostro_paciente_bbox"] = (
                int(x),
                int(y),
                int(x + ancho),
                int(y + alto),
            )
            estado["ultima_deteccion_rostro_paciente"] = ahora
        else:
            estado["rostro_paciente_bbox"] = None
            estado["ultima_deteccion_rostro_paciente"] = 0.0

        estado["estado_reconocimiento_facial"] = (
            "PACIENTE IDENTIFICADO"
        )

        if era_otro:

            print(
                f"[{nombre}] Identidad confirmada: paciente "
                f"{mejor_id} | "
                f"similitud {mejor_similitud:.3f} | "
                f"rostro {rostro_identificado.get('indice')}"
            )

    else:

        estado["estado_reconocimiento_facial"] = (
            f"VALIDANDO "
            f"{estado['contador_coincidencias_facial']}/"
            f"{COINCIDENCIAS_FACIALES_REQUERIDAS}"
        )

# ============================================================
# ACTUALIZAR LA POSTURA DE UNA CÁMARA
# ============================================================

def actualizar_postura(
    nombre,
    postura_detectada,
    imagen,
    confianza=0.0,
):
    """
    Confirma posturas mediante estabilidad temporal y registra eventos
    únicamente cuando se cumple la secuencia ACOSTADA -> SENTADA -> DE PIE.
    """
    estado = estados[nombre]
    ahora = time.time()

    if postura_detectada == "SIN PERSONA":
        estado["contador_sin_persona"] += 1
        estado["contador_postura"] = 0
        estado["postura_candidata"] = "SIN PERSONA"
        estado["ultimo_frame_candidato"] = ahora

        if estado["contador_sin_persona"] >= MAX_SIN_PERSONA:
            anterior = estado["ultima_postura_valida"]
            estado["postura_actual"] = "SIN PERSONA"
            estado["ultima_postura_valida"] = "SIN PERSONA"
            estado["postura_anterior"] = anterior
            estado["levantamiento_en_proceso"] = False
        return

    estado["contador_sin_persona"] = 0

    if postura_detectada == "DESCONOCIDO":
        if ahora - estado["ultimo_frame_valido"] > TIEMPO_MAXIMO_DESCONOCIDO:
            estado["postura_actual"] = "DESCONOCIDO"
        estado["contador_postura"] = 0
        estado["postura_candidata"] = "DESCONOCIDO"
        estado["ultimo_frame_candidato"] = 0.0
        return

    # No aceptar una postura si la confianza agregada es insuficiente.
    if confianza < CONFIANZA_MINIMA_CUERPO:
        estado["contador_postura"] = 0
        estado["postura_candidata"] = "DESCONOCIDO"
        estado["ultimo_frame_candidato"] = 0.0
        return

    estado["ultimo_frame_valido"] = ahora
    estado["ultima_confianza"] = confianza

    # Reiniciar la secuencia si hubo un intervalo excesivo entre frames.
    if (
        estado["ultimo_frame_candidato"] > 0
        and ahora - estado["ultimo_frame_candidato"] > INTERVALO_MAXIMO_ESTABILIDAD
    ):
        estado["contador_postura"] = 0
        estado["postura_candidata"] = "DESCONOCIDO"

    estado["ultimo_frame_candidato"] = ahora

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
    estado["ultimo_frame_candidato"] = 0.0

    if postura_detectada == "ACOSTADA":
        if estado["levantamiento_en_proceso"]:
            print(f"[{nombre}] Regresó a ACOSTADA; levantamiento cancelado.")
        estado["levantamiento_en_proceso"] = False
        print(f"[{nombre}] Postura ACOSTADA confirmada.")
        return

    if anterior == "ACOSTADA" and postura_detectada == "SENTADA":
        estado["levantamiento_en_proceso"] = True
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "INICIO"
        estado["tiempo_levantamiento"] = ahora
        registrar_evento(nombre, TIPO_PACIENTE_SENTADO, imagen, confianza)
        print(f"[{nombre}] ACOSTADA -> SENTADA: inicio confirmado.")
        return

    if postura_detectada == "DE PIE":
        if anterior == "SENTADA" and estado["levantamiento_en_proceso"]:
            estado["levantamiento_en_proceso"] = False
            estado["levantamiento_detectado"] = True
            estado["tipo_alerta_levantamiento"] = "COMPLETADO"
            estado["tiempo_levantamiento"] = ahora
            estado["contador_levantamientos"] += 1
            registrar_evento(nombre, TIPO_LEVANTAMIENTO_COMPLETO, imagen, confianza)
            print(f"[{nombre}] SENTADA -> DE PIE: levantamiento completado.")
        elif anterior == "ACOSTADA":
            # No registrar un levantamiento completo saltándose SENTADA.
            estado["levantamiento_en_proceso"] = False
            print(f"[{nombre}] ACOSTADA -> DE PIE: transición ignorada; falta SENTADA.")
        else:
            estado["levantamiento_en_proceso"] = False


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

    postura_detectada = "DESCONOCIDO"
    confianza = 0.0

    # ==================================================
    # ASOCIAR EL CUERPO AL PACIENTE RECONOCIDO
    # ==================================================
    # Nunca seleccionar simplemente el cuerpo más grande: podría
    # pertenecer a un acompañante y generar una postura incorrecta.

    config = CAMARAS_CONFIG[nombre]

    # Separar detección de cajas YOLO, puntos de pose y presencia facial.
    # Una persona puede estar visible de cara aunque YOLO no genere pose.
    hay_personas_yolo = (
        resultado.boxes is not None
        and len(resultado.boxes) > 0
    )
    hay_detecciones_pose = (
        hay_personas_yolo
        and resultado.keypoints is not None
    )

    # Ejecutar reconocimiento facial sin depender de que YOLO encuentre
    # cajas o keypoints. La propia función controla su intervalo de FPS.
    actualizar_identidad_facial(nombre, frame)

    tiempo_ultima_cara = estado.get("ultima_deteccion_rostro", 0.0)
    rostro_reciente_cualquiera = (
        tiempo_ultima_cara > 0
        and (time.time() - tiempo_ultima_cara) <= 2.0
    )
    hay_presencia = hay_personas_yolo or rostro_reciente_cualquiera
    estado["persona_detectada"] = bool(hay_presencia)

    identidad_confirmada = config.get("id_paciente") is not None
    bbox_rostro = estado.get("rostro_paciente_bbox")
    tiempo_rostro = estado.get(
        "ultima_deteccion_rostro_paciente", 0.0
    )
    rostro_reciente = (
        bbox_rostro is not None
        and tiempo_rostro > 0
        and (time.time() - tiempo_rostro) <= 2.0
    )
    indice = None

    # ==================================================
    # DETECTAR AUSENCIA REAL (SIN CAJAS YOLO NI ROSTROS)
    # ==================================================
    if not hay_presencia:
        if estado.get("inicio_sin_personas") is None:
            estado["inicio_sin_personas"] = time.time()
            estado["bbox_cuerpo_paciente"] = None
            estado["ultima_deteccion_cuerpo_paciente"] = 0.0
            estado["metodo_asociacion_cuerpo"] = "SIN PERSONAS EN IMAGEN"

        tiempo_ausencia = time.time() - estado["inicio_sin_personas"]

        if (
            tiempo_ausencia >= TIEMPO_AUSENCIA_PARA_REINICIAR
            and not estado.get("reinicio_por_ausencia_realizado", False)
        ):
            reiniciar_ciclo_camara(
                nombre,
                f"ninguna persona ni rostro detectado durante {tiempo_ausencia:.1f} s",
            )
            estado["reinicio_por_ausencia_realizado"] = True

        postura_detectada = "SIN PERSONA"
        confianza = 0.0
        indice = None
    else:
        estado["inicio_sin_personas"] = None
        estado["reinicio_por_ausencia_realizado"] = False

        # Si solo hay rostro y no hay pose, conservar la identidad facial,
        # pero no inventar una postura ni asociar un cuerpo.
        if not hay_detecciones_pose:
            postura_detectada = "DESCONOCIDO"
            confianza = 0.0

    if identidad_confirmada and hay_detecciones_pose:
        if rostro_reciente:
            # El rostro es el ancla más fiable: asociar directamente.
            indice = seleccionar_persona_asociada(resultado, bbox_rostro)
            if indice is not None:
                estado["metodo_asociacion_cuerpo"] = "ROSTRO"
        else:
            # Si el rostro está oculto, continuar únicamente desde la
            # última caja corporal que ya pertenecía al paciente.
            indice = seleccionar_cuerpo_por_seguimiento(
                resultado, estado, time.time()
            )
            if indice is not None:
                estado["metodo_asociacion_cuerpo"] = "SEGUIMIENTO"

    if indice is not None:
        puntos = resultado.keypoints.xy[indice].cpu().numpy()
        confianzas = (
            resultado.keypoints.conf[indice].cpu().numpy()
            if resultado.keypoints.conf is not None
            else None
        )
        caja_persona = resultado.boxes.xyxy[indice].cpu().numpy()

        # Actualizar el ancla corporal solo si los puntos son válidos
        # y el cuerpo tiene confianza suficiente.
        confianza = confianza_cuerpo(confianzas)

        # En postura acostada las piernas pueden quedar ocultas. Calculamos
        # también la confianza del torso para no descartar ese caso.
        indices_torso = [i for i in (5, 6, 11, 12)
                         if confianzas is not None
                         and len(confianzas) > i
                         and float(confianzas[i]) >= 0.25]
        confianza_torso = (
            float(np.mean([float(confianzas[i]) for i in indices_torso]))
            if indices_torso else 0.0
        )
        if confianza < CONFIANZA_MINIMA_CUERPO:
            confianza = max(confianza, confianza_torso)

        if (
            cuerpo_valido(puntos, confianzas)
            and confianza >= 0.30
        ):
            postura_detectada = detectar_postura(
                puntos, confianzas, caja_persona
            )
            estado["bbox_cuerpo_paciente"] = tuple(
                float(valor) for valor in caja_persona
            )
            estado["ultima_deteccion_cuerpo_paciente"] = time.time()
        else:
            postura_detectada = "DESCONOCIDO"
    else:
        postura_detectada = "DESCONOCIDO"
        # Si el seguimiento se perdió por demasiado tiempo, invalidar
        # el ancla para impedir que se recupere un acompañante por error.
        ultima_caja = estado.get("ultima_deteccion_cuerpo_paciente", 0.0)
        if (
            ultima_caja > 0
            and time.time() - ultima_caja > TIEMPO_MAXIMO_PERDIDA_CUERPO
        ):
            estado["bbox_cuerpo_paciente"] = None
            estado["ultima_deteccion_cuerpo_paciente"] = 0.0
            estado["metodo_asociacion_cuerpo"] = "SEGUIMIENTO PERDIDO"

    # Si hay otras personas visibles, pero el cuerpo del paciente ya no
    # puede asociarse durante varios segundos, también cerrar el ciclo.
    # Así no se conserva la identidad anterior mientras un acompañante
    # permanece dentro del campo de visión.
    if hay_detecciones_pose and config.get("id_paciente") is not None:
        ultima_asociacion = estado.get(
            "ultima_deteccion_cuerpo_paciente", 0.0
        )

        if ultima_asociacion > 0:
            tiempo_sin_asociacion = time.time() - ultima_asociacion
        else:
            if estado.get("inicio_sin_asociacion_paciente") is None:
                estado["inicio_sin_asociacion_paciente"] = time.time()
            tiempo_sin_asociacion = (
                time.time() - estado["inicio_sin_asociacion_paciente"]
            )

        if tiempo_sin_asociacion <= TIEMPO_MAXIMO_SIN_ASOCIACION_PACIENTE:
            estado["inicio_sin_asociacion_paciente"] = None
        else:
            reiniciar_ciclo_camara(
                nombre,
                "no se pudo asociar el cuerpo del paciente durante "
                f"{tiempo_sin_asociacion:.1f} s",
            )
            estado["reinicio_por_ausencia_realizado"] = False
    else:
        estado["inicio_sin_asociacion_paciente"] = None

    if hay_detecciones_pose:
        actualizar_postura(
            nombre,
            postura_detectada,
            frame,
            confianza,
        )
    elif not estado.get("reinicio_por_ausencia_realizado", False):
        # Sin pose corporal no generar transiciones ni eventos, aunque
        # exista presencia facial o cajas YOLO sin keypoints.
        estado["postura_actual"] = "DESCONOCIDO"
        estado["contador_postura"] = 0
        estado["postura_candidata"] = "DESCONOCIDO"
        estado["ultimo_frame_candidato"] = 0.0

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
        (
            f"PACIENTE: {CAMARAS_CONFIG[nombre]['id_paciente'] or 'NO IDENTIFICADO'}",
            275, 0.60, (0, 255, 255)
        ),
        (
            f"FACIAL: {estado['estado_reconocimiento_facial']} "
            f"({estado['ultima_similitud_facial']:.2f})",
            305, 0.50, (0, 255, 255)
        ),
        (
            f"CUERPO: {estado['metodo_asociacion_cuerpo']}",
            335, 0.55, (255, 200, 0)
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

    global transmisor_livekit, reconocedor_facial

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
        # INICIALIZAR RECONOCIMIENTO FACIAL
        # ----------------------------------------------------

        try:
            print("\\nInicializando YuNet y SFace...")
            reconocedor_facial = ReconocedorFacial()
            print("[Facial] YuNet y SFace inicializados correctamente.")
        except Exception as error:
            reconocedor_facial = None
            print(
                "[Facial] No se pudo inicializar el reconocedor. "
                "YOLO continuará, pero no se asociarán pacientes:",
                error
            )

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

            plantillas_faciales = []

            if reconocedor_facial is not None:
                try:
                    plantillas_faciales = obtener_plantillas_faciales(
                        id_camara_int
                    )
                except Exception as error:
                    print(
                        f"[{nombre}] No se pudieron obtener las plantillas "
                        f"faciales. Los eventos no se asociarán a pacientes: "
                        f"{error}"
                    )

            CAMARAS_CONFIG[nombre] = {

                "indice_opencv": indice_opencv,
                "id_camara": id_camara,
                "id_habitacion": id_habitacion,

                # La identidad inicia vacía y solo se asigna por reconocimiento.
                "id_paciente": None,
                "plantillas_faciales": plantillas_faciales,

            }

            print(
                f"[CONFIG] {nombre} | "
                f"GerIApp ID: {id_camara} | "
                f"OpenCV índice: {indice_opencv} | "
                f"Habitación: {id_habitacion} | "
                f"Plantillas faciales: {len(plantillas_faciales)}"
            )

            if not plantillas_faciales:
                print(
                    f"[AVISO] {nombre}: no hay plantillas faciales "
                    "disponibles. YOLO funcionará, pero no se asociarán "
                    "eventos a pacientes."
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
                f"Paciente inicial: NO IDENTIFICADO | "
                f"Plantillas: {len(config['plantillas_faciales'])} | "
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