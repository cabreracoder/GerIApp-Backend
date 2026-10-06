import subprocess
import cv2
import numpy as np
from ultralytics import YOLO

# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

MODELO_YOLO = "yolo11n-pose.pt"

# ============================================================
# INICIAR MODELO YOLO POSE
# ============================================================

print("==========================================")
print("🤖 GerIApp - YOLO POSE + JALTECH")
print("==========================================")

print("Cargando modelo YOLO Pose...")

modelo = YOLO(MODELO_YOLO)

print("✅ YOLO Pose iniciado")

# ============================================================
# CONFIGURAR FFMPEG
# ============================================================

comando = [
    FFMPEG,
    "-f", "dshow",
    "-video_size", "1920x1080",
    "-framerate", "30",
    "-vcodec", "mjpeg",
    "-i", "video=HK 2M CAM",
    "-c:v", "copy",
    "-f", "mjpeg",
    "pipe:1"
]

# ============================================================
# INICIAR FFMPEG
# ============================================================

proceso = subprocess.Popen(
    comando,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    bufsize=0
)

buffer = b""

# ============================================================
# CONFIGURAR VENTANA
# ============================================================

nombre_ventana = "GerIApp - JALTECH + YOLO POSE"

cv2.namedWindow(
    nombre_ventana,
    cv2.WINDOW_NORMAL
)

cv2.resizeWindow(
    nombre_ventana,
    1280,
    720
)

print("==========================================")
print("📷 Resolución: 1920x1080")
print("🎥 FPS: 30")
print("🤖 YOLO Pose activo")
print("Presiona Q para cerrar.")
print("==========================================")

contador_frames = 0

# ============================================================
# ESTABILIZACIÓN DE POSTURA
# ============================================================

# Postura que GerIApp considera actualmente confirmada
postura_actual = "DESCONOCIDO"

# Nueva postura que estamos comprobando
postura_candidata = "DESCONOCIDO"

# Cantidad de frames consecutivos de la postura candidata
contador_postura = 0

# La nueva postura debe mantenerse durante esta cantidad
# de frames antes de ser aceptada.
FRAMES_ESTABILIDAD = 15

# ============================================================
# SECUENCIA DE LEVANTAMIENTO
# ============================================================

# Guarda la última postura confirmada
postura_anterior = "DESCONOCIDO"

# Indica si la persona pasó de acostada a sentada
levantamiento_en_proceso = False

# Indica que se detectó el último levantamiento
levantamiento_detectado = False

# Contador total de levantamientos
contador_levantamientos = 0

# ============================================================
# FUNCIÓN PARA CALCULAR ÁNGULO
# ============================================================

def calcular_angulo(a, b, c):
    """
    Calcula el ángulo formado por tres puntos:

    a -> b -> c

    Se utiliza para analizar las rodillas.
    """

    a = np.array(a)
    b = np.array(b)
    c = np.array(c)

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
    """
    Detecta tres posturas básicas:

    ACOSTADA
    SENTADA
    DE PIE
    """

    # ========================================================
    # PUNTOS COCO YOLO POSE
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
    # CENTRO DE LOS HOMBROS
    # ========================================================

    hombros = (
        (hombro_izq[0] + hombro_der[0]) / 2,
        (hombro_izq[1] + hombro_der[1]) / 2
    )

    # ========================================================
    # CENTRO DE LAS CADERAS
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
        - puntos_validos[:, 0].min()
    )

    alto = (
        puntos_validos[:, 1].max()
        - puntos_validos[:, 1].min()
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
    # PROMEDIO DE LAS RODILLAS
    # ========================================================

    angulo_rodillas = (
        angulo_rodilla_izq
        + angulo_rodilla_der
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
    # PERSONA ACOSTADA
    # ========================================================

    if proporcion > 1.30:
        return "ACOSTADA"

    # ========================================================
    # PERSONA SENTADA
    # ========================================================

    if angulo_rodillas < 145:
        return "SENTADA"

    # ========================================================
    # PERSONA DE PIE
    # ========================================================

    if (
        angulo_rodillas >= 145
        and angulo_tronco < 35
    ):
        return "DE PIE"

    # ========================================================
    # CASO NO CLARO
    # ========================================================

    return "DESCONOCIDO"


# ============================================================
# PROCESAMIENTO
# ============================================================

try:

    while True:

        # ====================================================
        # LEER DATOS DE FFMPEG
        # ====================================================

        datos = proceso.stdout.read(65536)

        if not datos:
            print("❌ No se recibieron datos.")
            break

        buffer += datos

        # ====================================================
        # BUSCAR IMÁGENES JPEG
        # ====================================================

        while True:

            inicio = buffer.find(b"\xff\xd8")

            if inicio == -1:
                buffer = buffer[-1:]
                break

            fin = buffer.find(
                b"\xff\xd9",
                inicio + 2
            )

            if fin == -1:
                buffer = buffer[inicio:]
                break

            jpg = buffer[
                inicio:fin + 2
            ]

            buffer = buffer[
                fin + 2:
            ]

            # =================================================
            # CONVERTIR JPEG A IMAGEN
            # =================================================

            frame = cv2.imdecode(
                np.frombuffer(
                    jpg,
                    dtype=np.uint8
                ),
                cv2.IMREAD_COLOR
            )

            if frame is None:
                continue

            contador_frames += 1

            # =================================================
            # YOLO POSE
            # =================================================

            resultados = modelo(
                frame,
                verbose=False,
                conf=0.5
            )

            resultado = resultados[0]

            # =================================================
            # DIBUJAR ESQUELETO
            # =================================================

            frame_con_detecciones = resultado.plot()

            # =================================================
            # POSTURA DETECTADA EN ESTE FRAME
            # =================================================

            postura_detectada = "SIN PERSONA"

            if resultado.keypoints is not None:

                if len(resultado.keypoints) > 0:

                    # Tomamos la primera persona detectada
                    puntos = (
                        resultado
                        .keypoints
                        .xy[0]
                        .cpu()
                        .numpy()
                    )

                    # Verificamos que existan los 17 puntos
                    if len(puntos) >= 17:

                        postura_detectada = detectar_postura(
                            puntos
                        )

            # =================================================
            # ESTABILIZAR POSTURA
            # =================================================

            if postura_detectada == "SIN PERSONA":

                # No hay persona.
                # Reiniciamos la comprobación.

                postura_candidata = "SIN PERSONA"

                contador_postura = 0

                postura_actual = "SIN PERSONA"

                # Reiniciamos la secuencia porque la persona
                # salió completamente de la cámara.

                postura_anterior = "SIN PERSONA"

                levantamiento_en_proceso = False

                levantamiento_detectado = False

            elif postura_detectada == "DESCONOCIDO":

                # No cambiamos la postura actual.
                #
                # Un frame dudoso NO debe provocar
                # un cambio de postura.

                contador_postura = 0

            else:

                # =================================================
                # LA POSTURA DETECTADA ES IGUAL A LA CANDIDATA
                # =================================================

                if postura_detectada == postura_candidata:

                    contador_postura += 1

                else:

                    # =================================================
                    # APARECIÓ UNA NUEVA POSTURA
                    # =================================================

                    postura_candidata = postura_detectada

                    contador_postura = 1

                # =================================================
                # CONFIRMAR NUEVA POSTURA
                # =================================================

                if contador_postura >= FRAMES_ESTABILIDAD:

                    # =================================================
                    # SOLO PROCESAR SI REALMENTE CAMBIÓ
                    # LA POSTURA CONFIRMADA
                    # =================================================

                    if postura_actual != postura_candidata:

                        # =================================================
                        # GUARDAR POSTURA ANTERIOR
                        # =================================================

                        postura_anterior = postura_actual

                        # =================================================
                        # CONFIRMAR NUEVA POSTURA
                        # =================================================

                        postura_actual = postura_candidata

                        contador_postura = 0

                        # =================================================
                        # ACOSTADA
                        # =================================================

                        if postura_actual == "ACOSTADA":

                            # La persona volvió a acostarse.
                            #
                            # Esto significa que el ciclo anterior
                            # terminó y estamos listos para detectar
                            # un nuevo levantamiento.

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
                            and postura_actual == "SENTADA"
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
                            and postura_anterior == "SENTADA"
                            and postura_actual == "DE PIE"
                        ):

                            # Levantamiento completo
                            levantamiento_detectado = True

                            # Terminamos este ciclo
                            levantamiento_en_proceso = False

                            # Aumentamos el contador
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

            # =================================================
            # MOSTRAR POSTURA CONFIRMADA
            # =================================================

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

            # =================================================
            # MOSTRAR POSTURA QUE YOLO ESTÁ INTENTANDO CONFIRMAR
            # =================================================

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

            # =================================================
            # MOSTRAR PROGRESO DE ESTABILIZACIÓN
            # =================================================

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

            # =================================================
            # MOSTRAR ESTADO DEL LEVANTAMIENTO
            # =================================================

            texto_levantamiento = (
                "SI"
                if levantamiento_detectado
                else "NO"
            )

            cv2.putText(
                frame_con_detecciones,
                f"LEVANTAMIENTO: {texto_levantamiento}",
                (30, 175),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255)
                if levantamiento_detectado
                else (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            # =================================================
            # MOSTRAR CONTADOR DE LEVANTAMIENTOS
            # =================================================

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

            # =================================================
            # MOSTRAR IMAGEN
            # =================================================

            cv2.imshow(
                nombre_ventana,
                frame_con_detecciones
            )

            # =================================================
            # TECLADO
            # =================================================

            tecla = cv2.waitKey(1) & 0xFF

            if tecla == ord("q"):

                raise KeyboardInterrupt


except KeyboardInterrupt:

    print("\n🛑 Cámara detenida.")


finally:

    # ========================================================
    # CERRAR FFMPEG
    # ========================================================

    proceso.terminate()

    try:

        proceso.wait(
            timeout=2
        )

    except subprocess.TimeoutExpired:

        proceso.kill()

    # ========================================================
    # CERRAR OPENCV
    # ========================================================

    cv2.destroyAllWindows()

    print("==========================================")

    print(
        "Frames recibidos:",
        contador_frames
    )

    print(
        "Levantamientos detectados:",
        contador_levantamientos
    )

    print("✅ FFmpeg cerrado.")

    print("==========================================")