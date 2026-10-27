
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

HOST = "127.0.0.1"
PUERTO = 8765


def detectar_camaras_usb():
    """Obtiene las cámaras USB conectadas mediante PowerShell en Windows."""
    script = r"""
    Get-PnpDevice -PresentOnly |
    Where-Object {
        $_.Class -in @('Camera', 'Image') -and
        $_.InstanceId -like 'USB*' -and
        $_.Status -eq 'OK'
    } |
    Select-Object FriendlyName, InstanceId, Status |
    ConvertTo-Json -Compress
    """

    resultado = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
        encoding="utf-8",
        errors="replace",
    )

    salida = resultado.stdout.strip()
    if not salida:
        return []

    dispositivos = json.loads(salida)

    # PowerShell devuelve un objeto cuando encuentra uno y una lista cuando
    # encuentra varios; normalizamos ambos casos.
    if isinstance(dispositivos, dict):
        dispositivos = [dispositivos]

   
    
    return [
        {
            "nombre": dispositivo.get("FriendlyName"),
            "identificador_dispositivo": dispositivo.get("InstanceId"),
            "estado": dispositivo.get("Status"),
        }
        for dispositivo in dispositivos
        if dispositivo.get("FriendlyName")
        and dispositivo.get("InstanceId")
        and "USB2.0 HD UVC WebCam" not in dispositivo.get("FriendlyName")
    ]




class ManejadorCamaras(BaseHTTPRequestHandler):
    def responder_json(self, codigo, datos):
        contenido = json.dumps(datos, ensure_ascii=False).encode("utf-8")

        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(contenido)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(contenido)

    def do_OPTIONS(self):
        self.responder_json(200, {"mensaje": "OK"})

    def do_GET(self):
        ruta = urlparse(self.path).path

        if ruta != "/camaras":
            self.responder_json(404, {"error": "Ruta no encontrada"})
            return

        try:
            camaras = detectar_camaras_usb()
            self.responder_json(200, {"camaras": camaras})
        except Exception as error:
            print(f"Error detectando cámaras: {error}")
            self.responder_json(
                500,
                {"error": "No fue posible detectar las cámaras USB"},
            )

    def log_message(self, formato, *argumentos):
        print(formato % argumentos)


if __name__ == "__main__":
    servidor = HTTPServer((HOST, PUERTO), ManejadorCamaras)
    print(f"Servicio local disponible en http://{HOST}:{PUERTO}")
    print("Presiona Ctrl+C para detenerlo.")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServicio detenido.")
    finally:
        servidor.server_close()
