import subprocess
import re

def obtener_dispositivos_dshow():
    """Ejecuta FFmpeg para listar los dispositivos DirectShow disponibles en Windows con codificación segura."""
    dispositivos = []
    # Comando estándar de FFmpeg para listar dispositivos DShow
    comando = ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
    
    try:
        resultado = subprocess.run(
            comando,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="latin-1",  # Evita errores con caracteres especiales en Windows
            errors="ignore"
        )
        
        # FFmpeg arroja la lista de dispositivos en el canal de errores (stderr)
        lineas = resultado.stderr.split("\n")
        capturar = False
        
        for linea in lineas:
            if "DirectShow video devices" in linea:
                capturar = True
                continue
            if "DirectShow audio devices" in linea:
                capturar = False
            
            if capturar:
                # Busca el texto entre comillas dobles que corresponde al nombre del dispositivo
                match_nombre = re.search(r'\"([^\"]+)\"', linea)
                if match_nombre and "Alternative name" not in linea:
                    nombre = match_nombre.group(1)
                    if not any(d['nombre'] == nombre for d in dispositivos):
                        dispositivos.append({"nombre": nombre})
                    
    except Exception as e:
        print(f"Error al listar dispositivos con FFmpeg: {e}")
        
    return dispositivos

def main():
    print("=" * 60)
    print("DETECTOR DE CÁMARAS USB (DIRECTSHOW / FFMPEG)")
    print("=" * 60)
    
    dispositivos = obtener_dispositivos_dshow()
    
    if not dispositivos:
        print("\nNo se detectaron cámaras mediante FFmpeg o DirectShow.")
        print("Verifica que las cámaras estén conectadas y no estén siendo usadas por otra aplicación.")
        return
        
    print(f"\nSe encontraron {len(dispositivos)} dispositivo(s) de video:\n")
    for i, dev in enumerate(dispositivos, start=1):
        print(f"[{i}] Nombre exacto: {dev['nombre']}")
        
    print("\n" + "=" * 60)
    print("Copia estos nombres exactos para tu configuración en GerIApp.")
    print("=" * 60)

if __name__ == "__main__":
    main()