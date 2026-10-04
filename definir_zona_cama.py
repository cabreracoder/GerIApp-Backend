import subprocess
import cv2
import numpy as np

# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

nombre_ventana = "GerIApp - Definir zona de cama"

# ============================================================
# VARIABLES PARA LA ZONA
# ============================================================

puntos = []

frame_actual = None

# ============================================================
# FUNCIÓN PARA SELECCIONAR LOS PUNTOS
# ============================================================

def seleccionar_punto(evento, x, y, flags, parametro):

    global puntos

    if evento == cv2.EVENT_LBUTTONDOWN:

        # Solo permitimos 4 puntos
        if len(puntos) < 4:

            puntos.append((x, y))

            print(
                f"Punto {len(puntos)}: "
                f"x={x}, y={y}"
            )


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
# CREAR VENTANA
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

cv2.setMouseCallback(
    nombre_ventana,
    seleccionar_punto
)

print("==========================================")
print("🛏️ GER IAPP - ZONA DE LA CAMA")
print("==========================================")
print()
print("Haz clic en 4 esquinas de la cama.")
print()
print("Orden recomendado:")
print("1. Esquina superior izquierda")
print("2. Esquina superior derecha")
print("3. Esquina inferior derecha")
print("4. Esquina inferior izquierda")
print()
print("Presiona R para reiniciar los puntos.")
print("Presiona Q para salir.")
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

            # Extraer imagen JPEG
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

            frame_actual = frame.copy()

            # =================================================
            # DIBUJAR LOS PUNTOS
            # =================================================

            for numero, punto in enumerate(puntos):

                cv2.circle(
                    frame_actual,
                    punto,
                    8,
                    (0, 255, 0),
                    -1
                )

                cv2.putText(
                    frame_actual,
                    str(numero + 1),
                    (
                        punto[0] + 10,
                        punto[1] - 10
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )

            # =================================================
            # DIBUJAR LÍNEAS
            # =================================================

            if len(puntos) >= 2:

                for i in range(
                    len(puntos) - 1
                ):

                    cv2.line(
                        frame_actual,
                        puntos[i],
                        puntos[i + 1],
                        (0, 255, 0),
                        3
                    )

            # =================================================
            # CERRAR POLÍGONO
            # =================================================

            if len(puntos) == 4:

                cv2.line(
                    frame_actual,
                    puntos[3],
                    puntos[0],
                    (0, 255, 0),
                    3
                )

                # Oscurecer ligeramente el interior
                overlay = frame_actual.copy()

                poligono = np.array(
                    puntos,
                    dtype=np.int32
                )

                cv2.fillPoly(
                    overlay,
                    [poligono],
                    (0, 255, 0)
                )

                frame_actual = cv2.addWeighted(
                    overlay,
                    0.15,
                    frame_actual,
                    0.85,
                    0
                )

                # Dibujar nuevamente el borde
                cv2.polylines(
                    frame_actual,
                    [poligono],
                    True,
                    (0, 255, 0),
                    3
                )

                cv2.putText(
                    frame_actual,
                    "ZONA DE LA CAMA",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    3
                )

            # =================================================
            # MOSTRAR INFORMACIÓN
            # =================================================

            texto = (
                f"Puntos seleccionados: "
                f"{len(puntos)}/4"
            )

            cv2.putText(
                frame_actual,
                texto,
                (30, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2
            )

            # =================================================
            # MOSTRAR IMAGEN
            # =================================================

            cv2.imshow(
                nombre_ventana,
                frame_actual
            )

            # =================================================
            # TECLADO
            # =================================================

            tecla = cv2.waitKey(1) & 0xFF

            # Reiniciar puntos
            if tecla == ord("r"):

                puntos.clear()

                print()
                print("🔄 Puntos reiniciados.")

            # Salir
            if tecla == ord("q"):

                raise KeyboardInterrupt

except KeyboardInterrupt:

    print()
    print("🛑 Selección finalizada.")

finally:

    # ========================================================
    # MOSTRAR COORDENADAS
    # ========================================================

    print()
    print("==========================================")
    print("📍 COORDENADAS DE LA ZONA DE LA CAMA")
    print("==========================================")

    if len(puntos) == 4:

        for numero, punto in enumerate(puntos):

            print(
                f"Punto {numero + 1}: "
                f"x={punto[0]}, y={punto[1]}"
            )

        print()
        print("✅ Zona de cama definida.")

    else:

        print(
            f"⚠️ Solo se seleccionaron "
            f"{len(puntos)} puntos."
        )

    print("==========================================")

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

    cv2.destroyAllWindows()

    print("✅ FFmpeg cerrado.")