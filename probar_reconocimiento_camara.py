import os
import cv2
import time
import numpy as np

from dotenv import load_dotenv

# =====================================================
# CARGAR VARIABLES DE ENTORNO
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# =====================================================
# IMPORTAR RECONOCIMIENTO FACIAL Y GER IAPP
# =====================================================

from reconocimiento_facial.reconocedor import ReconocedorFacial

from conexion_backend import obtener_plantillas_faciales


# =====================================================
# CONFIGURACIÓN
# =====================================================

ID_CAMARA_GERIAPP = 1
INDICE_OPENCV = 1

FPS_RECONOCIMIENTO = 1


# =====================================================
# COMPARAR EMBEDDINGS
# =====================================================

def comparar_embeddings(embedding_capturado, embedding_registrado):

    embedding_capturado = np.asarray(
        embedding_capturado,
        dtype=np.float32
    )

    embedding_registrado = np.asarray(
        embedding_registrado,
        dtype=np.float32
    )

    if (
        embedding_capturado.shape != (128,)
        or embedding_registrado.shape != (128,)
    ):
        return -1.0

    similitud = float(
        np.dot(
            embedding_capturado,
            embedding_registrado
        )
    )

    return float(np.clip(similitud, -1.0, 1.0))


# =====================================================
# CARGAR PLANTILLAS FACIALES
# =====================================================

print("\nConsultando plantillas faciales de GerIApp...")

plantillas = obtener_plantillas_faciales(
    ID_CAMARA_GERIAPP
)

if not plantillas:

    raise RuntimeError(
        "La cámara no tiene plantillas faciales disponibles."
    )

print(
    f"Plantillas cargadas: {len(plantillas)}"
)


# =====================================================
# INICIALIZAR RECONOCEDOR
# =====================================================

print("\nInicializando YuNet y SFace...")

reconocedor = ReconocedorFacial()

print("Reconocedor facial inicializado correctamente.")


# =====================================================
# ABRIR CÁMARA
# =====================================================

print("\nAbriendo cámara OpenCV...")

camara = cv2.VideoCapture(
    INDICE_OPENCV,
    cv2.CAP_DSHOW
)

if not camara.isOpened():

    raise RuntimeError(
        "No fue posible abrir la cámara."
    )

camara.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


# =====================================================
# BUCLE DE RECONOCIMIENTO
# =====================================================

ultimo_procesamiento = 0

ultimo_mensaje = "Esperando rostro..."

try:

    while True:

        correcto, frame = camara.read()

        if not correcto:
            print("No se pudo capturar la imagen.")
            break

        ahora = time.time()

        if (
            ahora - ultimo_procesamiento
            >= 1 / FPS_RECONOCIMIENTO
        ):

            ultimo_procesamiento = ahora

            correcto_jpg, imagen_jpg = cv2.imencode(
                ".jpg",
                frame
            )

            if not correcto_jpg:
                continue

            resultados = reconocedor.procesar_imagen(
                imagen_jpg.tobytes()
            )

            if not resultados:

                ultimo_mensaje = "NO SE DETECTAN ROSTROS"

            else:

                mejores_coincidencias = []

                for rostro in resultados:

                    embedding = rostro["embedding"]

                    for plantilla in plantillas:

                        similitud = comparar_embeddings(
                            embedding,
                            plantilla["embedding"]
                        )

                        mejores_coincidencias.append({
                            "id_paciente": plantilla["id_paciente"],
                            "similitud": similitud
                        })

                if mejores_coincidencias:

                    mejor = max(
                        mejores_coincidencias,
                        key=lambda x: x["similitud"]
                    )

                    ultimo_mensaje = (
                        f"Paciente candidato: "
                        f"{mejor['id_paciente']} | "
                        f"Similitud: "
                        f"{mejor['similitud']:.4f}"
                    )

                else:

                    ultimo_mensaje = "SIN COMPARACIONES"

        # Mostrar resultado de prueba.
        cv2.putText(
            frame,
            ultimo_mensaje,
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2
        )

        cv2.imshow(
            "PRUEBA RECONOCIMIENTO FACIAL",
            frame
        )

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:

    camara.release()

    cv2.destroyAllWindows()

    print("\nPrueba finalizada.")