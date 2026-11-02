
import cv2
import numpy as np
import threading
import time
import queue
from ultralytics import YOLO
import os
from dotenv import load_dotenv
load_dotenv()
import re
import subprocess

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
# CAPTURA POR IDENTIFICADOR DEL DISPOSITIVO USB
# ============================================================

ANCHO_CAMARA = 640
ALTO_CAMARA = 480
FPS_CAMARA = 30


def normalizar_identificador(valor):
    """Normaliza el identificador USB para compararlo con FFmpeg."""
    return re.sub(r"[^a-z0-9]", "", str(valor).lower())


def obtener_dispositivos_dshow():
    """Obtiene los nombres alternativos de las cámaras de Windows."""
    resultado = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-list_devices", "true",
            "-f", "dshow",
            "-i", "dummy",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    lineas = resultado.stderr.splitlines()
    dispositivos = []

    for i, linea in enumerate(lineas):
        nombre = re.search(r'"([^"]+)"\s+\(video\)', linea)

        if not nombre:
            continue

        for siguiente in lineas[i + 1:i + 4]:
            alternativa = re.search(
                r'Alternative name "([^"]+)"',
                siguiente,
            )

            if alternativa:
                dispositivos.append({
                    "nombre": nombre.group(1),
                    "alternativa": alternativa.group(1),
                })
                break

            if "(video)" in siguiente:
                break

    return dispositivos


def buscar_dispositivo_usb(identificador, dispositivos):
    """Relaciona el identificador del backend con el dispositivo físico."""
    if not identificador:
        return None

    objetivo = normalizar_identificador(identificador)

    for dispositivo in dispositivos:
        alternativa = normalizar_identificador(
            dispositivo["alternativa"]
        )

        if objetivo in alternativa:
            return dispositivo["alternativa"]

    return None


class CapturaFFmpeg:
    """Interfaz compatible con read(), isOpened() y release()."""

    def __init__(self, dispositivo):
        self.bytes_frame = ANCHO_CAMARA * ALTO_CAMARA * 3

        comando = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "dshow",
            "-video_size", f"{ANCHO_CAMARA}x{ALTO_CAMARA}",
            "-framerate", str(FPS_CAMARA),
            "-i", f"video={dispositivo}",
            "-vf", "fps=15",
            "-an",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "pipe:1",
        ]
        self.proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=self.bytes_frame * 2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def isOpened(self):
        return (
            self.proceso is not None
            and self.proceso.poll() is None
        )

    def read(self):
        if not self.isOpened():
            return False, None

        datos = bytearray()

        while len(datos) < self.bytes_frame:
            bloque = self.proceso.stdout.read(
                self.bytes_frame - len(datos)
            )

            if not bloque:
                return False, None

            datos.extend(bloque)

        imagen = np.frombuffer(
            datos,
            dtype=np.uint8,
        ).reshape(
            (ALTO_CAMARA, ANCHO_CAMARA, 3)
        ).copy()

        return True, imagen

    def release(self):
        if self.proceso is None:
            return

        if self.proceso.poll() is None:
            self.proceso.terminate()

            try:
                self.proceso.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
                self.proceso.wait()

        if self.proceso.stdout:
            self.proceso.stdout.close()

        self.proceso = None


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

MODELO_YOLO = "./runs/classify/train-3/weights/best.pt"
FPS_YOLO = 10
TAMANO_YOLO = 640
CONFIANZA_MINIMA_PUNTO = 0.35
FRAMES_ESTABILIDAD = 5
MAX_SIN_PERSONA = 15
DURACION_AVISO_LEVANTAMIENTO = 2

# Esta configuración se construirá desde el backend al iniciar.
CAMARAS_CONFIG = {}

TIPO_PACIENTE_SENTADO = 2
TIPO_LEVANTAMIENTO_COMPLETO = 4
CONFIANZA_EVENTO = 95.00


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

        "levantamiento_en_proceso": False,
        "levantamiento_detectado": False,
        "tipo_alerta_levantamiento": "",

        "contador_levantamientos": 0,
        "tiempo_levantamiento": 0,

        "ultimo_procesamiento": 0,
    }


# Se crean cuando se consultan las cámaras del backend.
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
            # El navegador cerró la conexión.
            pass

    def log_message(self, formato, *argumentos):
        # Evitar mensajes repetitivos por cada conexión.
        pass

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

def registrar_evento(nombre, tipo_evento, imagen):
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
        "confianza": CONFIANZA_EVENTO,
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

            # La imagen proviene de la cámara que generó el evento.
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
            print("Error procesando evento:", error)

        finally:
            cola_eventos.task_done()


# ============================================================
# ACTUALIZAR LA POSTURA DE UNA CÁMARA
# Conserva la secuencia de la versión original.
# ============================================================

def actualizar_postura(nombre, postura_detectada, imagen):
    estado = estados[nombre]

    # Normalizar texto para evitar errores por espacios o mayúsculas
    postura_detectada = postura_detectada.strip().upper()

    # Contar ausencia de persona.
    if postura_detectada == "SIN PERSONA":
        estado["contador_sin_persona"] += 1
        if estado["contador_sin_persona"] >= MAX_SIN_PERSONA:
            estado["postura_candidata"] = "SIN PERSONA"
            estado["contador_postura"] = 0
            estado["postura_actual"] = "SIN PERSONA"
            estado["postura_anterior"] = "SIN PERSONA"
            estado["ultima_postura_valida"] = "SIN PERSONA"
            estado["levantamiento_en_proceso"] = False
            estado["levantamiento_detectado"] = False
            estado["tipo_alerta_levantamiento"] = ""
        return

    estado["contador_sin_persona"] = 0

    if postura_detectada == "DESCONOCIDO":
        estado["postura_actual"] = "DESCONOCIDO"
        estado["postura_candidata"] = "DESCONOCIDO"
        estado["contador_postura"] = 0
        return

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

    estado["postura_anterior"] = estado["ultima_postura_valida"]
    estado["ultima_postura_valida"] = postura_detectada
    estado["postura_actual"] = postura_detectada
    estado["contador_postura"] = 0

    anterior = estado["postura_anterior"]
    actual = estado["postura_actual"]
    
    # 🔍 Imprimir cambios de estado para depurar en consola
    print(f"[{nombre}] Transición detectada: {anterior} ➔ {actual}")

    if actual in ["ACOSTADO", "ACOSTADA"]:
        estado["levantamiento_en_proceso"] = False
        print(f"[{nombre}] Persona ACOSTADA.")

    # ACOSTADA -> SENTADA
    elif anterior in ["ACOSTADO", "ACOSTADA"] and actual == "SENTADA":
        estado["levantamiento_en_proceso"] = True
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "INICIO"
        estado["tiempo_levantamiento"] = time.time()

        registrar_evento(
            nombre,
            TIPO_PACIENTE_SENTADO,
            imagen,
        )
        print(f"[{nombre}] INICIO DE LEVANTAMIENTO (ACOSTADA -> SENTADA)")

    # SENTADA -> DE PIE (o INCORPORADO)
    elif (
        estado["levantamiento_en_proceso"]
        and anterior == "SENTADA"
        and actual in ["DE PIE", "INCORPORADO"]
    ):
        estado["contador_levantamientos"] += 1
        estado["levantamiento_en_proceso"] = False
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "COMPLETO"
        estado["tiempo_levantamiento"] = time.time()

        registrar_evento(
            nombre,
            TIPO_LEVANTAMIENTO_COMPLETO,
            imagen,
        )
        print(f"[{nombre}] LEVANTAMIENTO COMPLETO. Total: {estado['contador_levantamientos']}")

        
# ============================================================
# PROCESAR UNA IMAGEN CON CLASIFICACIÓN YOLO (train-3)
# ============================================================

transmisor_livekit = None


def procesar_camara(nombre, modelo):
    estado = estados[nombre]

    ahora = time.time()

    if ahora - estado["ultimo_procesamiento"] < 1 / FPS_YOLO:
        return

    estado["ultimo_procesamiento"] = ahora

    # Copiar el fotograma y liberar el bloqueo antes de YOLO.
    with estado["frame_lock"]:
        if estado["frame"] is None:
            return

        frame = estado["frame"].copy()

    # Inferencia del modelo de clasificación YOLO fuera del bloqueo de captura.
    resultados = modelo(
        frame,
        verbose=False,
        imgsz=TAMANO_YOLO,
    )

    resultado = resultados[0]
    frame_mostrar = frame.copy()
    
    # Extracción de la clase predicha y su confianza (API de Clasificación de Ultralytics)
    if hasattr(resultado, 'probs') and resultado.probs is not None:
        top1_index = resultado.probs.top1
        postura_detectada = resultado.names[top1_index].upper()  # Ej: 'ACOSTADO', 'SENTADO', 'DE_PIE', 'SIN_PERSONA'
        confianza_pred = float(resultado.probs.top1conf) * 100
    else:
        postura_detectada = "DESCONOCIDO"
        confianza_pred = 0.0

    # Umbral opcional de seguridad (si la confianza es baja, se marca como desconocido)
    if confianza_pred < 45.0:
        postura_detectada = "DESCONOCIDO"

    # Actualizar la máquina de estados con la postura detectada
    actualizar_postura(
        nombre,
        postura_detectada,
        frame,
    )

    # Limpiar la alerta visual después de dos segundos.
    if (
        estado["levantamiento_detectado"]
        and time.time() - estado["tiempo_levantamiento"]
        >= DURACION_AVISO_LEVANTAMIENTO
    ):
        estado["levantamiento_detectado"] = False
        estado["tipo_alerta_levantamiento"] = ""

    postura_actual = estado["postura_actual"]
    contador = estado["contador_postura"]

    if estado["levantamiento_detectado"]:
        texto_levantamiento = estado["tipo_alerta_levantamiento"]
    elif estado["levantamiento_en_proceso"]:
        texto_levantamiento = "EN PROCESO"
    else:
        texto_levantamiento = "NO"

    color_alerta = (
        (0, 0, 255)
        if estado["levantamiento_detectado"]
        else (255, 255, 255)
    )

    cv2.putText(
        frame_mostrar,
        f"{nombre} | ID: {CAMARAS_CONFIG[nombre]['id_camara']}",
        (30, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame_mostrar,
        f"POSTURA: {postura_actual} ({confianza_pred:.1f}%)",
        (30, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame_mostrar,
        f"DETECTANDO: {postura_detectada} ({confianza_pred:.1f}%)",
        (30, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame_mostrar,
        f"CONFIRMACION: {contador}/{FRAMES_ESTABILIDAD}",
        (30, 135),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame_mostrar,
        f"LEVANTAMIENTO: {texto_levantamiento}",
        (30, 170),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color_alerta,
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame_mostrar,
        f"TOTAL: {estado['contador_levantamientos']}",
        (30, 205),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 165, 255),
        2,
        cv2.LINE_AA,
    )

    # Guardar el fotograma procesado para la transmisión.
    with estado["frame_lock"]:
        estado["frame_mostrar"] = frame_mostrar.copy()

    # Publicar el fotograma en LiveKit.
    if transmisor_livekit is not None:
        transmisor_livekit.publicar_frame(
            CAMARAS_CONFIG[nombre]["id_camara"],
            frame_mostrar,
        )

    # Mantener la ventana local de OpenCV.
    cv2.imshow(nombre, frame_mostrar)


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():
    hilos_captura = []
    hilo_backend = None

    try:
        print("=" * 60)
        print("GERIAPP - CLASIFICACIÓN DE POSTURAS YOLO CON DOS CÁMARAS")
        print("=" * 60)

        # Consultar las cámaras registradas en GerIApp.
        print("\nConsultando cámaras activas en GerIApp...")
        camaras_backend = obtener_camaras_activas()

        if not camaras_backend:
            raise RuntimeError(
                "GerIApp no tiene cámaras activas para procesar."
            )

        # Consultar los pacientes activos de GerIApp.
        pacientes_backend = obtener_pacientes_activos()


        # Agrupar los pacientes por habitación.
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

            # Algunos serializadores devuelven la habitación como objeto.
            if isinstance(id_habitacion, dict):
                id_habitacion = (
                    id_habitacion.get("id_habitacion")
                    or id_habitacion.get("id")
                )

            if id_habitacion is not None and id_paciente is not None:
                pacientes_por_habitacion.setdefault(
                    int(id_habitacion), []
                ).append(int(id_paciente))

        CAMARAS_CONFIG.clear()


        
        # Consultar dispositivos físicos y relacionarlos por identificador.
        dispositivos_dshow = obtener_dispositivos_dshow()

        print("\nDispositivos físicos encontrados por FFmpeg:")
        for dispositivo in dispositivos_dshow:
            print(f"- {dispositivo['nombre']}")

        CAMARAS_CONFIG.clear()

        camaras_validas = [
            camara for camara in camaras_backend
            if camara.get("estado") is True
            and camara.get("id_habitacion") is not None
        ]

        for camara_api in camaras_validas:
            id_camara = camara_api.get("id_camara")
            id_habitacion = camara_api.get("id_habitacion")
            identificador = camara_api.get("identificador_dispositivo")

            dispositivo = buscar_dispositivo_usb(
                identificador,
                dispositivos_dshow,
            )

            if not dispositivo:
                print(
                    f"[AVISO] Cámara GerIApp {id_camara}: "
                    "no se encontró su identificador USB en Windows."
                )
                continue

            # Comprobar que el dispositivo puede entregar imágenes.
            prueba = CapturaFFmpeg(dispositivo)
            disponible = False

            try:
                if prueba.isOpened():
                    correcto, frame = prueba.read()
                    disponible = correcto and frame is not None
            finally:
                prueba.release()

            if not disponible:
                print(
                    f"[AVISO] Cámara GerIApp {id_camara}: "
                    "no se pudo obtener una imagen."
                )
                continue

            nombre = (
                camara_api.get("nombre")
                or f"Cámara {id_camara}"
            )

            pacientes_habitacion = pacientes_por_habitacion.get(
                int(id_habitacion), []
            )

            id_paciente = (
                pacientes_habitacion[0]
                if len(pacientes_habitacion) == 1
                else None
            )

            CAMARAS_CONFIG[nombre] = {
                "dispositivo_dshow": dispositivo,
                "id_camara": id_camara,
                "id_habitacion": id_habitacion,
                "id_paciente": id_paciente,
            }

            print(
                f"[CONFIG] {nombre} | GerIApp ID: {id_camara} "
                f"| Habitación: {id_habitacion} "
                f"| Dispositivo USB: {identificador}"
            )

            if id_paciente is None:
                print(
                    f"[AVISO] {nombre}: hay "
                    f"{len(pacientes_habitacion)} pacientes activos "
                    "en la habitación. No se registrarán eventos "
                    "hasta resolver su asociación."
                )


        if not CAMARAS_CONFIG:
            raise RuntimeError(
                "No se encontraron cámaras externas configurables."
            )

        # Crear un estado independiente para cada cámara configurada.
        estados.clear()
        estados.update({
            nombre: crear_estado()
            for nombre in CAMARAS_CONFIG
        })

        # Iniciar el servidor local de video.
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
                f"Dispositivo USB: {config['dispositivo_dshow']}"
            )

        
        # Abrir cada cámara usando su dispositivo físico identificado.
        for nombre, config in CAMARAS_CONFIG.items():
            camara = CapturaFFmpeg(config["dispositivo_dshow"])

            if not camara.isOpened():
                camara.release()
                print(f"[{nombre}] No se pudo abrir el dispositivo.")
                continue

            estados[nombre]["camara"] = camara

            print(
                f"[{nombre}] Conectada por identificador USB | "
                f"GerIApp ID {config['id_camara']}"
            )

        activas = [
            nombre for nombre in CAMARAS_CONFIG
            if estados[nombre]["camara"] is not None
        ]

        if not activas:
            raise RuntimeError(
                "No se pudo abrir ninguna cámara."
            )

        print("\nCargando YOLO Pose...")
        modelo = YOLO(MODELO_YOLO)
        print("YOLO Pose cargado correctamente.")

        # Iniciar las transmisiones de video a LiveKit.
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

        # Captura independiente para cada cámara.
        for nombre in activas:
            hilo = threading.Thread(
                target=capturar_camara,
                args=(nombre,),
                daemon=True,
            )
            hilo.start()
            hilos_captura.append(hilo)

        # Hilo para Render y Cloudinary.
        hilo_backend = threading.Thread(
            target=enviar_eventos_backend,
            daemon=True,
        )
        hilo_backend.start()

        print("\nDetección iniciada. Presiona Q para salir.")

        while ejecutando.is_set():
            for nombre in activas:
                procesar_camara(nombre, modelo)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("Cierre solicitado desde el teclado.")

    except Exception as error:
        print("Error en el programa:", error)

    finally:
        ejecutando.clear()

        # Cerrar las transmisiones de LiveKit.
        if transmisor_livekit is not None:
            try:
                transmisor_livekit.cerrar()
            except Exception as error:
                print(f"[LiveKit] Error al cerrar: {error}")

        # Cerrar el servidor local de video.
        if "servidor_video" in locals():
            servidor_video.shutdown()
            servidor_video.server_close()

        if "hilo_video" in locals():
            hilo_video.join(timeout=3)

        for estado in estados.values():
            camara = estado["camara"]

            if camara is not None:
                camara.release()

        for hilo in hilos_captura:
            hilo.join(timeout=3)

        # El marcador se procesa después de los eventos encolados.
        if hilo_backend is not None:
            cola_eventos.put(None)
            hilo_backend.join(timeout=30)

            if hilo_backend.is_alive():
                print(
                    "Advertencia: el hilo del backend sigue activo."
                )

        cv2.destroyAllWindows()

        print("\nPrograma detenido.")

        for nombre, estado in estados.items():
            print(
                f"{nombre}: levantamientos detectados = "
                f"{estado['contador_levantamientos']}"
            )


if __name__ == "__main__":
    main()
