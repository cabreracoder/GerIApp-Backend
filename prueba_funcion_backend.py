
from conexion_backend import enviar_evento_geriapp

# ============================================================
# PRUEBA DE LA FUNCIÓN REUTILIZABLE
# ============================================================

resultado = enviar_evento_geriapp(
    id_camara=1,
    id_habitacion=1,
    id_paciente=24,
    id_tipo_evento=4,
    confianza=95.00
)

# Mostrar el resultado final.
print("Resultado de la función:", resultado)