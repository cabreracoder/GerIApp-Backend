from pathlib import Path

from reconocimiento_facial.detector_rostros import DetectorRostros
from reconocimiento_facial.embeddings import GeneradorEmbeddings


CARPETA_PRUEBAS = (
    Path(__file__).resolve().parent / "pruebas"
)

FOTOGRAFIAS = {
    "Persona A": "rostro_prueba.jpg",
    "Persona B": "rostro_misma_persona.jpg",
    "Persona C": "rostro_persona_diferente.jpg"
}


class ComparadorFacial:

    def __init__(self):
        self.detector = DetectorRostros()
        self.generador = GeneradorEmbeddings()

    def obtener_embedding(self, nombre, archivo):

        ruta = CARPETA_PRUEBAS / archivo

        if not ruta.exists():
            raise FileNotFoundError(
                f"No existe la fotografía: {ruta}"
            )

        import cv2

        imagen = cv2.imread(str(ruta))

        if imagen is None:
            raise ValueError(
                f"No se pudo leer la fotografía: {ruta}"
            )

        rostros = self.detector.detectar(imagen)

        print(f"\n{nombre}")
        print(f"Rostros detectados: {len(rostros)}")

        if len(rostros) != 1:
            raise ValueError(
                f"{nombre}: se esperaba exactamente un rostro "
                f"y se encontraron {len(rostros)}."
            )

        embedding = self.generador.generar_embedding(
            imagen,
            rostros[0]
        )

        print("Embedding generado correctamente.")
        print(
            "Confianza de detección:",
            round(rostros[0]["confianza"], 4)
        )

        return embedding

    def comparar(self, embedding1, embedding2):

        return self.generador.comparar_embeddings(
            embedding1,
            embedding2
        )

    def ejecutar(self):

        embeddings = {}

        print("\n================================")
        print(" EXTRACCIÓN DE ROSTROS")
        print("================================")

        for nombre, archivo in FOTOGRAFIAS.items():

            embeddings[nombre] = self.obtener_embedding(
                nombre,
                archivo
            )

        print("\n================================")
        print(" COMPARACIÓN FACIAL")
        print("================================")

        comparaciones = [
            ("Persona A", "Persona B"),
            ("Persona A", "Persona C"),
            ("Persona B", "Persona C")
        ]

        for persona1, persona2 in comparaciones:

            similitud = self.comparar(
                embeddings[persona1],
                embeddings[persona2]
            )

            print(
                f"\n{persona1} vs {persona2}: "
                f"{similitud:.4f}"
            )


if __name__ == "__main__":

    comparador = ComparadorFacial()
    comparador.ejecutar()