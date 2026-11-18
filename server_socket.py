import socket

HOST = "127.0.0.1"
PORT = 65432

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen()

print(f"Servidor socket escuchando en {HOST}:{PORT}")

conn, addr = server.accept()

print(f"Cliente conectado desde: {addr}")

conn.sendall(b"Hola desde GeriApp")

conn.close()
server.close()