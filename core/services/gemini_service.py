import csv
import io
import json
import logging
import os
from pathlib import Path

from django.conf import settings
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader

logger = logging.getLogger(__name__)

MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MODELOS_GEMINI_FALLBACK = (
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
)

CAMPOS_RANGO = (
    ("sistolica_min", "sistolica_max"),
    ("diastolica_min", "diastolica_max"),
    ("fc_min", "fc_max"),
    ("fr_min", "fr_max"),
    ("temp_min", "temp_max"),
    ("sat_min", "sat_max"),
)


class RangosVitalesGeriatricosSchema(BaseModel):
    """Esquema estricto para los rangos personalizados devueltos por Gemini."""

    sistolica_min: float = Field(
        description="Presión arterial sistólica mínima segura en mmHg."
    )
    sistolica_max: float = Field(
        description="Presión arterial sistólica máxima segura en mmHg."
    )
    diastolica_min: float = Field(
        description="Presión arterial diastólica mínima segura en mmHg."
    )
    diastolica_max: float = Field(
        description="Presión arterial diastólica máxima segura en mmHg."
    )
    fc_min: float = Field(
        description="Frecuencia cardíaca mínima segura en lpm."
    )
    fc_max: float = Field(
        description="Frecuencia cardíaca máxima segura en lpm."
    )
    fr_min: float = Field(
        description="Frecuencia respiratoria mínima segura en rpm."
    )
    fr_max: float = Field(
        description="Frecuencia respiratoria máxima segura en rpm."
    )
    temp_min: float = Field(
        description="Temperatura corporal mínima segura en °C."
    )
    temp_max: float = Field(
        description="Temperatura corporal máxima segura en °C."
    )
    sat_min: float = Field(
        description="Saturación de oxígeno (SpO2) mínima segura en %."
    )
    sat_max: float = Field(
        description="Saturación de oxígeno (SpO2) máxima segura en %."
    )
    resumen_condicion: str = Field(
        description=(
            "Resumen clínico breve de las condiciones geriátricas del paciente "
            "y la justificación de los rangos personalizados definidos."
        )
    )


def _leer_paginas_pdf(fuente) -> str:
    """Lee y concatena el texto de todas las páginas de un stream PDF."""
    reader = PdfReader(fuente)
    paginas_texto = []
    for pagina in reader.pages:
        texto = (pagina.extract_text() or "").strip()
        if texto:
            paginas_texto.append(texto)

    texto_completo = "\n\n".join(paginas_texto).strip()
    if not texto_completo:
        raise ValueError(
            "El archivo PDF no contiene texto legible para analizar."
        )
    return texto_completo


def _extraer_texto_pdf(archivo_pdf) -> str:
    """Extrae el texto completo de un PDF (ruta, bytes o file-like)."""
    if archivo_pdf is None:
        raise ValueError("No se proporcionó ningún archivo PDF.")

    if isinstance(archivo_pdf, (str, Path)):
        with open(archivo_pdf, "rb") as fuente:
            return _leer_paginas_pdf(fuente)

    if isinstance(archivo_pdf, (bytes, bytearray)):
        return _leer_paginas_pdf(io.BytesIO(archivo_pdf))

    if hasattr(archivo_pdf, "seek"):
        archivo_pdf.seek(0)

    try:
        return _leer_paginas_pdf(archivo_pdf)
    finally:
        if hasattr(archivo_pdf, "seek"):
            # Restaurar puntero para permitir que Django guarde el archivo después
            try:
                archivo_pdf.seek(0)
            except (OSError, ValueError) as exc:
                logger.debug("No se pudo restaurar puntero del PDF: %s", exc)


def _cargar_ejemplos_few_shot() -> str:
    """Lee dataset_entrenamiento.csv desde BASE_DIR como ejemplos few-shot."""
    ruta_csv = Path(settings.BASE_DIR) / "dataset_entrenamiento.csv"

    if not ruta_csv.exists():
        logger.warning(
            "No se encontró dataset_entrenamiento.csv en %s",
            ruta_csv,
        )
        return ""

    ejemplos = []
    with open(ruta_csv, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for fila in reader:
            id_reg = (fila.get("id_registro") or "").strip()
            entrada = (fila.get("texto_entrada") or "").strip()
            salida = (fila.get("salida_esperada") or "").strip()
            if entrada and salida:
                ejemplos.append(
                    f"- [{id_reg}] Caso: {entrada}\n"
                    f"  Criterio clínico esperado: {salida}"
                )

    return "\n".join(ejemplos)


def _construir_prompt(texto_pdf: str, ejemplos_few_shot: str) -> str:
    """Construye el prompt clínico con reglas geriátricas y ejemplos few-shot."""
    bloque_ejemplos = ""
    if ejemplos_few_shot:
        bloque_ejemplos = (
            "### CRITERIOS DE REFERENCIA GERIÁTRICA (EJEMPLOS FEW-SHOT)\n"
            "Usa estos casos reales/clínicos como guía de criterio geriátrico para "
            "entender cómo las patologías base modifican las metas seguras (por ejemplo: "
            "EPOC requiere SatO2 88-92% y no hiperoxigenar; HTA sistólica aislada o ACV "
            "isquémico reciente tienen metas sistólicas particulares; insuficiencia cardíaca "
            "o enfermedad del nodo sinusal ajustan FC; aneurisma aórtico exige TA sistólica baja; "
            "en ancianos frágiles la hipotermia puede indicar infección severa):\n"
            f"{ejemplos_few_shot}\n\n"
        )

    return (
        "Eres un médico geriatra experto en monitoreo clínico de adultos mayores.\n"
        "Tu tarea es analizar el texto extraído de la historia clínica en PDF de un "
        "paciente geriátrico y determinar sus rangos normales PERSONALIZADOS de signos vitales "
        "en formato JSON estricto.\n\n"
        "Instrucciones obligatorias:\n"
        "1. Si la historia clínica especifica metas terapéuticas o rangos explícitos "
        "prescritos, respétalos estrictamente.\n"
        "2. Si no especifica rangos numéricos explícitos para algún signo, establece el rango "
        "seguro geriátrico personalizado acorde a la edad, patologías y antecedentes descritos "
        "en el documento (siguiendo los criterios de los ejemplos de referencia).\n"
        "3. Para signos no afectados por ninguna patología descrita, usa rangos fisiológicos "
        "normales seguros para un adulto mayor.\n"
        "4. Todos los valores numéricos (*_min y *_max) deben ser números válidos (no null) "
        "y cumplir estrictamente min <= max.\n"
        "5. Devuelve únicamente el JSON con las claves solicitadas.\n\n"
        f"{bloque_ejemplos}"
        "### HISTORIA CLÍNICA DEL PACIENTE (TEXTO EXTRAÍDO DEL PDF)\n"
        f"{texto_pdf}\n"
    )


def _normalizar_resultado(datos: dict) -> dict:
    """Valida con Pydantic y asegura que cada par min <= max."""
    validado = RangosVitalesGeriatricosSchema.model_validate(datos).model_dump()
    for campo_min, campo_max in CAMPOS_RANGO:
        if validado[campo_min] > validado[campo_max]:
            validado[campo_min], validado[campo_max] = (
                validado[campo_max],
                validado[campo_min],
            )
    validado["resumen_condicion"] = validado["resumen_condicion"].strip()
    return validado


def analizar_pdf_geriatrico(archivo_pdf) -> dict:
    """
    Extrae el texto de una historia clínica en PDF y utiliza Gemini 2.5 Flash
    con ejemplos few-shot de dataset_entrenamiento.csv para devolver los rangos
    normales personalizados de signos vitales en JSON.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY no está configurada en las variables de entorno."
        )

    texto_pdf = _extraer_texto_pdf(archivo_pdf)
    ejemplos_few_shot = _cargar_ejemplos_few_shot()
    prompt = _construir_prompt(texto_pdf, ejemplos_few_shot)

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=30000,
            retry_options=types.HttpRetryOptions(attempts=2),
        ),
    )
    modelos_a_probar = list(
        dict.fromkeys([MODELO_GEMINI, *MODELOS_GEMINI_FALLBACK])
    )
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=RangosVitalesGeriatricosSchema,
        temperature=0.1,
    )

    response = None
    ultimo_error = None
    for modelo in modelos_a_probar:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=config,
            )
            break
        except (genai_errors.ClientError, genai_errors.ServerError) as exc:
            status_code = getattr(exc, "code", None)
            if status_code in (404, 429, 500, 502, 503, 504):
                logger.warning(
                    "Modelo Gemini '%s' no disponible (HTTP %s). Probando fallback.",
                    modelo,
                    status_code,
                )
                ultimo_error = exc
                continue
            raise

    if response is None:
        raise RuntimeError(
            f"Ningún modelo Gemini disponible respondió correctamente: {ultimo_error}"
        ) from ultimo_error

    if not response.text:
        raise RuntimeError(
            "Gemini no devolvió contenido al analizar la historia clínica."
        )

    try:
        datos = json.loads(response.text)
    except json.JSONDecodeError as exc:
        logger.error("Respuesta no JSON de Gemini: %s", response.text)
        raise RuntimeError(
            "Gemini devolvió una respuesta con formato JSON inválido."
        ) from exc

    return _normalizar_resultado(datos)
