
import socket
import threading

HOST = "127.0.0.1"
PORT = 65433


def recibir_mensajes(cliente):
    try:
        with cliente.makefile("r", encoding="utf-8") as entrada:
            for linea in entrada:
                print(f"\n{linea.strip()}")
    except (OSError, ValueError):
        pass

    print("\nSe cerró la conexión con el servidor.")


def main():
    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        cliente.connect((HOST, PORT))
        print("Conectado al servidor de GeriApp.")

        hilo = threading.Thread(
            target=recibir_mensajes,
            args=(cliente,),
            daemon=True
        )
        hilo.start()

        print("Escribe un mensaje. Escribe salir para terminar.")

        while True:
            mensaje = input("> ")

            if mensaje.strip().lower() == "salir":
                break

            if not mensaje.strip():
                continue

            cliente.sendall((mensaje + "\n").encode("utf-8"))

    except (ConnectionRefusedError, ConnectionResetError):
        print("No se pudo conectar. Comprueba que el servidor esté activo.")
    except OSError as error:
        print(f"Error de conexión: {error}")
    finally:
        cliente.close()
        print("Cliente finalizado.")


if __name__ == "__main__":
    main()
