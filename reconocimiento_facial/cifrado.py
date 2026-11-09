import os
from cryptography.fernet import Fernet, InvalidToken


def obtener_cifrador():
    """
    Obtiene la clave de cifrado desde una variable de entorno.
    """
    clave = os.getenv("CLAVE_CIFRADO_FACIAL")

    if not clave:
        raise RuntimeError(
            "No se encontró la variable CLAVE_CIFRADO_FACIAL."
        )

    try:
        return Fernet(clave.encode("utf-8"))
    except Exception as error:
        raise RuntimeError(
            "La clave de cifrado facial no es válida."
        ) from error


def cifrar_embedding(embedding):
    """
    Cifra los bytes de un embedding facial.
    """
    if not isinstance(embedding, bytes):
        raise TypeError("El embedding debe estar en formato bytes.")

    cifrador = obtener_cifrador()
    return cifrador.encrypt(embedding)


def descifrar_embedding(embedding_cifrado):
    """
    Descifra un embedding facial.
    """
    cifrador = obtener_cifrador()

    try:
        return cifrador.decrypt(embedding_cifrado)
    except InvalidToken as error:
        raise ValueError(
            "No fue posible descifrar el embedding."
        ) from error