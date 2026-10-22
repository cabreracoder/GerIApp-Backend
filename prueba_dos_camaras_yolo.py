
import cv2
import numpy as np
import threading
import time
import queue
from ultralytics import YOLO

from conexion_backend import (
    enviar_evento_geriapp,
    subir_imagen_cloudinary,
    registrar_evidencia_geriapp
)
from conexion_backend import obtener_camaras_activas

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

MODELO_YOLO = "yolo11n-pose.pt"
FPS_YOLO = 10
TAMANO_YOLO = 640
CONFIANZA_MINIMA_PUNTO = 0.35
FRAMES_ESTABILIDAD = 5
MAX_SIN_PERSONA = 15
DURACION_AVISO_LEVANTAMIENTO = 2

# Cada cámara física está relacionada con su ID de GerIApp.
# Los índices de OpenCV ya fueron comprobados.
# ============================================================
# MAPEO LOCAL DE DISPOSITIVOS Y PACIENTES
# ============================================================

# Los índices de OpenCV fueron comprobados físicamente.
# Los pacientes corresponden a las asignaciones confirmadas.
MAPEO_LOCAL_CAMARAS = {
    1: {
        "indice_opencv": 1,
        "id_paciente": 1
    },
    2: {
        "indice_opencv": 2,
        "id_paciente": 3
    }
}

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

        "ultimo_procesamiento": 0
    }


# Se crean cuando se consultan las cámaras del backend.
estados = {}
# ============================================================
# FUNCIÓN ORIGINAL PARA CALCULAR ÁNGULOS
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
# FUNCIÓN ORIGINAL PARA VALIDAR EL CUERPO
# ============================================================

def cuerpo_valido(keypoints, confianzas):
    puntos_importantes = [5, 6, 11, 12, 13, 14, 15, 16]

    if confianzas is None or len(confianzas) < 17:
        return False

    puntos_visibles = sum(
        confianzas[i] >= CONFIANZA_MINIMA_PUNTO
        for i in puntos_importantes
    )

    if puntos_visibles < 6:
        return False

    hombro_izq = confianzas[5] >= CONFIANZA_MINIMA_PUNTO
    hombro_der = confianzas[6] >= CONFIANZA_MINIMA_PUNTO

    cadera_izq = confianzas[11] >= CONFIANZA_MINIMA_PUNTO
    cadera_der = confianzas[12] >= CONFIANZA_MINIMA_PUNTO

    rodilla_izq = confianzas[13] >= CONFIANZA_MINIMA_PUNTO
    rodilla_der = confianzas[14] >= CONFIANZA_MINIMA_PUNTO

    tobillo_izq = confianzas[15] >= CONFIANZA_MINIMA_PUNTO
    tobillo_der = confianzas[16] >= CONFIANZA_MINIMA_PUNTO

    hombros_validos = hombro_izq or hombro_der
    caderas_validas = cadera_izq or cadera_der

    pierna_izquierda = (
        cadera_izq and rodilla_izq and tobillo_izq
    )

    pierna_derecha = (
        cadera_der and rodilla_der and tobillo_der
    )

    piernas_validas = pierna_izquierda or pierna_derecha

    return hombros_validos and caderas_validas and piernas_validas


# ============================================================
# FUNCIÓN ORIGINAL PARA DETECTAR POSTURA
# ============================================================

def detectar_postura(puntos):
    hombro_izq = puntos[5]
    hombro_der = puntos[6]

    cadera_izq = puntos[11]
    cadera_der = puntos[12]

    rodilla_izq = puntos[13]
    rodilla_der = puntos[14]

    tobillo_izq = puntos[15]
    tobillo_der = puntos[16]

    hombros = (
        (hombro_izq[0] + hombro_der[0]) / 2,
        (hombro_izq[1] + hombro_der[1]) / 2
    )

    caderas = (
        (cadera_izq[0] + cadera_der[0]) / 2,
        (cadera_izq[1] + cadera_der[1]) / 2
    )

    puntos_validos = np.array(puntos)

    ancho = (
        puntos_validos[:, 0].max()
        - puntos_validos[:, 0].min()
    )

    alto = (
        puntos_validos[:, 1].max()
        - puntos_validos[:, 1].min()
    )

    if alto == 0:
        return "DESCONOCIDO"

    proporcion = ancho / alto

    angulo_rodilla_izq = calcular_angulo(
        cadera_izq, rodilla_izq, tobillo_izq
    )

    angulo_rodilla_der = calcular_angulo(
        cadera_der, rodilla_der, tobillo_der
    )

    angulo_rodillas = (
        angulo_rodilla_izq + angulo_rodilla_der
    ) / 2

    dx = caderas[0] - hombros[0]
    dy = caderas[1] - hombros[1]

    angulo_tronco = abs(
        np.degrees(np.arctan2(dx, dy))
    )

    dx_pierna_izq = tobillo_izq[0] - cadera_izq[0]
    dy_pierna_izq = tobillo_izq[1] - cadera_izq[1]

    dx_pierna_der = tobillo_der[0] - cadera_der[0]
    dy_pierna_der = tobillo_der[1] - cadera_der[1]

    angulo_pierna_izq = abs(
        np.degrees(np.arctan2(dx_pierna_izq, dy_pierna_izq))
    )

    angulo_pierna_der = abs(
        np.degrees(np.arctan2(dx_pierna_der, dy_pierna_der))
    )

    angulo_piernas = (
        angulo_pierna_izq + angulo_pierna_der
    ) / 2

    # ACOSTADA
    if angulo_tronco > 55 and angulo_piernas > 55:
        return "ACOSTADA"

    # SENTADA con rodillas dobladas
    if angulo_rodillas < 145:
        return "SENTADA"

    # SENTADA con piernas estiradas
    if angulo_rodillas >= 145 and angulo_piernas > 45:
        return "SENTADA"

    # Validaciones para DE PIE
    rodillas_extendidas = (
        angulo_rodilla_izq >= 145
        and angulo_rodilla_der >= 145
    )

    piernas_verticales = (
        angulo_pierna_izq <= 45
        and angulo_pierna_der <= 45
    )

    rodillas_debajo_caderas = (
        rodilla_izq[1] > caderas[1]
        and rodilla_der[1] > caderas[1]
    )

    tobillos_debajo_rodillas = (
        tobillo_izq[1] > rodilla_izq[1]
        and tobillo_der[1] > rodilla_der[1]
    )

    if (
        rodillas_extendidas
        and piernas_verticales
        and rodillas_debajo_caderas
        and tobillos_debajo_rodillas
        and angulo_tronco < 35
    ):
        return "DE PIE"

    return "DESCONOCIDO"


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

    evento = {
        "nombre_camara": nombre,
        "id_camara": config["id_camara"],
        "id_habitacion": config["id_habitacion"],
        "id_paciente": config["id_paciente"],
        "id_tipo_evento": tipo_evento,
        "confianza": CONFIANZA_EVENTO,
        "imagen": imagen.copy()
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

            print(
                    f"[DIAGNÓSTICO] Cámara: {nombre} | "
                    f"ID cámara: {evento['id_camara']} | "
                    f"ID habitación: {evento['id_habitacion']} | "
                    f"ID paciente: {evento['id_paciente']}"
                )

            resultado = enviar_evento_geriapp(
                id_camara=evento["id_camara"],
                id_habitacion=evento["id_habitacion"],
                id_paciente=evento["id_paciente"],
                id_tipo_evento=evento["id_tipo_evento"],
                confianza=evento["confianza"]
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
                [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            )

            if not correcto:
                print(f"[{nombre}] No se pudo codificar la imagen.")
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
                public_id=public_id
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

    # Conservar el comportamiento de la versión original.
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

    if actual == "ACOSTADA":
        estado["levantamiento_en_proceso"] = False
        print(f"[{nombre}] Persona ACOSTADA.")

    # ACOSTADA -> SENTADA
    elif anterior == "ACOSTADA" and actual == "SENTADA":
        estado["levantamiento_en_proceso"] = True
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "INICIO"
        estado["tiempo_levantamiento"] = time.time()

        registrar_evento(
            nombre,
            TIPO_PACIENTE_SENTADO,
            imagen
        )

        print(f"[{nombre}] INICIO DE LEVANTAMIENTO")
        print(f"[{nombre}] ACOSTADA -> SENTADA")

    # SENTADA -> DE PIE
    elif (
        estado["levantamiento_en_proceso"]
        and anterior == "SENTADA"
        and actual == "DE PIE"
    ):
        estado["contador_levantamientos"] += 1
        estado["levantamiento_en_proceso"] = False
        estado["levantamiento_detectado"] = True
        estado["tipo_alerta_levantamiento"] = "COMPLETO"
        estado["tiempo_levantamiento"] = time.time()

        registrar_evento(
            nombre,
            TIPO_LEVANTAMIENTO_COMPLETO,
            imagen
        )

        print(f"[{nombre}] LEVANTAMIENTO COMPLETO")
        print(
            f"[{nombre}] Total: "
            f"{estado['contador_levantamientos']}"
        )


# ============================================================
# PROCESAR UNA IMAGEN CON YOLO POSE
# ============================================================

def procesar_camara(nombre, modelo):
    estado = estados[nombre]

    ahora = time.time()
    if ahora - estado["ultimo_procesamiento"] < 1 / FPS_YOLO:
        return

    estado["ultimo_procesamiento"] = ahora

    with estado["frame_lock"]:
        if estado["frame"] is None:
            return
        frame = estado["frame"].copy()

    resultados = modelo(
        frame,
        verbose=False,
        conf=0.5,
        imgsz=TAMANO_YOLO
    )

    resultado = resultados[0]
    frame_mostrar = resultado.plot()
    postura_detectada = "SIN PERSONA"

    if (
        resultado.keypoints is not None
        and len(resultado.keypoints) > 0
    ):
        # Conservamos la selección de la primera persona,
        # igual que en el script original.
        puntos = resultado.keypoints.xy[0].cpu().numpy()

        if resultado.keypoints.conf is not None:
            confianzas = (
                resultado.keypoints.conf[0].cpu().numpy()
            )
        else:
            confianzas = None

        if (
            len(puntos) >= 17
            and confianzas is not None
            and len(confianzas) >= 17
            and cuerpo_valido(puntos, confianzas)
        ):
            postura_detectada = detectar_postura(puntos)
        else:
            postura_detectada = "DESCONOCIDO"

    actualizar_postura(
        nombre,
        postura_detectada,
        frame
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
        cv2.LINE_AA
    )

    cv2.putText(
        frame_mostrar,
        f"POSTURA: {postura_actual}",
        (30, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        frame_mostrar,
        f"DETECTANDO: {postura_detectada}",
        (30, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 0),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        frame_mostrar,
        f"CONFIRMACION: {contador}/{FRAMES_ESTABILIDAD}",
        (30, 135),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        frame_mostrar,
        f"LEVANTAMIENTO: {texto_levantamiento}",
        (30, 170),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color_alerta,
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        frame_mostrar,
        f"TOTAL: {estado['contador_levantamientos']}",
        (30, 205),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 165, 255),
        2,
        cv2.LINE_AA
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
        print("GERIAPP - YOLO POSE CON DOS CÁMARAS JALTECH")
        print("=" * 55)

                # Consultar las cámaras registradas en GerIApp.
        print("\nConsultando cámaras activas en GerIApp...")
        camaras_backend = obtener_camaras_activas()

        if not camaras_backend:
            raise RuntimeError(
                "GerIApp no tiene cámaras activas para procesar."
            )

        # Construir la configuración combinando los datos del
        # backend con el mapeo físico local ya comprobado.
        CAMARAS_CONFIG.clear()

        for camara_api in camaras_backend:
            id_camara = camara_api.get("id_camara")
            mapeo = MAPEO_LOCAL_CAMARAS.get(id_camara)

            if mapeo is None:
                print(
                    f"[AVISO] Cámara ID {id_camara} "
                    "sin mapeo local de dispositivo y paciente. "
                    "Se omitirá."
                )
                continue

            nombre = camara_api.get("nombre") or f"Cámara {id_camara}"
            id_habitacion = camara_api.get("id_habitacion")

            if id_habitacion is None:
                print(
                    f"[AVISO] {nombre} no tiene habitación asignada. "
                    "Se omitirá."
                )
                continue

            CAMARAS_CONFIG[nombre] = {
                "indice_opencv": mapeo["indice_opencv"],
                "id_camara": id_camara,
                "id_habitacion": id_habitacion,
                "id_paciente": mapeo["id_paciente"]
            }

        if not CAMARAS_CONFIG:
            raise RuntimeError(
                "No hay cámaras activas con un mapeo local válido."
            )

        # Crear un estado independiente para cada cámara configurada.
        estados.clear()
        estados.update({
            nombre: crear_estado()
            for nombre in CAMARAS_CONFIG
        })

        print("\nCámaras configuradas para YOLO:")
        for nombre, config in CAMARAS_CONFIG.items():
            print(
                f"- {nombre} | "
                f"GerIApp ID: {config['id_camara']} | "
                f"Habitación: {config['id_habitacion']} | "
                f"Paciente: {config['id_paciente']} | "
                f"OpenCV: {config['indice_opencv']}"
            )

        # Abrir las cámaras.
        for nombre, config in CAMARAS_CONFIG.items():
            camara = cv2.VideoCapture(
                config["indice_opencv"],
                cv2.CAP_DSHOW
            )

            if not camara.isOpened():
                camara.release()
                print(f"[{nombre}] No se pudo abrir.")
                continue

            camara.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            camara.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            estados[nombre]["camara"] = camara

            print(
                f"[{nombre}] Conectada | "
                f"OpenCV {config['indice_opencv']} | "
                f"GerIApp ID {config['id_camara']}"
            )

        activas = [
            nombre for nombre in CAMARAS_CONFIG
            if estados[nombre]["camara"] is not None
        ]

        if not activas:
            raise RuntimeError("No se pudo abrir ninguna cámara.")

        print("\nCargando YOLO Pose...")
        modelo = YOLO(MODELO_YOLO)
        print("YOLO Pose cargado correctamente.")

        # Captura independiente para cada cámara.
        for nombre in activas:
            hilo = threading.Thread(
                target=capturar_camara,
                args=(nombre,),
                daemon=True
            )
            hilo.start()
            hilos_captura.append(hilo)

        # Hilo para Render y Cloudinary.
        hilo_backend = threading.Thread(
            target=enviar_eventos_backend,
            daemon=True
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
