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