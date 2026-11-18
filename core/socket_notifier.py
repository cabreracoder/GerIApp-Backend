
import json
import logging
import socket

HOST = "127.0.0.1"
PORT = 65433

logger = logging.getLogger(__name__)


def publicar_evento(evento):
    """
    Envía un evento de GeriApp al servidor TCP local.
    Si el servidor no está disponible, no interrumpe
    el guardado del registro en Django.
    """
    try:
        with socket.create_connection(
            (HOST, PORT),
            timeout=2
        ) as cliente:

            cliente.settimeout(2)

            # Leer el mensaje de bienvenida del servidor.
            cliente.recv(1024)

            # Enviar el evento en formato JSON.
            mensaje = json.dumps(
                evento,
                ensure_ascii=False
            ) + "\n"

            cliente.sendall(mensaje.encode("utf-8"))

            # Leer la respuesta para cerrar la conexión
            # sin dejar pendiente el mensaje recibido.
            try:
                cliente.recv(4096)
            except socket.timeout:
                pass

    except OSError as error:
        logger.warning(
            "No se pudo publicar el evento TCP: %s",
            error
        )
