
import cloudinary
import cloudinary.uploader


def subir_imagen(imagen, carpeta="geriapp/imagenes"):
    """
    Sube una imagen recibida desde Django a Cloudinary.
    """
    resultado = cloudinary.uploader.upload(
        imagen,
        folder=carpeta
    )

    return resultado


# NUEVA FUNCIÓN: subida de documentos
def subir_documento(archivo, carpeta="geriapp/documentos"):
    """
    Sube documentos a Cloudinary.
    """
    resultado = cloudinary.uploader.upload(
        archivo,
        folder=carpeta,
        resource_type="raw"
    )

    return resultado


def eliminar_imagen(public_id):
    """
    Elimina de Cloudinary una imagen identificada por su public_id.
    """
    if not public_id:
        raise ValueError("El public_id de la imagen es obligatorio.")

    resultado = cloudinary.uploader.destroy(
        public_id,
        invalidate=True
    )

    if resultado.get("result") != "ok":
        raise RuntimeError(
            f"Cloudinary no confirmó la eliminación: "
            f"{resultado.get('result')}"
        )

    return resultado
