
import subprocess
import cv2
import numpy as np
import threading
import time
import queue
from ultralytics import YOLO
from conexion_backend import enviar_evento_geriapp

# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
CAMARA = "video=HK 2M CAM"
MODELO_YOLO = "yolo11n-pose.pt"

FPS_CAMARA = 30
FPS_YOLO = 10
TAMANO_YOLO = 640

# ============================================================
# CONFIGURACIÓN DE GERIAPP
# ============================================================

ID_CAMARA = 1
ID_HABITACION = 1
ID_PACIENTE = 24

# IDs del catálogo TiposEventoIa
TIPO_PACIENTE_SENTADO = 2
TIPO_LEVANTAMIENTO_COMPLETO = 4

# Confianza provisional para el registro del evento.
# No es la confianza real calculada por YOLO.
CONFIANZA_EVENTO = 95.00

# ============================================================
# CONFIGURACIÓN DE VALIDACIÓN DEL CUERPO
# ============================================================

CONFIANZA_MINIMA_PUNTO = 0.35

# ============================================================
# VARIABLES COMPARTIDAS
# ============================================================

frame_actual = None
frame_lock = threading.Lock()

resultado_actual = None
resultado_lock = threading.Lock()

ejecutando = True

# Cola de eventos que se enviarán al backend.
cola_eventos = queue.Queue()

# ============================================================
# VARIABLES DE POSTURA
# ============================================================

postura_actual = "DESCONOCIDO"
postura_candidata = "DESCONOCIDO"
ultima_postura_valida = "DESCONOCIDO"

contador_postura = 0
FRAMES_ESTABILIDAD = 5

# ============================================================
# VARIABLES DE LEVANTAMIENTO
# ============================================================

postura_anterior = "DESCONOCIDO"

levantamiento_en_proceso = False
levantamiento_detectado = False
tipo_alerta_levantamiento = ""

contador_levantamientos = 0
tiempo_levantamiento = 0

DURACION_AVISO_LEVANTAMIENTO = 2

# ============================================================
# CONTADOR DE PERSONAS AUSENTES
# ============================================================

contador_sin_persona = 0
MAX_SIN_PERSONA = 15

# ============================================================
# FUNCIÓN PARA CALCULAR ÁNGULO
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
# VALIDAR CUERPO
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
# DETECTAR POSTURA
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

    ancho = puntos_validos[:, 0].max() - puntos_validos[:, 0].min()
    alto = puntos_validos[:, 1].max() - puntos_validos[:, 1].min()

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
# HILO DE CAPTURA DE CÁMARA
# ============================================================

def capturar_camara():
    global frame_actual

    comando = [
        FFMPEG,
        "-f", "dshow",
        "-video_size", "1920x1080",
        "-framerate", str(FPS_CAMARA),
        "-vcodec", "mjpeg",
        "-i", CAMARA,
        "-c:v", "copy",
        "-f", "mjpeg",
        "pipe:1"
    ]

    proceso = None

    try:
        proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**8
        )

        buffer = b""

        while ejecutando:
            datos = proceso.stdout.read(4096)

            if not datos:
                break

            buffer += datos

            while True:
                inicio = buffer.find(b"\xff\xd8")

                if inicio == -1:
                    buffer = buffer[-1:]
                    break

                fin = buffer.find(b"\xff\xd9", inicio + 2)

                if fin == -1:
                    if inicio > 0:
                        buffer = buffer[inicio:]
                    break

                jpg = buffer[inicio:fin + 2]
                buffer = buffer[fin + 2:]

                imagen = cv2.imdecode(
                    np.frombuffer(jpg, dtype=np.uint8),
                    cv2.IMREAD_COLOR
                )

                if imagen is not None:
                    with frame_lock:
                        frame_actual = imagen

    except Exception as error:
        print("Error en la captura de cámara:", error)

    finally:
        if proceso is not None:
            proceso.terminate()

            try:
                proceso.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proceso.kill()

# ============================================================
# HILO DE ENVÍO DE EVENTOS A GERIAPP
# ============================================================

def enviar_eventos_backend():
    # Este hilo sigue activo hasta recibir la señal de cierre.
    # Si quedan eventos en la cola, los procesa antes de terminar.

    while True:
        evento = cola_eventos.get()

        try:
            # None significa que debemos cerrar el hilo.
            if evento is None:
                return

            print(
                f"📤 Enviando evento tipo "
                f"{evento['id_tipo_evento']} a GerIApp..."
            )

            resultado = enviar_evento_geriapp(
                id_camara=evento["id_camara"],
                id_habitacion=evento["id_habitacion"],
                id_paciente=evento["id_paciente"],
                id_tipo_evento=evento["id_tipo_evento"],
                confianza=evento["confianza"]
            )

            if resultado:
                print("✅ GerIApp confirmó el registro del evento.")
            else:
                print(
                    "⚠️ No se confirmó el registro del evento. "
                    "Revisa el mensaje anterior."
                )

        except Exception as error:
            print("Error procesando evento de GerIApp:", error)

        finally:
            cola_eventos.task_done()

# ============================================================
# AGREGAR EVENTO A LA COLA
# ============================================================

def registrar_evento(tipo_evento):
    evento = {
        "id_camara": ID_CAMARA,
        "id_habitacion": ID_HABITACION,
        "id_paciente": ID_PACIENTE,
        "id_tipo_evento": tipo_evento,
        "confianza": CONFIANZA_EVENTO
    }

    # No hacemos solicitudes HTTP en el hilo de YOLO.
    cola_eventos.put(evento)

    print(
        f"📥 Evento tipo {tipo_evento} agregado a la cola."
    )

# ============================================================
# HILO DE YOLO
# ============================================================

def procesar_yolo():
    global resultado_actual
    global postura_actual
    global postura_candidata
    global contador_postura
    global postura_anterior
    global ultima_postura_valida
    global levantamiento_en_proceso
    global levantamiento_detectado
    global tipo_alerta_levantamiento
    global contador_levantamientos
    global contador_sin_persona
    global tiempo_levantamiento

    print("🤖 Cargando modelo YOLO Pose...")

    modelo = YOLO(MODELO_YOLO)

    print("✅ YOLO Pose iniciado.")

    ultimo_procesamiento = 0

    while ejecutando:
        ahora = time.time()
        intervalo = 1 / FPS_YOLO

        if ahora - ultimo_procesamiento < intervalo:
            time.sleep(0.001)
            continue

        ultimo_procesamiento = ahora

        # Tomar una copia del frame más reciente.
        with frame_lock:
            if frame_actual is None:
                time.sleep(0.01)
                continue

            frame = frame_actual.copy()

        resultados = modelo(
            frame,
            verbose=False,
            conf=0.5,
            imgsz=TAMANO_YOLO
        )

        resultado = resultados[0]
        frame_con_detecciones = resultado.plot()

        postura_detectada = "SIN PERSONA"

        if resultado.keypoints is not None and len(resultado.keypoints) > 0:
            puntos = resultado.keypoints.xy[0].cpu().numpy()

            if resultado.keypoints.conf is not None:
                confianzas = resultado.keypoints.conf[0].cpu().numpy()
            else:
                confianzas = None

            if (
                len(puntos) >= 17
                and confianzas is not None
                and len(confianzas) >= 17
            ):
                if cuerpo_valido(puntos, confianzas):
                    postura_detectada = detectar_postura(puntos)
                    contador_sin_persona = 0
                else:
                    postura_detectada = "DESCONOCIDO"
                    contador_sin_persona = 0
            else:
                postura_detectada = "DESCONOCIDO"
                contador_sin_persona = 0
        else:
            contador_sin_persona += 1

        # Restablecer el ciclo cuando la persona desaparece.
        if contador_sin_persona >= MAX_SIN_PERSONA:
            postura_candidata = "SIN PERSONA"
            contador_postura = 0
            postura_actual = "SIN PERSONA"
            postura_anterior = "SIN PERSONA"
            ultima_postura_valida = "SIN PERSONA"
            levantamiento_en_proceso = False
            levantamiento_detectado = False
            tipo_alerta_levantamiento = ""

        # No cambiar la última postura válida si el cuerpo no se ve bien.
        elif postura_detectada == "DESCONOCIDO":
            postura_actual = "DESCONOCIDO"
            postura_candidata = "DESCONOCIDO"
            contador_postura = 0

        else:
            if postura_detectada == postura_candidata:
                contador_postura += 1
            else:
                postura_candidata = postura_detectada
                contador_postura = 1

            # Confirmar la postura después de varios frames.
            if contador_postura >= FRAMES_ESTABILIDAD:
                if postura_detectada != ultima_postura_valida:
                    postura_anterior = ultima_postura_valida
                    ultima_postura_valida = postura_detectada
                    postura_actual = postura_detectada
                    contador_postura = 0

                    # ============================================
                    # PERSONA ACOSTADA
                    # ============================================

                    if postura_actual == "ACOSTADA":
                        levantamiento_en_proceso = False
                        print("🔵 Persona está ACOSTADA.")

                    # ============================================
                    # ACOSTADA → SENTADA
                    # Evento tipo 2: Paciente sentado
                    # ============================================

                    elif (
                        postura_anterior == "ACOSTADA"
                        and postura_actual == "SENTADA"
                    ):
                        levantamiento_en_proceso = True
                        levantamiento_detectado = True
                        tipo_alerta_levantamiento = "INICIO"
                        tiempo_levantamiento = time.time()

                        registrar_evento(TIPO_PACIENTE_SENTADO)

                        print()
                        print("⚠️ INICIO DE LEVANTAMIENTO")
                        print("   Secuencia: ACOSTADA → SENTADA")
                        print("   Esperando que pase a DE PIE...")
                        print()

                    # ============================================
                    # SENTADA → DE PIE
                    # Evento tipo 4: Levantamiento detectado
                    # ============================================

                    elif (
                        levantamiento_en_proceso
                        and postura_anterior == "SENTADA"
                        and postura_actual == "DE PIE"
                    ):
                        contador_levantamientos += 1
                        levantamiento_en_proceso = False
                        levantamiento_detectado = True
                        tipo_alerta_levantamiento = "COMPLETO"
                        tiempo_levantamiento = time.time()

                        registrar_evento(TIPO_LEVANTAMIENTO_COMPLETO)

                        print()
                        print("🚨 LEVANTAMIENTO DETECTADO")
                        print(f"   Levantamiento #{contador_levantamientos}")
                        print(
                            "   Secuencia completa: "
                            "ACOSTADA → SENTADA → DE PIE"
                        )
                        print()

                else:
                    postura_actual = postura_detectada

        # Quitar la alerta visual después de dos segundos.
        if (
            levantamiento_detectado
            and time.time() - tiempo_levantamiento
            >= DURACION_AVISO_LEVANTAMIENTO
        ):
            levantamiento_detectado = False
            tipo_alerta_levantamiento = ""

        # Mostrar postura actual.
        cv2.putText(
            frame_con_detecciones,
            f"POSTURA: {postura_actual}",
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.3,
            (0, 255, 0),
            3,
            cv2.LINE_AA
        )

        cv2.putText(
            frame_con_detecciones,
            f"DETECTANDO: {postura_detectada}",
            (30, 105),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            frame_con_detecciones,
            f"CONFIRMACION: {contador_postura}/{FRAMES_ESTABILIDAD}",
            (30, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        if levantamiento_detectado:
            texto_levantamiento = tipo_alerta_levantamiento
        elif levantamiento_en_proceso:
            texto_levantamiento = "EN PROCESO"
        else:
            texto_levantamiento = "NO"

        color_alerta = (
            (0, 0, 255)
            if levantamiento_detectado
            else (255, 255, 255)
        )

        cv2.putText(
            frame_con_detecciones,
            f"LEVANTAMIENTO: {texto_levantamiento}",
            (30, 175),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color_alerta,
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            frame_con_detecciones,
            f"TOTAL LEVANTAMIENTOS: {contador_levantamientos}",
            (30, 210),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 165, 255),
            2,
            cv2.LINE_AA
        )

        with resultado_lock:
            resultado_actual = (
                frame_con_detecciones,
                postura_actual,
                postura_detectada,
                contador_postura,
                levantamiento_detectado,
                contador_levantamientos
            )

# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():
    global ejecutando

    print("==========================================")
    print("🤖 GerIApp - YOLO POSE + JALTECH")
    print("==========================================")
    print("📷 Resolución: 1920x1080")
    print(f"🎥 Cámara configurada: {FPS_CAMARA} FPS")
    print(f"🤖 YOLO: {FPS_YOLO} FPS")
    print("⚠️ Evento inicial: ACOSTADA → SENTADA")
    print("🚨 Levantamiento: ACOSTADA → SENTADA → DE PIE")
    print("🌐 Backend: GerIApp en Render")
    print("Presiona Q para cerrar.")
    print("==========================================")

    hilo_camara = threading.Thread(
        target=capturar_camara,
        daemon=True
    )

    hilo_yolo = threading.Thread(
        target=procesar_yolo,
        daemon=True
    )

    # Este hilo consume la cola y envía los eventos al backend.
    hilo_backend = threading.Thread(
        target=enviar_eventos_backend,
        daemon=True
    )

    hilo_backend.start()
    hilo_camara.start()
    hilo_yolo.start()

    nombre_ventana = "GerIApp - JALTECH + YOLO POSE"

    cv2.namedWindow(nombre_ventana, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(nombre_ventana, 1280, 720)

    try:
        while True:
            with resultado_lock:
                if resultado_actual is None:
                    frame = None
                else:
                    frame = resultado_actual[0].copy()

            if frame is not None:
                cv2.imshow(nombre_ventana, frame)

            tecla = cv2.waitKey(1) & 0xFF

            if tecla == ord("q"):
                break

    except KeyboardInterrupt:
        print("Cierre solicitado desde el teclado.")

    finally:
        # Detener la captura y la inferencia.
        ejecutando = False

        hilo_camara.join(timeout=3)
        hilo_yolo.join(timeout=3)

        # El marcador None le indica al hilo backend que termine.
        # Los eventos encolados antes del marcador se procesan primero.
        cola_eventos.put(None)

        # Esperar un tiempo limitado para no bloquear el cierre
        # indefinidamente si el backend tarda en responder.
        hilo_backend.join(timeout=20)

        if hilo_backend.is_alive():
            print(
                "⚠️ El hilo del backend sigue trabajando. "
                "Revisa si la conexión está tardando."
            )

        cv2.destroyAllWindows()

        print()
        print("==========================================")
        print("🛑 Programa detenido.")
        print(f"Levantamientos detectados: {contador_levantamientos}")
        print("==========================================")

if __name__ == "__main__":
    main()