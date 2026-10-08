import subprocess
import cv2
import numpy as np
from ultralytics import YOLO

# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

MODELO_YOLO = "yolo11n.pt"

nombre_ventana = "GerIApp - Zona de cama + YOLO"

# ============================================================
# ZONA DE LA CAMA
# Coordenadas obtenidas de la cámara 1920x1080
# ============================================================

zona_cama = np.array([
    (1140, 309),
    (1303, 636),
    (514, 629),
    (475, 224)
], dtype=np.int32)

# ============================================================
# CARGAR YOLO
# ============================================================

print("==========================================")
print("🤖 GerIApp - YOLO + ZONA DE CAMA")
print("==========================================")

print("Cargando YOLO...")

modelo = YOLO(MODELO_YOLO)

print("✅ YOLO iniciado")

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
print("🛏️ Zona de cama configurada")
print("Presiona Q para cerrar.")
print("==========================================")

contador_frames = 0

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
        # BUSCAR JPEG
        # ====================================================

        while True:

            inicio = buffer.find(
                b"\xff\xd8"
            )

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

            # Extraer JPEG
            jpg = buffer[
                inicio:fin + 2
            ]

            buffer = buffer[
                fin + 2:
            ]

            # =================================================
            # CONVERTIR JPEG A OPENCV
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
            # DIBUJAR ZONA DE CAMA
            # =================================================

            overlay = frame.copy()

            cv2.fillPoly(
                overlay,
                [zona_cama],
                (0, 255, 0)
            )

            frame = cv2.addWeighted(
                overlay,
                0.12,
                frame,
                0.88,
                0
            )

            cv2.polylines(
                frame,
                [zona_cama],
                True,
                (0, 255, 0),
                4
            )

            # =================================================
            # YOLO
            # =================================================

            resultados = modelo(
                frame,
                verbose=False
            )

            # =================================================
            # PROCESAR PERSONAS
            # =================================================

            personas_detectadas = 0

            for resultado in resultados:

                if resultado.boxes is None:
                    continue

                for caja in resultado.boxes:

                    clase = int(
                        caja.cls[0]
                    )

                    confianza = float(
                        caja.conf[0]
                    )

                    # Clase 0 = persona
                    if clase != 0:
                        continue

                    # Ignorar detecciones con baja confianza
                    if confianza < 0.50:
                        continue

                    personas_detectadas += 1

                    # Coordenadas del cuadro
                    x1, y1, x2, y2 = map(
                        int,
                        caja.xyxy[0]
                    )

                    # =================================================
                    # PUNTO DE REFERENCIA DE LA PERSONA
                    # Usamos el centro inferior del cuerpo
                    # =================================================

                    punto_x = int(
                        (x1 + x2) / 2
                    )

                    punto_y = int(
                        y2
                    )

                    punto_persona = (
                        punto_x,
                        punto_y
                    )

                    # =================================================
                    # COMPROBAR SI ESTÁ EN LA CAMA
                    # =================================================

                    dentro_cama = cv2.pointPolygonTest(
                        zona_cama,
                        punto_persona,
                        False
                    )

                    if dentro_cama >= 0:

                        estado = "PERSONA EN CAMA"

                        color = (
                            0,
                            255,
                            0
                        )

                    else:

                        estado = "PERSONA FUERA DE CAMA"

                        color = (
                            0,
                            0,
                            255
                        )

                    # =================================================
                    # DIBUJAR CUADRO
                    # =================================================

                    cv2.rectangle(
                        frame,
                        (x1, y1),
                        (x2, y2),
                        color,
                        3
                    )

                    # =================================================
                    # DIBUJAR PUNTO DE REFERENCIA
                    # =================================================

                    cv2.circle(
                        frame,
                        punto_persona,
                        8,
                        color,
                        -1
                    )

                    # =================================================
                    # MOSTRAR ESTADO
                    # =================================================

                    texto = (
                        f"{estado} "
                        f"{confianza:.2f}"
                    )

                    cv2.putText(
                        frame,
                        texto,
                        (
                            x1,
                            max(
                                y1 - 10,
                                30
                            )
                        ),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        color,
                        2
                    )

            # =================================================
            # INFORMACIÓN GENERAL
            # =================================================

            cv2.putText(
                frame,
                f"Personas detectadas: {personas_detectadas}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2
            )

            cv2.putText(
                frame,
                "Zona verde = cama",
                (30, 85),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            # =================================================
            # MOSTRAR IMAGEN
            # =================================================

            cv2.imshow(
                nombre_ventana,
                frame
            )

            # =================================================
            # TECLADO
            # =================================================

            tecla = cv2.waitKey(1) & 0xFF

            if tecla == ord("q"):

                raise KeyboardInterrupt

except KeyboardInterrupt:

    print()
    print("🛑 Prueba detenida.")

finally:

    proceso.terminate()

    try:

        proceso.wait(
            timeout=2
        )

    except subprocess.TimeoutExpired:

        proceso.kill()

    cv2.destroyAllWindows()

    print("==========================================")
    print(
        "Frames recibidos:",
        contador_frames
    )
    print("✅ FFmpeg cerrado.")
    print("==========================================")