import subprocess
import cv2
import numpy as np
from ultralytics import YOLO

# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

MODELO_POSE = "yolo11n-pose.pt"

nombre_ventana = "GerIApp - YOLO Pose + JALTECH"

# ============================================================
# CARGAR YOLO POSE
# ============================================================

print("==========================================")
print("🤖 GerIApp - YOLO POSE + JALTECH")
print("==========================================")

print("Cargando YOLO Pose...")

modelo = YOLO(MODELO_POSE)

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
print("🦴 Detección de postura activa")
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
        # BUSCAR JPEG COMPLETO
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
            # YOLO POSE
            # =================================================

            resultados = modelo(
                frame,
                verbose=False
            )

            # =================================================
            # DIBUJAR POSTURA
            # =================================================

            frame_pose = resultados[0].plot()

            # =================================================
            # MOSTRAR INFORMACIÓN
            # =================================================

            cv2.putText(
                frame_pose,
                "YOLO POSE",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )

            # =================================================
            # MOSTRAR IMAGEN
            # =================================================

            cv2.imshow(
                nombre_ventana,
                frame_pose
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
    print("✅ FFmpeg cerrado.")
    print("==========================================")