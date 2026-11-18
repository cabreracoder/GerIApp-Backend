from pathlib import Path
from itertools import combinations, product

import numpy as np

from reconocimiento_facial.reconocedor import ReconocedorFacial


# ==========================================
# CONFIGURACIÓN
# ==========================================

RUTA_BASE = (
    Path(__file__).resolve().parent
    / "reconocimiento_facial"
    / "pruebas_umbral"
)

EXTENSIONES = {".jpg", ".jpeg", ".png"}


# ==========================================
# CARGAR EMBEDDINGS
# ==========================================

def cargar_embeddings():

    reconocedor = ReconocedorFacial()

    personas = {}

    carpetas = [
        carpeta
        for carpeta in RUTA_BASE.iterdir()
        if carpeta.is_dir()
    ]

    if len(carpetas) < 2:
        raise ValueError(
            "Se necesitan fotografías de al menos "
            "dos personas diferentes."
        )

    for carpeta in carpetas:

        imagenes = [
            archivo
            for archivo in carpeta.iterdir()
            if archivo.suffix.lower() in EXTENSIONES
        ]

        embeddings = []

        for imagen in imagenes:

            try:

                resultados = reconocedor.procesar_imagen(
                    imagen
                )

                if len(resultados) != 1:
                    print(
                        f"[OMITIDA] {imagen.name}: "
                        f"se detectaron {len(resultados)} rostros."
                    )
                    continue

                embedding = resultados[0]["embedding"]

                embeddings.append(embedding)

                print(
                    f"[OK] {carpeta.name}/{imagen.name}"
                )

            except Exception as error:

                print(
                    f"[ERROR] {imagen.name}: {error}"
                )

        if embeddings:
            personas[carpeta.name] = embeddings

    return personas


# ==========================================
# CALCULAR SIMILITUDES
# ==========================================

def calcular_similitudes(personas):

    generador = ReconocedorFacial().generador

    similitudes_misma_persona = []
    similitudes_personas_diferentes = []

    nombres = list(personas.keys())

    # Comparar fotografías de la misma persona
    for nombre in nombres:

        embeddings = personas[nombre]

        for emb1, emb2 in combinations(embeddings, 2):

            similitud = generador.comparar_embeddings(
                emb1,
                emb2
            )

            similitudes_misma_persona.append(similitud)

    # Comparar fotografías de personas diferentes
    for nombre1, nombre2 in combinations(nombres, 2):

        for emb1, emb2 in product(
            personas[nombre1],
            personas[nombre2]
        ):

            similitud = generador.comparar_embeddings(
                emb1,
                emb2
            )

            similitudes_personas_diferentes.append(
                similitud
            )

    return (
        similitudes_misma_persona,
        similitudes_personas_diferentes
    )


# ==========================================
# MOSTRAR RESULTADOS
# ==========================================

def mostrar_resultados(misma_persona, diferentes):

    if not misma_persona or not diferentes:
        raise ValueError(
            "No hay suficientes comparaciones para calibrar."
        )

    misma = np.array(misma_persona)
    distinta = np.array(diferentes)

    print("\n====================================")
    print("RESULTADOS DE CALIBRACIÓN FACIAL")
    print("====================================")

    print("\nMISMA PERSONA")

    print("Comparaciones:", len(misma))
    print("Mínimo:", round(float(np.min(misma)), 4))
    print("Máximo:", round(float(np.max(misma)), 4))
    print("Promedio:", round(float(np.mean(misma)), 4))
    print("Percentil 5:", round(float(np.percentile(misma, 5)), 4))

    print("\nPERSONAS DIFERENTES")

    print("Comparaciones:", len(distinta))
    print("Mínimo:", round(float(np.min(distinta)), 4))
    print("Máximo:", round(float(np.max(distinta)), 4))
    print("Promedio:", round(float(np.mean(distinta)), 4))
    print("Percentil 95:", round(float(np.percentile(distinta, 95)), 4))

    print("\n====================================")

    maximo_diferentes = float(np.max(distinta))
    minimo_misma = float(np.min(misma))

    if maximo_diferentes < minimo_misma:

        umbral = (
            maximo_diferentes + minimo_misma
        ) / 2

        print("Existe separación en estas pruebas.")

        print(
            "Umbral candidato:",
            round(umbral, 4)
        )

        print(
            "\nEste valor es solamente un candidato. "
            "Debe validarse con más fotografías antes "
            "de utilizarlo en producción."
        )

    else:

        print(
            "ATENCIÓN: hay solapamiento entre las "
            "comparaciones de la misma persona y "
            "personas diferentes."
        )

        print(
            "No es recomendable establecer todavía "
            "un umbral definitivo."
        )


# ==========================================
# EJECUCIÓN
# ==========================================

if __name__ == "__main__":

    personas = cargar_embeddings()

    misma, diferentes = calcular_similitudes(
        personas
    )

    mostrar_resultados(
        misma,
        diferentes
    )