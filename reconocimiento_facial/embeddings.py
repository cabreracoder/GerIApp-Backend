from pathlib import Path

import cv2
import numpy as np


RUTA_MODELO = (
    Path(__file__).resolve().parent
    / "modelos"
    / "face_recognition_sface_2021dec.onnx"
)


class GeneradorEmbeddings:

    def __init__(self):

        if not RUTA_MODELO.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo SFace: {RUTA_MODELO}"
            )

        self.reconocedor = cv2.FaceRecognizerSF.create(
            str(RUTA_MODELO),
            ""
        )

        print("Modelo SFace inicializado correctamente.")

    def generar_embedding(self, imagen, rostro):

        if imagen is None:
            raise ValueError("La imagen está vacía.")

        # Recuperar coordenadas del rostro
        x = rostro["x"]
        y = rostro["y"]
        ancho = rostro["ancho"]
        alto = rostro["alto"]

        puntos = np.asarray(
            rostro["puntos_faciales"],
            dtype=np.float32
        )

        confianza = float(rostro["confianza"])

        if puntos.size != 10:
            raise ValueError(
                "Se necesitan cinco puntos faciales."
            )

        # Reconstruir la detección de YuNet:
        # x, y, ancho, alto, 10 puntos faciales y confianza.
        deteccion = np.concatenate([
            np.array([x, y, ancho, alto], dtype=np.float32),
            puntos,
            np.array([confianza], dtype=np.float32)
        ]).reshape(1, 15)

        # Alinear y recortar el rostro
        rostro_alineado = self.reconocedor.alignCrop(
            imagen,
            deteccion
        )

        if rostro_alineado is None:
            raise ValueError("No fue posible alinear el rostro.")

        # Generar embedding
        embedding = self.reconocedor.feature(
            rostro_alineado
        )

        embedding = np.asarray(
            embedding,
            dtype=np.float32
        ).flatten()

        # Normalizar vector
        norma = np.linalg.norm(embedding)

        if norma == 0:
            raise ValueError("Embedding inválido.")

        embedding = embedding / norma

        return embedding

    @staticmethod
    def comparar_embeddings(embedding1, embedding2):

        embedding1 = np.asarray(
            embedding1,
            dtype=np.float32
        ).flatten()

        embedding2 = np.asarray(
            embedding2,
            dtype=np.float32
        ).flatten()

        if embedding1.shape != embedding2.shape:
            raise ValueError(
                "Los embeddings tienen dimensiones diferentes."
            )

        similitud = np.dot(embedding1, embedding2)

        return float(similitud)