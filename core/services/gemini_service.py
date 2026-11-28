import csv
import io
import json
import logging
import math
import os
from pathlib import Path

from django.conf import settings
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field, ValidationError
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PyPdfError

logger = logging.getLogger(__name__)

# Configuración oficial de transición: cero dependencia de Gemini 2.5 tras el 1 de diciembre de 2026.
MODELO_GEMINI_PRINCIPAL = "gemini-3.8-flash"
MODELOS_GEMINI_FALLBACK = (
    "gemini-3.5-flash-lite",
)

# Límites seguros para envío directo inline (types.Part.from_bytes sin subir a almacenamiento externo).
LIMITE_INLINE_PDF_BYTES = 20 * 1024 * 1024  # 20 MB recomendados por Gemini API para inline PDF
LIMITE_MAXIMO_PAGINAS_PDF = 1000
MAX_OUTPUT_TOKENS_EXTRACCION = 65536


def _normalizar_modelo_activo(modelo_raw: str | None) -> str:
    """
    Garantiza que no se utilicen modelos retirados de la serie Gemini 2.5 incluso
    si una variable de entorno heredada aún los referencia.
    """
    candidato = (modelo_raw or "").strip()
    limpio = candidato.lower().removeprefix("models/")
    if not limpio:
        return MODELO_GEMINI_PRINCIPAL
    if limpio.startswith("gemini-2.5"):
        logger.warning(
            "GEMINI_MODEL='%s' pertenece a la serie Gemini 2.5 deprecada; "
            "redirigiendo automáticamente a '%s'.",
            candidato,
            MODELO_GEMINI_PRINCIPAL,
        )
        return MODELO_GEMINI_PRINCIPAL
    return candidato


MODELO_GEMINI = _normalizar_modelo_activo(os.getenv("GEMINI_MODEL"))

MIMES_PDF_PERMITIDOS = frozenset({
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "applications/vnd.pdf",
    "text/pdf",
    "text/x-pdf",
})
MIMES_GENERICOS_MULTIPART = frozenset({
    "",
    "application/octet-stream",
    "binary/octet-stream",
})

CAMPOS_RANGO = (
    ("sistolica_min", "sistolica_max"),
    ("diastolica_min", "diastolica_max"),
    ("fc_min", "fc_max"),
    ("fr_min", "fr_max"),
    ("temp_min", "temp_max"),
    ("sat_min", "sat_max"),
)

CAMPOS_NUMERICOS_MEDICIONES = (
    "presion_sistolica",
    "presion_diastolica",
    "frecuencia_cardiaca",
    "frecuencia_respiratoria",
    "temperatura",
    "saturacion_oxigeno",
    "peso",
)


class ErrorExtraccionHistoriaPdf(Exception):
    """Base de errores controlados del servicio de extracción de historias clínicas."""


class ArchivoPdfInvalidoError(ErrorExtraccionHistoriaPdf, ValueError):
    """El archivo proporcionado no es un PDF válido, está cifrado o dañado."""


class TamanoPdfExcedidoError(ArchivoPdfInvalidoError):
    """El PDF supera el tamaño máximo permitido para envío directo inline a Gemini."""


class DocumentoClinicoIlegibleError(ErrorExtraccionHistoriaPdf, ValueError):
    """El PDF es estructuralmente válido pero su contenido visual es ilegible o en blanco."""


class RespuestaGeminiIncompletaError(ErrorExtraccionHistoriaPdf, RuntimeError):
    """Gemini devolvió una respuesta truncada, bloqueada, vacía o con JSON incompleto."""


class SignosVitalesMedidosSchema(BaseModel):
    """Mediciones reales/puntuales de signos vitales registradas en el PDF (NO son rangos ni metas)."""

    presion_sistolica: float | None = Field(
        default=None,
        description="Presión arterial sistólica medida en mmHg (última o representativa documentada), o null si no se registró.",
    )
    presion_diastolica: float | None = Field(
        default=None,
        description="Presión arterial diastólica medida en mmHg, o null si no se registró.",
    )
    frecuencia_cardiaca: float | None = Field(
        default=None,
        description="Frecuencia cardíaca medida en lpm, o null si no se registró.",
    )
    frecuencia_respiratoria: float | None = Field(
        default=None,
        description="Frecuencia respiratoria medida en rpm, o null si no se registró.",
    )
    temperatura: float | None = Field(
        default=None,
        description="Temperatura corporal medida en °C, o null si no se registró.",
    )
    saturacion_oxigeno: float | None = Field(
        default=None,
        description="Saturación de oxígeno (SpO2) medida en %, o null si no se registró.",
    )
    peso: float | None = Field(
        default=None,
        description="Peso corporal medido en kg, o null si no se registró.",
    )
    detalle_medicion: str = Field(
        default="",
        description="Detalle literal breve de las tomas o tabla de signos vitales documentadas en el PDF, o cadena vacía si no existen.",
    )


class ReferenciasClinicasExplicitasSchema(BaseModel):
    """
    Rangos o metas clínicas EXPLÍCITAMENTE escritas/prescritas en el PDF para el paciente.
    Nunca deben inferirse ni copiarse desde ejemplos ni desde mediciones puntuales.
    """

    sistolica_min: float | None = Field(
        default=None,
        description="Meta o referencia explícita de presión sistólica mínima en mmHg escrita en el PDF, o null si no se especifica.",
    )
    sistolica_max: float | None = Field(
        default=None,
        description="Meta o referencia explícita de presión sistólica máxima en mmHg escrita en el PDF, o null si no se especifica.",
    )
    diastolica_min: float | None = Field(
        default=None,
        description="Meta o referencia explícita de presión diastólica mínima en mmHg escrita en el PDF, o null si no se especifica.",
    )
    diastolica_max: float | None = Field(
        default=None,
        description="Meta o referencia explícita de presión diastólica máxima en mmHg escrita en el PDF, o null si no se especifica.",
    )
    fc_min: float | None = Field(
        default=None,
        description="Meta o referencia explícita de frecuencia cardíaca mínima en lpm escrita en el PDF, o null si no se especifica.",
    )
    fc_max: float | None = Field(
        default=None,
        description="Meta o referencia explícita de frecuencia cardíaca máxima en lpm escrita en el PDF, o null si no se especifica.",
    )
    fr_min: float | None = Field(
        default=None,
        description="Meta o referencia explícita de frecuencia respiratoria mínima en rpm escrita en el PDF, o null si no se especifica.",
    )
    fr_max: float | None = Field(
        default=None,
        description="Meta o referencia explícita de frecuencia respiratoria máxima en rpm escrita en el PDF, o null si no se especifica.",
    )
    temp_min: float | None = Field(
        default=None,
        description="Meta o referencia explícita de temperatura mínima en °C escrita en el PDF, o null si no se especifica.",
    )
    temp_max: float | None = Field(
        default=None,
        description="Meta o referencia explícita de temperatura máxima en °C escrita en el PDF, o null si no se especifica.",
    )
    sat_min: float | None = Field(
        default=None,
        description="Meta o referencia explícita de saturación de oxígeno (SpO2) mínima en % escrita en el PDF, o null si no se especifica.",
    )
    sat_max: float | None = Field(
        default=None,
        description="Meta o referencia explícita de saturación de oxígeno (SpO2) máxima en % escrita en el PDF, o null si no se especifica.",
    )
    resumen_condicion: str = Field(
        default="",
        description="Transcripción o descripción fiel de la meta o referencia clínica explícita indicada en el documento.",
    )


# Alias conservado por compatibilidad de nombres internos previos.
RangosVitalesGeriatricosSchema = ReferenciasClinicasExplicitasSchema


class ExtraccionHistoriaClinicaSchema(BaseModel):
    """Esquema integral devuelto por Gemini al analizar visualmente el PDF clínico."""

    documento_legible: bool = Field(
        description="True si el documento contiene información clínica legible (digital o escaneada); False si está en blanco, dañado o ilegible."
    )
    motivo_ilegible: str = Field(
        default="",
        description="Explicación breve solo cuando documento_legible es False; vacío en caso contrario.",
    )
    antecedentes: str = Field(
        description=(
            "Texto completo e íntegro de todos los antecedentes del paciente registrados en el PDF "
            "(patológicos, quirúrgicos, farmacológicos, hospitalarios, traumáticos, familiares, etc.), "
            "sin resumir ni truncar. Si el documento indica negación explícita (ej. 'Niega antecedentes quirúrgicos'), "
            "conservarla literalmente. Si no registra antecedentes, devolver cadena vacía ''."
        )
    )
    alergias: str = Field(
        description=(
            "Texto completo e íntegro de las alergias registradas en el PDF. "
            "Si existe negación explícita (ej. 'Niega alergias medicamentosas'), conservarla literalmente. "
            "Si el documento no menciona alergias, devolver cadena vacía ''."
        )
    )
    observaciones: str = Field(
        description=(
            "Texto completo e íntegro de las observaciones clínicas, evolución, examen físico relevante, "
            "cuidados o notas médicas documentadas en el PDF, sin recortar. "
            "Si el documento no registra observaciones, devolver cadena vacía ''."
        )
    )
    tiene_mediciones_signos_vitales: bool = Field(
        description="True únicamente si el PDF contiene tomas o mediciones reales de signos vitales del paciente."
    )
    signos_vitales_medidos: SignosVitalesMedidosSchema | None = Field(
        default=None,
        description="Mediciones puntuales reales tomadas al paciente en el PDF, o null si no existen mediciones.",
    )
    tiene_referencias_explicitas: bool = Field(
        description=(
            "True ÚNICAMENTE si el PDF declara de forma literal y explícita rangos objetivo, "
            "límites de alerta o metas terapéuticas numéricas de signos vitales prescritas para este paciente."
        )
    )
    rangos_vitales: ReferenciasClinicasExplicitasSchema | None = Field(
        default=None,
        description=(
            "Referencias o metas clínicas explícitas escritas en el PDF. "
            "Debe ser null cuando el documento no contiene rangos ni metas explícitas."
        ),
    )


def _normalizar_mime(content_type: str) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _leer_bytes_con_limite(
    archivo_pdf,
    limite_bytes: int = LIMITE_INLINE_PDF_BYTES,
) -> tuple[bytes, str, str]:
    """
    Obtiene los bytes originales del PDF sin agotar memoria si excede el límite inline,
    y restaura siempre el puntero en streams file-like.
    Retorna (pdf_bytes, nombre_detectado, mime_detectado).
    """
    if archivo_pdf is None:
        raise ArchivoPdfInvalidoError("No se proporcionó ningún archivo PDF.")

    max_lectura = limite_bytes + 1

    if isinstance(archivo_pdf, (str, Path)):
        ruta = Path(archivo_pdf)
        if not ruta.exists() or not ruta.is_file():
            raise ArchivoPdfInvalidoError("La ruta del archivo PDF no existe.")
        nombre_detectado = ruta.name
        tamano = ruta.stat().st_size
        if tamano > limite_bytes:
            raise TamanoPdfExcedidoError(
                f"El archivo PDF ({tamano} bytes) supera el límite máximo permitido de "
                f"{limite_bytes // (1024 * 1024)} MB para procesamiento directo."
            )
        return ruta.read_bytes(), nombre_detectado, ""

    if isinstance(archivo_pdf, (bytes, bytearray, memoryview)):
        bruto = bytes(archivo_pdf)
        if len(bruto) > limite_bytes:
            raise TamanoPdfExcedidoError(
                f"El archivo PDF ({len(bruto)} bytes) supera el límite máximo permitido de "
                f"{limite_bytes // (1024 * 1024)} MB para procesamiento directo."
            )
        return bruto, "", ""

    if not hasattr(archivo_pdf, "read"):
        raise ArchivoPdfInvalidoError("El objeto recibido no es un archivo PDF legible.")

    nombre_detectado = str(getattr(archivo_pdf, "name", "") or "")
    mime_detectado = str(getattr(archivo_pdf, "content_type", "") or "")
    tamano_declarado = getattr(archivo_pdf, "size", None)
    if isinstance(tamano_declarado, int) and tamano_declarado > limite_bytes:
        raise TamanoPdfExcedidoError(
            f"El archivo PDF ({tamano_declarado} bytes) supera el límite máximo permitido de "
            f"{limite_bytes // (1024 * 1024)} MB para procesamiento directo."
        )

    if hasattr(archivo_pdf, "seek"):
        archivo_pdf.seek(0)

    try:
        leido = archivo_pdf.read(max_lectura)
    finally:
        if hasattr(archivo_pdf, "seek"):
            try:
                archivo_pdf.seek(0)
            except (OSError, ValueError) as exc:
                logger.debug("No se pudo restaurar puntero del PDF: %s", exc)

    if isinstance(leido, str):
        raise ArchivoPdfInvalidoError(
            "El archivo PDF debe abrirse en modo binario (bytes), no como texto."
        )

    bruto = bytes(leido or b"")
    if len(bruto) > limite_bytes:
        raise TamanoPdfExcedidoError(
            f"El archivo PDF supera el límite máximo permitido de "
            f"{limite_bytes // (1024 * 1024)} MB para procesamiento directo."
        )

    return bruto, nombre_detectado, mime_detectado


def validar_y_leer_bytes_pdf(
    archivo_pdf,
    *,
    nombre_archivo: str = "",
    content_type: str = "",
    limite_bytes: int = LIMITE_INLINE_PDF_BYTES,
) -> bytes:
    """
    Valida tamaño, extensión/MIME, cabecera %PDF-, ausencia de cifrado y estructura
    de páginas con pypdf, SIN exigir texto extraíble (admite PDFs escaneados).
    """
    pdf_bytes, nombre_stream, mime_stream = _leer_bytes_con_limite(
        archivo_pdf,
        limite_bytes=limite_bytes,
    )

    if not pdf_bytes:
        raise ArchivoPdfInvalidoError("El archivo PDF está vacío.")

    nombre_final = (nombre_archivo or nombre_stream or "").strip()
    if nombre_final and not Path(nombre_final).name.lower().endswith(".pdf"):
        raise ArchivoPdfInvalidoError(
            "El archivo debe tener extensión .pdf válida."
        )

    mime_final = _normalizar_mime(content_type or mime_stream)
    if (
        mime_final
        and mime_final not in MIMES_PDF_PERMITIDOS
        and mime_final not in MIMES_GENERICOS_MULTIPART
    ):
        raise ArchivoPdfInvalidoError(
            f"Tipo de contenido no permitido ('{mime_final}'). Solo se aceptan archivos PDF."
        )

    # La especificación PDF exige la cabecera %PDF- dentro de los primeros 1024 bytes.
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise ArchivoPdfInvalidoError(
            "El archivo no posee una firma binaria %PDF- válida."
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise ArchivoPdfInvalidoError(
                "El archivo PDF está protegido con contraseña y no puede procesarse."
            )
        total_paginas = len(reader.pages)
    except ArchivoPdfInvalidoError:
        raise
    except (FileNotDecryptedError, PyPdfError, OSError, ValueError, EOFError) as exc:
        raise ArchivoPdfInvalidoError(
            "El archivo PDF está dañado o su estructura interna no es válida."
        ) from exc

    if total_paginas < 1:
        raise ArchivoPdfInvalidoError(
            "El archivo PDF no contiene páginas para analizar."
        )
    if total_paginas > LIMITE_MAXIMO_PAGINAS_PDF:
        raise ArchivoPdfInvalidoError(
            f"El archivo PDF contiene {total_paginas} páginas y supera el máximo "
            f"soportado de {LIMITE_MAXIMO_PAGINAS_PDF} páginas."
        )

    return pdf_bytes


def cargar_registros_dataset() -> list[dict[str, str]]:
    """
    Lee en modo solo lectura los registros de dataset_entrenamiento.csv desde BASE_DIR
    sin modificar jamás el archivo.
    """
    ruta_csv = Path(settings.BASE_DIR) / "dataset_entrenamiento.csv"

    if not ruta_csv.exists():
        logger.warning(
            "No se encontró dataset_entrenamiento.csv en %s",
            ruta_csv,
        )
        return []

    registros: list[dict[str, str]] = []
    with open(ruta_csv, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for fila in reader:
            id_reg = (fila.get("id_registro") or "").strip()
            entrada = (fila.get("texto_entrada") or "").strip()
            salida = (fila.get("salida_esperada") or "").strip()
            if id_reg and entrada and salida:
                registros.append(
                    {
                        "id_registro": id_reg,
                        "texto_entrada": entrada,
                        "salida_esperada": salida,
                    }
                )
    return registros


def _cargar_ejemplos_few_shot() -> str:
    """Formatea los 15 registros originales del dataset como guía conceptual de lectura clínica."""
    registros = cargar_registros_dataset()
    if not registros:
        return ""

    lineas = []
    for reg in registros:
        lineas.append(
            f"- [{reg['id_registro']}] Texto de ejemplo: {reg['texto_entrada']}\n"
            f"  Interpretación clínica de referencia: {reg['salida_esperada']}"
        )
    return "\n".join(lineas)


def _construir_prompt_historia_clinica(ejemplos_few_shot: str) -> str:
    """
    Construye el prompt multimodal instruyendo extracción íntegra y prohibiendo
    estrictamente inventar signos vitales o rangos clínicos no explícitos.
    """
    bloque_ejemplos = ""
    if ejemplos_few_shot:
        bloque_ejemplos = (
            "### GUÍA DE LECTURA CLÍNICA GERIÁTRICA (15 CASOS DE REFERENCIA — NO COPIAR DATOS)\n"
            "Los siguientes 15 casos muestran cómo en geriatría se diferencian dos conceptos distintos:\n"
            "  a) Mediciones puntuales registradas un día concreto (ej. 'Hoy registra TA 144/82 mmHg', "
            "como en REG-001 y REG-015 donde NO existe meta personalizada prescrita).\n"
            "  b) Metas o referencias clínicas explícitamente prescritas en el texto "
            "(ej. las frases literales 'meta geriátrica: mantener TA entre 135/80 y 150/85 mmHg', "
            "'meta clínica: mantener SatO2 entre 88% y 92%' o 'meta terapéutica: mantener FC bajo 65 lpm').\n"
            "PROHIBICIÓN ABSOLUTA SOBRE ESTOS EJEMPLOS:\n"
            "- NUNCA copies, traslades ni extrapoles números, metas, rangos, diagnósticos ni textos de "
            "REG-001..REG-015 al paciente del PDF adjunto, aunque el paciente tenga la misma enfermedad "
            "(por ejemplo EPOC, hipertensión, insuficiencia cardíaca, marcapasos, ACV o aneurisma).\n"
            "- Si el PDF adjunto menciona una patología pero NO escribe explícitamente una meta o rango "
            "numérico para ese paciente, `tiene_referencias_explicitas` DEBE ser `false` y `rangos_vitales` DEBE ser `null`.\n\n"
            f"{ejemplos_few_shot}\n\n"
        )

    return (
        "Analiza visual e íntegramente el documento PDF de historia clínica adjunto "
        "(puede ser digital o escaneado en una o varias páginas) y devuelve únicamente "
        "el JSON estructurado solicitado.\n\n"
        "REGLAS OBLIGATORIAS E INQUEBRANTABLES:\n"
        "1. LEGIBILIDAD DEL DOCUMENTO:\n"
        "   - Si el PDF está completamente en blanco, dañado visualmente, ilegible o no corresponde "
        "a información legible, devuelve `documento_legible = false` y explica en `motivo_ilegible`.\n"
        "   - Si el PDF es legible (incluso si es un documento escaneado), devuelve `documento_legible = true`.\n\n"
        "2. EXTRACCIÓN COMPLETA SIN RESUMIR NI TRUNCAR:\n"
        "   - Extrae de forma completa e íntegra `antecedentes`, `alergias` y `observaciones` "
        "respetando toda la información clínica presente en todas las páginas del PDF, sin recortar listas ni párrafos largos.\n"
        "   - No agregues campos de diagnósticos separados ni inventes encabezados de relleno.\n"
        "   - Diferencia estrictamente negación explícita de ausencia:\n"
        "     * Si el PDF expresa una negación médica explícita (por ejemplo: 'Niega alergias', "
        "'Sin alergias medicamentosas conocidas', 'Niega antecedentes quirúrgicos'), conserva ese texto literal.\n"
        "     * Si el PDF NO menciona ni contiene información para alguno de esos campos, devuelve cadena vacía `\"\"` "
        "(no escribas 'No especificado', 'N/A' ni 'No registrado').\n\n"
        "3. MEDICIONES REALES DE SIGNOS VITALES (`signos_vitales_medidos`):\n"
        "   - Registra aquí ÚNICAMENTE valores numéricos que hayan sido medidos/tomados al paciente en el PDF.\n"
        "   - Si el PDF no contiene ninguna medición de signos vitales, devuelve "
        "`tiene_mediciones_signos_vitales = false` y `signos_vitales_medidos = null`.\n"
        "   - Si solo aparecen algunos signos medidos, deja en `null` los signos no medidos; jamás los inventes.\n\n"
        "4. REFERENCIAS O METAS CLÍNICAS EXPLÍCITAS (`rangos_vitales`):\n"
        "   - Pobla `rangos_vitales` ÚNICAMENTE cuando el PDF declare de forma literal y explícita "
        "un rango objetivo, límite de alerta o meta terapéutica prescrita para este paciente "
        "(ej. 'Meta TA: 130-150 / 70-85 mmHg', 'Mantener SpO2 entre 88% y 92%', 'Mantener FC menor a 65 lpm').\n"
        "   - NUNCA conviertas una medición puntual o una tabla de tomas históricas en `rangos_vitales`.\n"
        "   - NUNCA inventes rangos fisiológicos generales ni infieras rangos por edad o patología.\n"
        "   - Si el PDF NO contiene metas o referencias clínicas explícitas, devuelve obligatoriamente "
        "`tiene_referencias_explicitas = false` y `rangos_vitales = null`.\n"
        "   - Si el PDF solo especifica meta explícita para uno o algunos signos (o solo mínimo o solo máximo), "
        "asigna únicamente esos límites explícitos y deja todos los demás campos numéricos en `null`.\n\n"
        f"{bloque_ejemplos}"
        "Analiza ahora exclusivamente el documento PDF adjunto de este paciente y responde solo con el JSON."
    )


def _limpiar_numero_opcional(valor) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isnan(numero) or math.isinf(numero):
        return None
    return numero


def _normalizar_mediciones(
    tiene_mediciones: bool,
    mediciones_raw: dict | None,
) -> tuple[bool, dict | None]:
    if not tiene_mediciones or not isinstance(mediciones_raw, dict):
        return False, None

    limpio: dict[str, float | None | str] = {}
    hay_algun_valor = False
    for campo in CAMPOS_NUMERICOS_MEDICIONES:
        num = _limpiar_numero_opcional(mediciones_raw.get(campo))
        limpio[campo] = num
        if num is not None:
            hay_algun_valor = True

    detalle = (mediciones_raw.get("detalle_medicion") or "").strip()
    limpio["detalle_medicion"] = detalle

    if not hay_algun_valor and not detalle:
        return False, None

    return True, limpio


def _normalizar_referencias_explicitas(
    tiene_referencias: bool,
    rangos_raw: dict | None,
) -> tuple[bool, dict | None]:
    if not tiene_referencias or not isinstance(rangos_raw, dict):
        return False, None

    limpio: dict[str, float | None | str] = {}
    hay_algun_limite_numerico = False

    for campo_min, campo_max in CAMPOS_RANGO:
        val_min = _limpiar_numero_opcional(rangos_raw.get(campo_min))
        val_max = _limpiar_numero_opcional(rangos_raw.get(campo_max))
        if val_min is not None and val_max is not None and val_min > val_max:
            val_min, val_max = val_max, val_min
        limpio[campo_min] = val_min
        limpio[campo_max] = val_max
        if val_min is not None or val_max is not None:
            hay_algun_limite_numerico = True

    # Si no existe ningún límite numérico explícito real, no se permite devolver rangos vacíos ni inventados.
    if not hay_algun_limite_numerico:
        return False, None

    limpio["resumen_condicion"] = (rangos_raw.get("resumen_condicion") or "").strip()
    return True, limpio


def _normalizar_extraccion_historia(datos: dict) -> dict:
    """Valida contra el esquema estricto y normaliza textos, mediciones y referencias explícitas."""
    if not isinstance(datos, dict):
        raise RespuestaGeminiIncompletaError(
            "Gemini no devolvió un objeto JSON válido al extraer la historia clínica."
        )

    try:
        validado = ExtraccionHistoriaClinicaSchema.model_validate(datos).model_dump()
    except ValidationError as exc:
        raise RespuestaGeminiIncompletaError(
            "La respuesta de Gemini está incompleta o no cumple el esquema clínico requerido."
        ) from exc

    if not validado["documento_legible"]:
        motivo = (validado.get("motivo_ilegible") or "").strip()
        detalle = f" Detalle: {motivo}" if motivo else ""
        raise DocumentoClinicoIlegibleError(
            f"El documento PDF no es legible para extraer la historia clínica.{detalle}"
        )

    antecedentes = (validado.get("antecedentes") or "").strip()
    alergias = (validado.get("alergias") or "").strip()
    observaciones = (validado.get("observaciones") or "").strip()

    tiene_mediciones, mediciones = _normalizar_mediciones(
        bool(validado.get("tiene_mediciones_signos_vitales")),
        validado.get("signos_vitales_medidos"),
    )
    tiene_referencias, rangos_vitales = _normalizar_referencias_explicitas(
        bool(validado.get("tiene_referencias_explicitas")),
        validado.get("rangos_vitales"),
    )

    return {
        "documento_legible": True,
        "motivo_ilegible": "",
        "antecedentes": antecedentes,
        "alergias": alergias,
        "observaciones": observaciones,
        "tiene_mediciones_signos_vitales": tiene_mediciones,
        "signos_vitales_medidos": mediciones,
        "tiene_referencias_explicitas": tiene_referencias,
        "rangos_vitales": rangos_vitales,
    }


def construir_thinking_config_compatible(modelo: str) -> types.ThinkingConfig | None:
    """
    Construye la configuración de razonamiento con `thinking_level=LOW` compatible con
    `gemini-3.8-flash` y `gemini-3.5-flash-lite` en google-genai 3.5.0 (sin `thinking_budget`).
    """
    nombre = (modelo or "").strip().lower().removeprefix("models/")
    if nombre.startswith(("gemini-3", "gemini-4")):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    return None


def _construir_config_generacion(
    modelo: str,
    *,
    incluir_thinking: bool = True,
) -> types.GenerateContentConfig:
    kwargs: dict = {
        "response_mime_type": "application/json",
        "response_schema": ExtraccionHistoriaClinicaSchema,
        "temperature": 0.0,
        "max_output_tokens": MAX_OUTPUT_TOKENS_EXTRACCION,
    }
    if incluir_thinking:
        thinking_cfg = construir_thinking_config_compatible(modelo)
        if thinking_cfg is not None:
            kwargs["thinking_config"] = thinking_cfg
    return types.GenerateContentConfig(**kwargs)


def _obtener_modelos_candidatos() -> list[str]:
    modelo_principal = _normalizar_modelo_activo(os.getenv("GEMINI_MODEL"))
    return list(dict.fromkeys([modelo_principal, *MODELOS_GEMINI_FALLBACK]))


def _es_error_thinking_incompatible(exc: Exception) -> bool:
    codigo = getattr(exc, "code", None)
    if codigo != 400:
        return False
    texto = str(exc).lower()
    return "thinking" in texto


def _extraer_texto_respuesta(response) -> str:
    texto_directo = getattr(response, "text", None)
    if isinstance(texto_directo, str) and texto_directo.strip():
        return texto_directo.strip()

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""

    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    fragmentos = []
    for part in parts:
        if getattr(part, "thought", False):
            continue
        txt = getattr(part, "text", None)
        if isinstance(txt, str) and txt:
            fragmentos.append(txt)
    return "".join(fragmentos).strip()


def _es_finish_reason_stop(finish_reason) -> bool:
    if finish_reason == types.FinishReason.STOP:
        return True
    nombre = getattr(finish_reason, "name", None) or str(finish_reason or "")
    return nombre.upper().endswith("STOP") and nombre.upper() in ("STOP", "FINISHREASON.STOP")


def _validar_y_parsear_respuesta_gemini(response) -> dict:
    """
    Exige candidato válido, ausencia de bloqueo, FinishReason.STOP y JSON íntegro
    para impedir que respuestas truncadas o parciales pasen como válidas.
    """
    if response is None:
        raise RespuestaGeminiIncompletaError(
            "No se obtuvo respuesta de ningún modelo Gemini disponible."
        )

    prompt_feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(prompt_feedback, "block_reason", None)
    if block_reason:
        raise RespuestaGeminiIncompletaError(
            f"La solicitud a Gemini fue bloqueada ({block_reason})."
        )

    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise RespuestaGeminiIncompletaError(
            "Gemini no devolvió candidatos en la respuesta al analizar el PDF."
        )

    candidato = candidates[0]
    finish_reason = getattr(candidato, "finish_reason", None)
    if not _es_finish_reason_stop(finish_reason):
        raise RespuestaGeminiIncompletaError(
            f"La respuesta de Gemini terminó de forma incompleta o anormal "
            f"(finish_reason={finish_reason}). Se aborta para evitar datos truncados."
        )

    texto_json = _extraer_texto_respuesta(response)
    if not texto_json:
        raise RespuestaGeminiIncompletaError(
            "Gemini devolvió una respuesta vacía al analizar la historia clínica."
        )

    try:
        datos = json.loads(texto_json)
    except json.JSONDecodeError as exc:
        logger.error("Respuesta JSON truncada o inválida de Gemini: %s", texto_json[:500])
        raise RespuestaGeminiIncompletaError(
            "Gemini devolvió un JSON truncado o con formato inválido."
        ) from exc

    return _normalizar_extraccion_historia(datos)


def extraer_historia_clinica_pdf(
    archivo_pdf,
    *,
    nombre_archivo: str = "",
    content_type: str = "",
) -> dict:
    """
    Envía el PDF original de forma multimodal a Gemini para extraer de manera íntegra
    antecedentes, alergias, observaciones, mediciones reales de signos vitales y
    únicamente referencias/metas clínicas explícitas (soportando PDFs digitales y escaneados).
    """
    pdf_bytes = validar_y_leer_bytes_pdf(
        archivo_pdf,
        nombre_archivo=nombre_archivo,
        content_type=content_type,
    )

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY no está configurada en las variables de entorno."
        )

    ejemplos_few_shot = _cargar_ejemplos_few_shot()
    prompt = _construir_prompt_historia_clinica(ejemplos_few_shot)
    pdf_part = types.Part.from_bytes(
        data=pdf_bytes,
        mime_type="application/pdf",
    )
    contenidos = [pdf_part, prompt]

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=60000,
            retry_options=types.HttpRetryOptions(attempts=2),
        ),
    )

    modelos_a_probar = _obtener_modelos_candidatos()
    response = None
    ultimo_error: Exception | None = None

    for modelo in modelos_a_probar:
        config = _construir_config_generacion(modelo, incluir_thinking=True)
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=contenidos,
                config=config,
            )
            break
        except genai_errors.ClientError as exc:
            if _es_error_thinking_incompatible(exc):
                logger.warning(
                    "Modelo Gemini '%s' rechazó thinking_config; reintentando sin thinking_config.",
                    modelo,
                )
                try:
                    config_sin_thinking = _construir_config_generacion(
                        modelo,
                        incluir_thinking=False,
                    )
                    response = client.models.generate_content(
                        model=modelo,
                        contents=contenidos,
                        config=config_sin_thinking,
                    )
                    break
                except (genai_errors.ClientError, genai_errors.ServerError) as retry_exc:
                    exc = retry_exc

            status_code = getattr(exc, "code", None)
            if status_code in (404, 429, 500, 502, 503, 504):
                logger.warning(
                    "Modelo Gemini '%s' no disponible (HTTP %s). Probando modelo alternativo.",
                    modelo,
                    status_code,
                )
                ultimo_error = exc
                continue
            raise
        except genai_errors.ServerError as exc:
            status_code = getattr(exc, "code", None)
            logger.warning(
                "Error de servidor en modelo Gemini '%s' (HTTP %s). Probando modelo alternativo.",
                modelo,
                status_code,
            )
            ultimo_error = exc
            continue

    if response is None:
        raise RuntimeError(
            f"Ningún modelo Gemini disponible respondió correctamente: {ultimo_error}"
        ) from ultimo_error

    return _validar_y_parsear_respuesta_gemini(response)


def analizar_pdf_geriatrico(archivo_pdf) -> dict | None:
    """
    Función de compatibilidad mientras no se integran los nuevos endpoints (Etapas 4 y 5).
    Delega en extraer_historia_clinica_pdf() y devuelve únicamente rangos_vitales (o None).
    """
    resultado = extraer_historia_clinica_pdf(archivo_pdf)
    return resultado["rangos_vitales"]
