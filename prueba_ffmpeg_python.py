import subprocess
import cv2
import numpy as np
import threading
import time
from ultralytics import YOLO


# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

CAMARA = "video=HK 2M CAM"

MODELO_YOLO = "yolo11n-pose.pt"

FPS_CAMARA = 30

# YOLO no necesita procesar los 30 FPS.
# Procesamos solamente 10 FPS.
FPS_YOLO = 10

TAMANO_YOLO = 640


# ============================================================
# VARIABLES DE CAPTURA
# ============================================================

frame_actual = None

frame_lock = threading.Lock()

ejecutando = True


# ============================================================
# VARIABLES DE RESULTADO YOLO
# ============================================================

resultado_actual = None

resultado_lock = threading.Lock()


# ============================================================
# VARIABLES DE POSTURA
# ============================================================

postura_actual = "DESCONOCIDO"

postura_candidata = "DESCONOCIDO"

contador_postura = 0

FRAMES_ESTABILIDAD = 5


# ============================================================
# VARIABLES DE LEVANTAMIENTO
# ============================================================

postura_anterior = "DESCONOCIDO"

levantamiento_en_proceso = False

levantamiento_detectado = False

contador_levantamientos = 0


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

    magnitud = (
        np.linalg.norm(ba) *
        np.linalg.norm(bc)
    )

    if magnitud == 0:

        return 0

    coseno = producto / magnitud

    coseno = np.clip(
        coseno,
        -1.0,
        1.0
    )

    angulo = np.degrees(
        np.arccos(coseno)
    )

    return angulo


# ============================================================
# FUNCIÓN PARA DETECTAR POSTURA
# ============================================================

def detectar_postura(puntos):

    # ========================================================
    # PUNTOS YOLO POSE
    # ========================================================

    hombro_izq = puntos[5]
    hombro_der = puntos[6]

    cadera_izq = puntos[11]
    cadera_der = puntos[12]

    rodilla_izq = puntos[13]
    rodilla_der = puntos[14]

    tobillo_izq = puntos[15]
    tobillo_der = puntos[16]


    # ========================================================
    # CENTRO DE HOMBROS
    # ========================================================

    hombros = (
        (hombro_izq[0] + hombro_der[0]) / 2,
        (hombro_izq[1] + hombro_der[1]) / 2
    )


    # ========================================================
    # CENTRO DE CADERAS
    # ========================================================

    caderas = (
        (cadera_izq[0] + cadera_der[0]) / 2,
        (cadera_izq[1] + cadera_der[1]) / 2
    )


    # ========================================================
    # DIMENSIONES DEL CUERPO
    # ========================================================

    puntos_validos = np.array(puntos)

    ancho = (
        puntos_validos[:, 0].max()
        -
        puntos_validos[:, 0].min()
    )

    alto = (
        puntos_validos[:, 1].max()
        -
        puntos_validos[:, 1].min()
    )


    if alto == 0:

        return "DESCONOCIDO"


    proporcion = ancho / alto


    # ========================================================
    # ÁNGULO RODILLA IZQUIERDA
    # ========================================================

    angulo_rodilla_izq = calcular_angulo(
        cadera_izq,
        rodilla_izq,
        tobillo_izq
    )


    # ========================================================
    # ÁNGULO RODILLA DERECHA
    # ========================================================

    angulo_rodilla_der = calcular_angulo(
        cadera_der,
        rodilla_der,
        tobillo_der
    )


    # ========================================================
    # PROMEDIO
    # ========================================================

    angulo_rodillas = (
        angulo_rodilla_izq
        +
        angulo_rodilla_der
    ) / 2


    # ========================================================
    # ORIENTACIÓN DEL TRONCO
    # ========================================================

    dx = caderas[0] - hombros[0]

    dy = caderas[1] - hombros[1]

    angulo_tronco = abs(
        np.degrees(
            np.arctan2(dx, dy)
        )
    )


    # ========================================================
    # ACOSTADA
    # ========================================================

    if proporcion > 1.30:

        return "ACOSTADA"


    # ========================================================
    # SENTADA
    # ========================================================

    if angulo_rodillas < 145:

        return "SENTADA"


    # ========================================================
    # DE PIE
    # ========================================================

    if (
        angulo_rodillas >= 145
        and
        angulo_tronco < 35
    ):

        return "DE PIE"


    # ========================================================
    # DESCONOCIDO
    # ========================================================

    return "DESCONOCIDO"


# ============================================================
# HILO DE CAPTURA DE CÁMARA
# ============================================================

def capturar_camara():

    global frame_actual
    global ejecutando


    comando = [
        FFMPEG,

        "-f",
        "dshow",

        "-video_size",
        "1920x1080",

        "-framerate",
        "30",

        "-vcodec",
        "mjpeg",

        "-i",
        CAMARA,

        "-c:v",
        "copy",

        "-f",
        "mjpeg",

        "pipe:1"
    ]


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

            inicio = buffer.find(
                b"\xff\xd8"
            )


            if inicio == -1:

                break


            fin = buffer.find(
                b"\xff\xd9",
                inicio + 2
            )


            if fin == -1:

                break


            jpg = buffer[
                inicio:
                fin + 2
            ]


            buffer = buffer[
                fin + 2:
            ]


            imagen = cv2.imdecode(
                np.frombuffer(
                    jpg,
                    dtype=np.uint8
                ),
                cv2.IMREAD_COLOR
            )


            if imagen is not None:

                # =================================================
                # IMPORTANTE:
                #
                # No guardamos una cola de imágenes.
                #
                # Reemplazamos la anterior por la más reciente.
                #
                # Esto evita el retraso de varios segundos.
                # =================================================

                with frame_lock:

                    frame_actual = imagen


    proceso.terminate()


# ============================================================
# HILO DE YOLO
# ============================================================

def procesar_yolo():

    global resultado_actual

    global ejecutando

    global postura_actual

    global postura_candidata

    global contador_postura

    global postura_anterior

    global levantamiento_en_proceso

    global levantamiento_detectado

    global contador_levantamientos

    global contador_sin_persona


    # ========================================================
    # CARGAR YOLO
    # ========================================================

    print("==========================================")

    print("🤖 Cargando modelo YOLO Pose...")

    modelo = YOLO(MODELO_YOLO)

    print("✅ YOLO Pose iniciado")

    print("==========================================")


    ultimo_procesamiento = 0


    while ejecutando:

        # ====================================================
        # CONTROLAR FPS DE YOLO
        # ====================================================

        ahora = time.time()

        intervalo = 1 / FPS_YOLO


        if (
            ahora -
            ultimo_procesamiento
            <
            intervalo
        ):

            time.sleep(0.001)

            continue


        ultimo_procesamiento = ahora


        # ====================================================
        # OBTENER SOLO EL ÚLTIMO FRAME
        # ====================================================

        with frame_lock:

            if frame_actual is None:

                continue

            frame = frame_actual.copy()


        # ====================================================
        # YOLO
        # ====================================================

        resultados = modelo(
            frame,
            verbose=False,
            conf=0.5,
            imgsz=TAMANO_YOLO
        )


        resultado = resultados[0]


        # ====================================================
        # DIBUJAR ESQUELETO
        # ====================================================

        frame_con_detecciones = resultado.plot()


        # ====================================================
        # POSTURA
        # ====================================================

        postura_detectada = "SIN PERSONA"


        if (
            resultado.keypoints is not None
            and
            len(resultado.keypoints) > 0
        ):

            puntos = (
                resultado
                .keypoints
                .xy[0]
                .cpu()
                .numpy()
            )


            if len(puntos) >= 17:

                postura_detectada = detectar_postura(
                    puntos
                )


                contador_sin_persona = 0


        else:

            contador_sin_persona += 1


        # ====================================================
        # PERSONA NO DETECTADA
        # ====================================================

        if contador_sin_persona >= MAX_SIN_PERSONA:

            postura_candidata = "SIN PERSONA"

            contador_postura = 0

            postura_actual = "SIN PERSONA"

            postura_anterior = "SIN PERSONA"

            levantamiento_en_proceso = False

            levantamiento_detectado = False


        # ====================================================
        # POSTURA DESCONOCIDA
        # ====================================================

        elif postura_detectada == "DESCONOCIDO":

            # No cambiamos la postura confirmada.

            contador_postura = 0


        # ====================================================
        # POSTURA VÁLIDA
        # ====================================================

        else:

            # =================================================
            # MISMA POSTURA CANDIDATA
            # =================================================

            if postura_detectada == postura_candidata:

                contador_postura += 1


            else:

                # =================================================
                # NUEVA POSTURA
                # =================================================

                postura_candidata = postura_detectada

                contador_postura = 1


            # =================================================
            # CONFIRMAR POSTURA
            # =================================================

            if contador_postura >= FRAMES_ESTABILIDAD:

                if postura_actual != postura_candidata:

                    # =================================================
                    # GUARDAR POSTURA ANTERIOR
                    # =================================================

                    postura_anterior = postura_actual


                    # =================================================
                    # CONFIRMAR
                    # =================================================

                    postura_actual = postura_candidata

                    contador_postura = 0


                    # =================================================
                    # ACOSTADA
                    # =================================================

                    if postura_actual == "ACOSTADA":

                        levantamiento_en_proceso = False

                        levantamiento_detectado = False

                        print(
                            "🔵 Persona está ACOSTADA"
                        )


                    # =================================================
                    # ACOSTADA → SENTADA
                    # =================================================

                    elif (
                        postura_anterior == "ACOSTADA"
                        and
                        postura_actual == "SENTADA"
                    ):

                        levantamiento_en_proceso = True

                        levantamiento_detectado = False

                        print(
                            "🟡 Persona pasó de "
                            "ACOSTADA a SENTADA"
                        )


                    # =================================================
                    # SENTADA → DE PIE
                    # =================================================

                    elif (
                        levantamiento_en_proceso
                        and
                        postura_anterior == "SENTADA"
                        and
                        postura_actual == "DE PIE"
                    ):

                        levantamiento_detectado = True

                        levantamiento_en_proceso = False

                        contador_levantamientos += 1


                        print()

                        print(
                            "🚨 LEVANTAMIENTO DETECTADO"
                        )

                        print(
                            f"   Levantamiento #{contador_levantamientos}"
                        )

                        print(
                            "   Secuencia: "
                            "ACOSTADA → SENTADA → DE PIE"
                        )

                        print()


        # ====================================================
        # MOSTRAR POSTURA
        # ====================================================

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


        # ====================================================
        # MOSTRAR DETECCIÓN ACTUAL
        # ====================================================

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


        # ====================================================
        # MOSTRAR ESTABILIZACIÓN
        # ====================================================

        cv2.putText(
            frame_con_detecciones,
            f"CONFIRMACION: "
            f"{contador_postura}/{FRAMES_ESTABILIDAD}",
            (30, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )


        # ====================================================
        # MOSTRAR LEVANTAMIENTO
        # ====================================================

        texto_levantamiento = (
            "SI"
            if levantamiento_detectado
            else "NO"
        )


        cv2.putText(
            frame_con_detecciones,
            f"LEVANTAMIENTO: "
            f"{texto_levantamiento}",
            (30, 175),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255)
            if levantamiento_detectado
            else (255, 255, 255),
            2,
            cv2.LINE_AA
        )


        # ====================================================
        # TOTAL
        # ====================================================

        cv2.putText(
            frame_con_detecciones,
            f"TOTAL LEVANTAMIENTOS: "
            f"{contador_levantamientos}",
            (30, 210),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 165, 255),
            2,
            cv2.LINE_AA
        )


        # ====================================================
        # GUARDAR RESULTADO
        # ====================================================

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

    print(
        "🤖 GerIApp - YOLO POSE + JALTECH"
    )

    print("==========================================")

    print(
        "📷 Resolución: 1920x1080"
    )

    print(
        "🎥 Cámara: 30 FPS"
    )

    print(
        "🤖 YOLO: 10 FPS"
    )

    print(
        "Presiona Q para cerrar."
    )

    print("==========================================")


    # ========================================================
    # HILO DE CÁMARA
    # ========================================================

    hilo_camara = threading.Thread(
        target=capturar_camara,
        daemon=True
    )


    # ========================================================
    # HILO DE YOLO
    # ========================================================

    hilo_yolo = threading.Thread(
        target=procesar_yolo,
        daemon=True
    )


    hilo_camara.start()

    hilo_yolo.start()


    # ========================================================
    # VENTANA
    # ========================================================

    nombre_ventana = (
        "GerIApp - JALTECH + YOLO POSE"
    )


    cv2.namedWindow(
        nombre_ventana,
        cv2.WINDOW_NORMAL
    )


    cv2.resizeWindow(
        nombre_ventana,
        1280,
        720
    )


    try:

        while True:

            # =================================================
            # OBTENER ÚLTIMO RESULTADO YOLO
            # =================================================

            with resultado_lock:

                if resultado_actual is None:

                    time.sleep(0.01)

                    continue


                frame = resultado_actual[0].copy()


            # =================================================
            # MOSTRAR
            # =================================================

            cv2.imshow(
                nombre_ventana,
                frame
            )


            # =================================================
            # TECLA
            # =================================================

            tecla = cv2.waitKey(1) & 0xFF


            if tecla == ord("q"):

                break


    finally:

        ejecutando = False


        # ====================================================
        # ESPERAR HILOS
        # ====================================================

        hilo_camara.join(
            timeout=2
        )

        hilo_yolo.join(
            timeout=2
        )


        cv2.destroyAllWindows()


        print()
        print("==========================================")
        print("🛑 Cámara detenida.")
        print(
            f"Levantamientos detectados: "
            f"{contador_levantamientos}"
        )
        print("==========================================")


# ============================================================
# INICIAR
# ============================================================

if __name__ == "__main__":

    main()

