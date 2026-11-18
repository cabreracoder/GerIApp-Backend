
import socket
import threading

HOST = "127.0.0.1"
PORT = 65433

clientes = set()
bloqueo = threading.Lock()


def enviar_a_todos(mensaje):
    datos = (mensaje + "\n").encode("utf-8")

    with bloqueo:
        destinatarios = list(clientes)

    for cliente in destinatarios:
        try:
            cliente.sendall(datos)
        except OSError:
            with bloqueo:
                clientes.discard(cliente)


def manejar_cliente(cliente, direccion):
    print(f"Cliente conectado: {direccion}")

    with bloqueo:
        clientes.add(cliente)

    try:
        cliente.sendall(
            "Conectado al servidor GeriApp\n".encode("utf-8")
        )

        with cliente.makefile("r", encoding="utf-8") as entrada:
            for linea in entrada:
                mensaje = linea.strip()

                if not mensaje:
                    continue

                print(f"Mensaje de {direccion}: {mensaje}")

                enviar_a_todos(
                    f"EVENTO: {mensaje}"
                )

    except (ConnectionResetError, OSError) as error:
        print(f"Error con {direccion}: {error}")

    finally:
        with bloqueo:
            clientes.discard(cliente)

        cliente.close()
        print(f"Cliente desconectado: {direccion}")


def main():
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    ) as servidor:

        servidor.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        servidor.bind((HOST, PORT))
        servidor.listen()

        print(f"Servidor escuchando en {HOST}:{PORT}")

        while True:
            cliente, direccion = servidor.accept()

            threading.Thread(
                target=manejar_cliente,
                args=(cliente, direccion),
                daemon=True
            ).start()


if __name__ == "__main__":
    main()
