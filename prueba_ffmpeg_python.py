import subprocess
import cv2
import numpy as np
import threading
import time
from ultralytics import YOLO


# ============================================================
# CONFIGURACIÓN
# ============================================================

FFMPEG = r"C:\Users\josec\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

CAMARA = "video=HK 2M CAM"

MODELO_YOLO = "yolo11n-pose.pt"

FPS_CAMARA = 30

# YOLO procesa 10 FPS para mantener buena velocidad.
FPS_YOLO = 10

TAMANO_YOLO = 640


# ============================================================
# CONFIGURACIÓN DE VALIDACIÓN DEL CUERPO
# ============================================================

CONFIANZA_MINIMA_PUNTO = 0.35


# ============================================================
# VARIABLES DE CAPTURA
# ============================================================

frame_actual = None

frame_lock = threading.Lock()

ejecutando = True


# ============================================================
# VARIABLES DE RESULTADO YOLO
# ============================================================

resultado_actual = None

resultado_lock = threading.Lock()


# ============================================================
# VARIABLES DE POSTURA
# ============================================================

postura_actual = "DESCONOCIDO"

postura_candidata = "DESCONOCIDO"

ultima_postura_valida = "DESCONOCIDO"

contador_postura = 0

FRAMES_ESTABILIDAD = 5


# ============================================================
# VARIABLES DE LEVANTAMIENTO
# ============================================================

# Última postura válida utilizada para las transiciones.
postura_anterior = "DESCONOCIDO"


# Indica que la persona ya inició el levantamiento.
#
# Se activa cuando ocurre:
#
# ACOSTADA → SENTADA
#
# y permanece activa hasta:
#
# SENTADA → DE PIE
#
levantamiento_en_proceso = False


# Indica que existe una alerta visual activa.
levantamiento_detectado = False


# Tipo de alerta que se está mostrando.
#
# Puede ser:
#
# "INICIO"
# "COMPLETO"
# ""
#
tipo_alerta_levantamiento = ""


# Total de levantamientos completos.
contador_levantamientos = 0


# Momento en que se generó la última alerta.
tiempo_levantamiento = 0


# Duración de cada alerta visual.
DURACION_AVISO_LEVANTAMIENTO = 2


# ============================================================
# CONTADOR DE PERSONAS AUSENTES
# ============================================================

contador_sin_persona = 0

MAX_SIN_PERSONA = 15


# ============================================================
# FUNCIÓN PARA CALCULAR ÁNGULO
# ============================================================

def calcular_angulo(a, b, c):

    a = np.array(a, dtype=np.float32)

    b = np.array(b, dtype=np.float32)

    c = np.array(c, dtype=np.float32)

    ba = a - b

    bc = c - b

    producto = np.dot(ba, bc)

    magnitud = (
        np.linalg.norm(ba) *
        np.linalg.norm(bc)
    )

    if magnitud == 0:

        return 0

    coseno = producto / magnitud

    coseno = np.clip(
        coseno,
        -1.0,
        1.0
    )

    angulo = np.degrees(
        np.arccos(coseno)
    )

    return angulo


# ============================================================
# VALIDAR CUERPO COMPLETO
# ============================================================

def cuerpo_valido(keypoints, confianzas):

    # ========================================================
    # PUNTOS IMPORTANTES
    #
    # 5  = hombro izquierdo
    # 6  = hombro derecho
    # 11 = cadera izquierda
    # 12 = cadera derecha
    # 13 = rodilla izquierda
    # 14 = rodilla derecha
    # 15 = tobillo izquierdo
    # 16 = tobillo derecho
    # ========================================================

    puntos_importantes = [
        5,
        6,
        11,
        12,
        13,
        14,
        15,
        16
    ]


    # ========================================================
    # COMPROBAR CONFIANZAS
    # ========================================================

    if confianzas is None:

        return False


    if len(confianzas) < 17:

        return False


    # ========================================================
    # CONTAR PUNTOS VISIBLES
    # ========================================================

    puntos_visibles = 0


    for indice in puntos_importantes:

        if confianzas[indice] >= CONFIANZA_MINIMA_PUNTO:

            puntos_visibles += 1


    # ========================================================
    # EXIGIMOS MÍNIMO 6 DE 8 PUNTOS
    # ========================================================

    if puntos_visibles < 6:

        return False


    # ========================================================
    # COMPROBAR PARTES PRINCIPALES
    # ========================================================

    hombro_izq = (
        confianzas[5]
        >=
        CONFIANZA_MINIMA_PUNTO
    )

    hombro_der = (
        confianzas[6]
        >=
        CONFIANZA_MINIMA_PUNTO
    )


    cadera_izq = (
        confianzas[11]
        >=
        CONFIANZA_MINIMA_PUNTO
    )

    cadera_der = (
        confianzas[12]
        >=
        CONFIANZA_MINIMA_PUNTO
    )


    rodilla_izq = (
        confianzas[13]
        >=
        CONFIANZA_MINIMA_PUNTO
    )

    rodilla_der = (
        confianzas[14]
        >=
        CONFIANZA_MINIMA_PUNTO
    )


    tobillo_izq = (
        confianzas[15]
        >=
        CONFIANZA_MINIMA_PUNTO
    )

    tobillo_der = (
        confianzas[16]
        >=
        CONFIANZA_MINIMA_PUNTO
    )


    # ========================================================
    # HOMBROS
    # ========================================================

    hombros_validos = (
        hombro_izq
        or
        hombro_der
    )


    # ========================================================
    # CADERAS
    # ========================================================

    caderas_validas = (
        cadera_izq
        or
        cadera_der
    )


    # ========================================================
    # PIERNA IZQUIERDA COMPLETA
    # ========================================================

    pierna_izquierda = (
        cadera_izq
        and
        rodilla_izq
        and
        tobillo_izq
    )


    # ========================================================
    # PIERNA DERECHA COMPLETA
    # ========================================================

    pierna_derecha = (
        cadera_der
        and
        rodilla_der
        and
        tobillo_der
    )


    # ========================================================
    # AL MENOS UNA PIERNA COMPLETA
    # ========================================================

    piernas_validas = (
        pierna_izquierda
        or
        pierna_derecha
    )


    # ========================================================
    # VALIDACIÓN FINAL
    # ========================================================

    if (
        hombros_validos
        and
        caderas_validas
        and
        piernas_validas
    ):

        return True

    return False


# ============================================================
# FUNCIÓN PARA DETECTAR POSTURA
# ============================================================

def detectar_postura(puntos):

    # ========================================================
    # PUNTOS YOLO POSE
    # ========================================================

    hombro_izq = puntos[5]

    hombro_der = puntos[6]

    cadera_izq = puntos[11]

    cadera_der = puntos[12]

    rodilla_izq = puntos[13]

    rodilla_der = puntos[14]

    tobillo_izq = puntos[15]

    tobillo_der = puntos[16]


    # ========================================================
    # CENTRO DE HOMBROS
    # ========================================================

    hombros = (
        (hombro_izq[0] + hombro_der[0]) / 2,
        (hombro_izq[1] + hombro_der[1]) / 2
    )


    # ========================================================
    # CENTRO DE CADERAS
    # ========================================================

    caderas = (
        (cadera_izq[0] + cadera_der[0]) / 2,
        (cadera_izq[1] + cadera_der[1]) / 2
    )


    # ========================================================
    # DIMENSIONES DEL CUERPO
    # ========================================================

    puntos_validos = np.array(puntos)

    ancho = (
        puntos_validos[:, 0].max()
        -
        puntos_validos[:, 0].min()
    )

    alto = (
        puntos_validos[:, 1].max()
        -
        puntos_validos[:, 1].min()
    )


    if alto == 0:

        return "DESCONOCIDO"


    proporcion = ancho / alto


    # ========================================================
    # ÁNGULO RODILLA IZQUIERDA
    # ========================================================

    angulo_rodilla_izq = calcular_angulo(
        cadera_izq,
        rodilla_izq,
        tobillo_izq
    )


    # ========================================================
    # ÁNGULO RODILLA DERECHA
    # ========================================================

    angulo_rodilla_der = calcular_angulo(
        cadera_der,
        rodilla_der,
        tobillo_der
    )


    # ========================================================
    # PROMEDIO DE LAS RODILLAS
    # ========================================================

    angulo_rodillas = (
        angulo_rodilla_izq
        +
        angulo_rodilla_der
    ) / 2


    # ========================================================
    # ORIENTACIÓN DEL TRONCO
    # ========================================================

    dx = caderas[0] - hombros[0]

    dy = caderas[1] - hombros[1]


    angulo_tronco = abs(
        np.degrees(
            np.arctan2(
                dx,
                dy
            )
        )
    )


    # ========================================================
    # ORIENTACIÓN DE LAS PIERNAS
    # ========================================================

    dx_pierna_izq = (
        tobillo_izq[0]
        -
        cadera_izq[0]
    )

    dy_pierna_izq = (
        tobillo_izq[1]
        -
        cadera_izq[1]
    )


    dx_pierna_der = (
        tobillo_der[0]
        -
        cadera_der[0]
    )

    dy_pierna_der = (
        tobillo_der[1]
        -
        cadera_der[1]
    )


    # ========================================================
    # ÁNGULO DE ORIENTACIÓN DE CADA PIERNA
    # ========================================================

    angulo_pierna_izq = abs(
        np.degrees(
            np.arctan2(
                dx_pierna_izq,
                dy_pierna_izq
            )
        )
    )


    angulo_pierna_der = abs(
        np.degrees(
            np.arctan2(
                dx_pierna_der,
                dy_pierna_der
            )
        )
    )


    # ========================================================
    # PROMEDIO DE ORIENTACIÓN DE LAS PIERNAS
    # ========================================================

    angulo_piernas = (
        angulo_pierna_izq
        +
        angulo_pierna_der
    ) / 2


    # ========================================================
    # ACOSTADA
    # ========================================================

    if proporcion > 1.30:

        return "ACOSTADA"


    # ========================================================
    # SENTADA CON PIERNAS DOBLADAS
    # ========================================================

    if angulo_rodillas < 145:

        return "SENTADA"


    # ========================================================
    # SENTADA CON PIERNAS ESTIRADAS
    # ========================================================

    if (
        angulo_rodillas >= 145
        and
        angulo_piernas > 45
    ):

        return "SENTADA"


    # ========================================================
    # DE PIE
    # ========================================================

    if (
        angulo_rodillas >= 145
        and
        angulo_tronco < 35
        and
        angulo_piernas <= 45
    ):

        return "DE PIE"


    # ========================================================
    # DESCONOCIDO
    # ========================================================

    return "DESCONOCIDO"


# ============================================================
# HILO DE CAPTURA DE CÁMARA
# ============================================================

def capturar_camara():

    global frame_actual
    global ejecutando


    comando = [

        FFMPEG,

        "-f",
        "dshow",

        "-video_size",
        "1920x1080",

        "-framerate",
        "30",

        "-vcodec",
        "mjpeg",

        "-i",
        CAMARA,

        "-c:v",
        "copy",

        "-f",
        "mjpeg",

        "pipe:1"
    ]


    proceso = subprocess.Popen(

        comando,

        stdout=subprocess.PIPE,

        stderr=subprocess.DEVNULL,

        bufsize=10**8
    )


    buffer = b""


    while ejecutando:

        datos = proceso.stdout.read(4096)


        if not datos:

            break


        buffer += datos


        while True:

            inicio = buffer.find(
                b"\xff\xd8"
            )


            if inicio == -1:

                break


            fin = buffer.find(
                b"\xff\xd9",
                inicio + 2
            )


            if fin == -1:

                break


            jpg = buffer[
                inicio:
                fin + 2
            ]


            buffer = buffer[
                fin + 2:
            ]


            imagen = cv2.imdecode(

                np.frombuffer(
                    jpg,
                    dtype=np.uint8
                ),

                cv2.IMREAD_COLOR
            )


            if imagen is not None:

                # =================================================
                # GUARDAR SOLO EL ÚLTIMO FRAME
                # =================================================

                with frame_lock:

                    frame_actual = imagen


    proceso.terminate()


# ============================================================
# HILO DE YOLO
# ============================================================

def procesar_yolo():

    global resultado_actual
    global ejecutando

    global postura_actual
    global postura_candidata
    global contador_postura

    global postura_anterior
    global ultima_postura_valida

    global levantamiento_en_proceso
    global levantamiento_detectado
    global tipo_alerta_levantamiento

    global contador_levantamientos
    global contador_sin_persona

    global tiempo_levantamiento


    # ========================================================
    # CARGAR YOLO
    # ========================================================

    print(
        "=========================================="
    )

    print(
        "🤖 Cargando modelo YOLO Pose..."
    )

    modelo = YOLO(
        MODELO_YOLO
    )

    print(
        "✅ YOLO Pose iniciado"
    )

    print(
        "=========================================="
    )


    ultimo_procesamiento = 0


    while ejecutando:

        # ====================================================
        # CONTROLAR FPS DE YOLO
        # ====================================================

        ahora = time.time()

        intervalo = 1 / FPS_YOLO


        if (
            ahora
            -
            ultimo_procesamiento
            <
            intervalo
        ):

            time.sleep(0.001)

            continue


        ultimo_procesamiento = ahora


        # ====================================================
        # OBTENER SOLO EL ÚLTIMO FRAME
        # ====================================================

        with frame_lock:

            if frame_actual is None:

                continue

            frame = frame_actual.copy()


        # ====================================================
        # YOLO
        # ====================================================

        resultados = modelo(

            frame,

            verbose=False,

            conf=0.5,

            imgsz=TAMANO_YOLO
        )


        resultado = resultados[0]


        # ====================================================
        # DIBUJAR ESQUELETO
        # ====================================================

        frame_con_detecciones = resultado.plot()


        # ====================================================
        # POSTURA DETECTADA EN ESTE FRAME
        # ====================================================

        postura_detectada = "SIN PERSONA"


        # ====================================================
        # EXISTE DETECCIÓN DE PERSONA
        # ====================================================

        if (
            resultado.keypoints is not None
            and
            len(resultado.keypoints) > 0
        ):

            puntos = (
                resultado
                .keypoints
                .xy[0]
                .cpu()
                .numpy()
            )


            # =================================================
            # OBTENER CONFIANZAS
            # =================================================

            confianzas = (
                resultado
                .keypoints
                .conf[0]
                .cpu()
                .numpy()
            )


            # =================================================
            # COMPROBAR LOS 17 PUNTOS
            # =================================================

            if (
                len(puntos) >= 17
                and
                len(confianzas) >= 17
            ):

                # =================================================
                # VALIDAR CUERPO
                # =================================================

                if cuerpo_valido(
                    puntos,
                    confianzas
                ):

                    # =============================================
                    # CUERPO SUFICIENTEMENTE COMPLETO
                    # =============================================

                    postura_detectada = detectar_postura(
                        puntos
                    )

                    contador_sin_persona = 0


                else:

                    # =============================================
                    # PERSONA DETECTADA PERO CUERPO INCOMPLETO
                    # =============================================

                    postura_detectada = "DESCONOCIDO"

                    contador_sin_persona = 0


        else:

            contador_sin_persona += 1


        # ====================================================
        # SIN PERSONA
        # ====================================================

        if contador_sin_persona >= MAX_SIN_PERSONA:

            postura_candidata = "SIN PERSONA"

            contador_postura = 0

            postura_actual = "SIN PERSONA"

            postura_anterior = "SIN PERSONA"

            ultima_postura_valida = "SIN PERSONA"

            levantamiento_en_proceso = False

            levantamiento_detectado = False

            tipo_alerta_levantamiento = ""


        # ====================================================
        # CUERPO INCOMPLETO
        #
        # NO eliminamos la última postura válida.
        #
        # Esto permite continuar la secuencia después de
        # un frame temporalmente incompleto.
        # ====================================================

        elif postura_detectada == "DESCONOCIDO":

            postura_actual = "DESCONOCIDO"

            postura_candidata = "DESCONOCIDO"

            contador_postura = 0


        # ====================================================
        # POSTURA VÁLIDA
        # ====================================================

        else:

            # =================================================
            # MISMA POSTURA CANDIDATA
            # =================================================

            if postura_detectada == postura_candidata:

                contador_postura += 1


            else:

                # =================================================
                # NUEVA POSTURA CANDIDATA
                # =================================================

                postura_candidata = postura_detectada

                contador_postura = 1


            # =================================================
            # CONFIRMAR POSTURA
            # =================================================

            if contador_postura >= FRAMES_ESTABILIDAD:

                # =================================================
                # SOLO PROCESAR SI CAMBIÓ LA POSTURA VÁLIDA
                # =================================================

                if postura_detectada != ultima_postura_valida:

                    # =================================================
                    # GUARDAR POSTURA VÁLIDA ANTERIOR
                    # =================================================

                    postura_anterior = ultima_postura_valida


                    # =================================================
                    # ACTUALIZAR ÚLTIMA POSTURA VÁLIDA
                    # =================================================

                    ultima_postura_valida = postura_detectada


                    # =================================================
                    # ACTUALIZAR POSTURA MOSTRADA
                    # =================================================

                    postura_actual = postura_detectada

                    contador_postura = 0


                    # =================================================
                    # ACOSTADA
                    #
                    # Si vuelve a acostarse, el ciclo anterior
                    # termina y queda preparado uno nuevo.
                    # =================================================

                    if postura_actual == "ACOSTADA":

                        levantamiento_en_proceso = False

                        print(
                            "🔵 Persona está ACOSTADA"
                        )


                    # =================================================
                    # ACOSTADA → SENTADA
                    #
                    # PRIMERA ALERTA
                    #
                    # Aquí NO sumamos todavía el levantamiento.
                    #
                    # Solamente indicamos que la persona comenzó
                    # a levantarse.
                    # =================================================

                    elif (
                        postura_anterior == "ACOSTADA"
                        and
                        postura_actual == "SENTADA"
                    ):

                        levantamiento_en_proceso = True

                        levantamiento_detectado = True

                        tipo_alerta_levantamiento = "INICIO"

                        tiempo_levantamiento = time.time()


                        print()

                        print(
                            "⚠️ INICIO DE LEVANTAMIENTO"
                        )

                        print(
                            "   Secuencia: "
                            "ACOSTADA → SENTADA"
                        )

                        print(
                            "   Esperando que pase a DE PIE..."
                        )

                        print()


                    # =================================================
                    # SENTADA → DE PIE
                    #
                    # SEGUNDA ALERTA
                    #
                    # Aquí sí completamos el levantamiento.
                    # =================================================

                    elif (
                        levantamiento_en_proceso
                        and
                        postura_anterior == "SENTADA"
                        and
                        postura_actual == "DE PIE"
                    ):

                        # =============================================
                        # REGISTRAR LEVANTAMIENTO COMPLETO
                        # =============================================

                        contador_levantamientos += 1

                        levantamiento_en_proceso = False

                        levantamiento_detectado = True

                        tipo_alerta_levantamiento = "COMPLETO"

                        tiempo_levantamiento = time.time()


                        print()

                        print(
                            "🚨 LEVANTAMIENTO DETECTADO"
                        )

                        print(
                            f"   Levantamiento "
                            f"#{contador_levantamientos}"
                        )

                        print(
                            "   Secuencia completa: "
                            "ACOSTADA → SENTADA → DE PIE"
                        )

                        print()


                else:

                    # =================================================
                    # LA POSTURA SIGUE SIENDO LA MISMA
                    # =================================================

                    postura_actual = postura_detectada


        # ====================================================
        # AVISO TEMPORAL
        #
        # La alerta visual dura 2 segundos.
        #
        # IMPORTANTE:
        #
        # El contador NO depende de este tiempo.
        # El contador ya fue actualizado cuando correspondía.
        # ====================================================

        if (
            levantamiento_detectado
            and
            (
                time.time()
                -
                tiempo_levantamiento
            )
            >=
            DURACION_AVISO_LEVANTAMIENTO
        ):

            levantamiento_detectado = False

            tipo_alerta_levantamiento = ""


        # ====================================================
        # MOSTRAR POSTURA
        # ====================================================

        cv2.putText(

            frame_con_detecciones,

            f"POSTURA: {postura_actual}",

            (30, 60),

            cv2.FONT_HERSHEY_SIMPLEX,

            1.3,

            (0, 255, 0),

            3,

            cv2.LINE_AA
        )


        # ====================================================
        # MOSTRAR DETECCIÓN ACTUAL
        # ====================================================

        cv2.putText(

            frame_con_detecciones,

            f"DETECTANDO: {postura_detectada}",

            (30, 105),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.8,

            (255, 255, 0),

            2,

            cv2.LINE_AA
        )


        # ====================================================
        # MOSTRAR ESTABILIZACIÓN
        # ====================================================

        cv2.putText(

            frame_con_detecciones,

            f"CONFIRMACION: "
            f"{contador_postura}/"
            f"{FRAMES_ESTABILIDAD}",

            (30, 140),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.7,

            (255, 255, 255),

            2,

            cv2.LINE_AA
        )


        # ====================================================
        # MOSTRAR ESTADO DEL LEVANTAMIENTO
        # ====================================================

        if levantamiento_detectado:

            if tipo_alerta_levantamiento == "INICIO":

                texto_levantamiento = "INICIO"

            elif tipo_alerta_levantamiento == "COMPLETO":

                texto_levantamiento = "COMPLETO"

            else:

                texto_levantamiento = "SI"

        else:

            if levantamiento_en_proceso:

                texto_levantamiento = "EN PROCESO"

            else:

                texto_levantamiento = "NO"


        cv2.putText(

            frame_con_detecciones,

            f"LEVANTAMIENTO: "
            f"{texto_levantamiento}",

            (30, 175),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.7,

            (0, 0, 255)

            if levantamiento_detectado

            else

            (255, 255, 255),

            2,

            cv2.LINE_AA
        )


        # ====================================================
        # MOSTRAR TOTAL
        # ====================================================

        cv2.putText(

            frame_con_detecciones,

            f"TOTAL LEVANTAMIENTOS: "
            f"{contador_levantamientos}",

            (30, 210),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.7,

            (0, 165, 255),

            2,

            cv2.LINE_AA
        )


        # ====================================================
        # GUARDAR RESULTADO
        # ====================================================

        with resultado_lock:

            resultado_actual = (

                frame_con_detecciones,

                postura_actual,

                postura_detectada,

                contador_postura,

                levantamiento_detectado,

                contador_levantamientos

            )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    global ejecutando


    print(
        "=========================================="
    )

    print(
        "🤖 GerIApp - YOLO POSE + JALTECH"
    )

    print(
        "=========================================="
    )

    print(
        "📷 Resolución: 1920x1080"
    )

    print(
        "🎥 Cámara: 30 FPS"
    )

    print(
        "🤖 YOLO: 10 FPS"
    )

    print(
        "⚠️ Alerta inicial: ACOSTADA → SENTADA"
    )

    print(
        "🚨 Levantamiento: ACOSTADA → SENTADA → DE PIE"
    )

    print(
        "Presiona Q para cerrar."
    )

    print(
        "=========================================="
    )


    # ========================================================
    # HILO DE CÁMARA
    # ========================================================

    hilo_camara = threading.Thread(

        target=capturar_camara,

        daemon=True

    )


    # ========================================================
    # HILO DE YOLO
    # ========================================================

    hilo_yolo = threading.Thread(

        target=procesar_yolo,

        daemon=True

    )


    hilo_camara.start()

    hilo_yolo.start()


    # ========================================================
    # VENTANA
    # ========================================================

    nombre_ventana = (
        "GerIApp - JALTECH + YOLO POSE"
    )


    cv2.namedWindow(

        nombre_ventana,

        cv2.WINDOW_NORMAL

    )


    cv2.resizeWindow(

        nombre_ventana,

        1280,

        720

    )


    try:

        while True:

            # =================================================
            # OBTENER ÚLTIMO RESULTADO YOLO
            # =================================================

            with resultado_lock:

                if resultado_actual is None:

                    time.sleep(0.01)

                    continue

                frame = resultado_actual[0].copy()


            # =================================================
            # MOSTRAR
            # =================================================

            cv2.imshow(

                nombre_ventana,

                frame

            )


            # =================================================
            # TECLA
            # =================================================

            tecla = cv2.waitKey(1) & 0xFF


            if tecla == ord("q"):

                break


    finally:

        ejecutando = False


        # ====================================================
        # ESPERAR HILOS
        # ====================================================

        hilo_camara.join(
            timeout=2
        )

        hilo_yolo.join(
            timeout=2
        )


        cv2.destroyAllWindows()


        print()

        print(
            "=========================================="
        )

        print(
            "🛑 Cámara detenida."
        )

        print(
            f"Levantamientos detectados: "
            f"{contador_levantamientos}"
        )

        print(
            "=========================================="
        )


# ============================================================
# INICIAR
# ============================================================

if __name__ == "__main__":

    main()

