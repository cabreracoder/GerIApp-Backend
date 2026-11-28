import hashlib
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from rest_framework import status

from core.models import Bitacora, HistoriaClinicas, Pacientes, SignosVitales
from core.serializers import evaluar_rangos_signos_vitales
from core.services.gemini_service import (
    LIMITE_INLINE_PDF_BYTES,
    MAX_OUTPUT_TOKENS_EXTRACCION,
    MODELO_GEMINI,
    MODELO_GEMINI_PRINCIPAL,
    MODELOS_GEMINI_FALLBACK,
    ArchivoPdfInvalidoError,
    DocumentoClinicoIlegibleError,
    ExtraccionHistoriaClinicaSchema,
    RespuestaGeminiIncompletaError,
    TamanoPdfExcedidoError,
    analizar_pdf_geriatrico,
    cargar_registros_dataset,
    construir_thinking_config_compatible,
    extraer_historia_clinica_pdf,
    validar_y_leer_bytes_pdf,
)
from core.tests_historia_clinica import BaseTablasHistoriaEnMemoriaTestCase
from core.views import _guardar_rangos_historia_clinica

# Hash SHA-256 exacto del blob confirmado en Git (`git cat-file blob HEAD:dataset_entrenamiento.csv`).
SHA256_HEAD_DATASET_CONFIRMADO = (
    "b04384f3d2d9ca02451dceafd7854b48d673c64da31a5c27fbcb95b16e541f5b"
)


def envolver_lineas_por_ancho_px(
    texto: str,
    dibujo: ImageDraw.ImageDraw,
    fuente: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_ancho_px: int,
) -> list[str]:
    """
    Ajusta automáticamente cada párrafo al ancho visible en píxeles (`max_ancho_px`),
    sin perder ningún carácter ni desbordar horizontalmente la imagen.
    """
    lineas_ajustadas: list[str] = []
    for parrafo in texto.splitlines():
        if not parrafo.strip():
            lineas_ajustadas.append("")
            continue

        palabras = parrafo.split()
        actual = ""
        for palabra in palabras:
            # Si una palabra individual supera el ancho útil, partirla carácter por carácter
            while dibujo.textlength(palabra, font=fuente) > max_ancho_px:
                if actual:
                    lineas_ajustadas.append(actual)
                    actual = ""
                corte = 1
                while (
                    corte < len(palabra)
                    and dibujo.textlength(palabra[: corte + 1], font=fuente) <= max_ancho_px
                ):
                    corte += 1
                lineas_ajustadas.append(palabra[:corte])
                palabra = palabra[corte:]

            candidato = f"{actual} {palabra}".strip() if actual else palabra
            if dibujo.textlength(candidato, font=fuente) <= max_ancho_px:
                actual = candidato
            else:
                if actual:
                    lineas_ajustadas.append(actual)
                actual = palabra

        if actual:
            lineas_ajustadas.append(actual)

    return lineas_ajustadas


def construir_pdf_escaneado_con_imagen_texto(
    texto_documento: str = (
        "HISTORIA CLINICA ESCANEADA\n"
        "Antecedentes: HTA cronica y diabetes tipo 2.\n"
        "Alergias: Penicilina."
    ),
    *,
    retornar_metadatos: bool = False,
) -> bytes | tuple[bytes, dict]:
    """
    Construye 100% en memoria un PDF escaneado multipágina donde todo `texto_documento`
    se ajusta automáticamente al ancho visible de la página y se distribuye en tantas
    páginas RGB como sea necesario (sin capa de texto extraíble por pypdf).
    """
    ancho_pagina, alto_pagina = 900, 1200
    margen_izq, margen_der = 55, 55
    max_ancho_px = ancho_pagina - margen_izq - margen_der
    y_encabezado = 55
    y_inicio_cuerpo = 98
    y_limite_inferior = 1135
    alto_linea = 26

    fuente = ImageFont.load_default(size=17)
    lienzo_medicion = Image.new("RGB", (ancho_pagina, alto_pagina), color="white")
    dibujo_medicion = ImageDraw.Draw(lienzo_medicion)

    lineas_totales = envolver_lineas_por_ancho_px(
        texto_documento,
        dibujo_medicion,
        fuente,
        max_ancho_px,
    )
    if not lineas_totales:
        lineas_totales = [""]

    bloques_paginas: list[list[str]] = []
    bloque_actual: list[str] = []
    y_cursor = y_inicio_cuerpo

    for linea in lineas_totales:
        if bloque_actual and (y_cursor + alto_linea > y_limite_inferior):
            bloques_paginas.append(bloque_actual)
            bloque_actual = []
            y_cursor = y_inicio_cuerpo
        bloque_actual.append(linea)
        y_cursor += alto_linea

    if bloque_actual:
        bloques_paginas.append(bloque_actual)

    imagenes: list[Image.Image] = []
    max_ancho_medido = 0.0
    max_y_dibujado = 0
    total_paginas = len(bloques_paginas)

    for indice, lineas_pagina in enumerate(bloques_paginas, start=1):
        lienzo = Image.new("RGB", (ancho_pagina, alto_pagina), color="white")
        dibujo = ImageDraw.Draw(lienzo)
        dibujo.rectangle([(30, 30), (870, 1170)], outline="black", width=2)
        encabezado = f"Historia clinica escaneada - Pagina {indice} de {total_paginas}"
        dibujo.text((margen_izq, y_encabezado), encabezado, fill="black", font=fuente)

        y = y_inicio_cuerpo
        for linea in lineas_pagina:
            ancho_linea = dibujo.textlength(linea, font=fuente)
            max_ancho_medido = max(max_ancho_medido, ancho_linea)
            dibujo.text((margen_izq, y), linea, fill="black", font=fuente)
            max_y_dibujado = max(max_y_dibujado, y + alto_linea)
            y += alto_linea

        imagenes.append(lienzo)

    buffer = io.BytesIO()
    primera, restantes = imagenes[0], imagenes[1:]
    primera.save(
        buffer,
        format="PDF",
        resolution=150.0,
        save_all=bool(restantes),
        append_images=restantes,
    )
    pdf_bytes = buffer.getvalue()
    if retornar_metadatos:
        return pdf_bytes, {
            "num_paginas": total_paginas,
            "lineas_dibujadas": lineas_totales,
            "max_ancho_px_permitido": max_ancho_px,
            "max_ancho_px_medido": max_ancho_medido,
            "y_limite_inferior": y_limite_inferior,
            "max_y_dibujado": max_y_dibujado,
        }
    return pdf_bytes


def construir_pdf_paginas_en_blanco(num_paginas: int = 1) -> bytes:
    """Construye en memoria un PDF estructuralmente válido con páginas completamente en blanco."""
    writer = PdfWriter()
    for _ in range(num_paginas):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def construir_pdf_digital_con_texto(texto: str = "Historia clinica digital de prueba") -> bytes:
    """Construye en memoria un PDF digital válido con texto extraíble por pypdf."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    fuente = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    fuente_ref = writer._add_object(fuente)
    recursos = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): fuente_ref})}
    )
    page[NameObject("/Resources")] = recursos

    texto_escapado = (
        texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    )
    contenido = DecodedStreamObject()
    contenido.set_data(f"BT /F1 12 Tf 72 720 Td ({texto_escapado}) Tj ET".encode("latin-1", errors="ignore"))
    contenido_ref = writer._add_object(contenido)
    page[NameObject("/Contents")] = contenido_ref

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def construir_pdf_protegido_con_password(password: str = "secreto123") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def simular_respuesta_gemini(
    payload: dict | str | None,
    *,
    finish_reason=types.FinishReason.STOP,
    sin_candidatos: bool = False,
    block_reason: str | None = None,
):
    """Crea una respuesta simulada equivalente a GenerateContentResponse del SDK google-genai."""
    prompt_feedback = SimpleNamespace(block_reason=block_reason)
    if sin_candidatos:
        return SimpleNamespace(
            text=None,
            candidates=[],
            prompt_feedback=prompt_feedback,
        )

    if isinstance(payload, dict):
        texto = json.dumps(payload, ensure_ascii=False)
    else:
        texto = payload

    partes = [SimpleNamespace(text=texto, thought=False)] if texto is not None else []
    candidato = SimpleNamespace(
        finish_reason=finish_reason,
        content=SimpleNamespace(parts=partes),
    )
    return SimpleNamespace(
        text=texto,
        candidates=[candidato],
        prompt_feedback=prompt_feedback,
    )


class ValidacionPdfYLecturaDatasetTests(SimpleTestCase):
    """Pruebas unitarias de validación de PDF (digital, escaneado, tamaño) e integridad del dataset."""

    def test_dataset_entrenamiento_coincide_con_head_git_y_conserva_los_15_registros_originales(self):
        ruta_csv = Path(settings.BASE_DIR) / "dataset_entrenamiento.csv"
        self.assertTrue(ruta_csv.exists(), "dataset_entrenamiento.csv debe existir en BASE_DIR")

        bytes_head_git = subprocess.check_output(
            ["git", "cat-file", "blob", "HEAD:dataset_entrenamiento.csv"],
            cwd=settings.BASE_DIR,
        )
        sha_head_git = hashlib.sha256(bytes_head_git).hexdigest()
        self.assertEqual(sha_head_git, SHA256_HEAD_DATASET_CONFIRMADO)

        bytes_disco_antes = ruta_csv.read_bytes()
        registros = cargar_registros_dataset()
        bytes_disco_despues = ruta_csv.read_bytes()

        # Garantiza que la lectura no altera ni un byte en disco
        self.assertEqual(bytes_disco_antes, bytes_disco_despues)

        # Normaliza CRLF->LF de checkout Windows para comparar contenido exacto contra el blob HEAD de Git
        bytes_disco_canonico = bytes_disco_despues.replace(b"\r\n", b"\n")
        bytes_head_canonico = bytes_head_git.replace(b"\r\n", b"\n")
        self.assertEqual(bytes_disco_canonico, bytes_head_canonico)
        self.assertEqual(
            hashlib.sha256(bytes_disco_canonico).hexdigest(),
            SHA256_HEAD_DATASET_CONFIRMADO,
        )

        self.assertEqual(len(registros), 15)
        ids_esperados = [f"REG-{i:03d}" for i in range(1, 16)]
        self.assertEqual([r["id_registro"] for r in registros], ids_esperados)
        for reg in registros:
            self.assertTrue(reg["texto_entrada"])
            self.assertTrue(reg["salida_esperada"])

    def test_acepta_pdf_digital_y_restaura_puntero_del_stream(self):
        pdf_digital = construir_pdf_digital_con_texto("Paciente geriatrico control mensual")
        reader = PdfReader(io.BytesIO(pdf_digital))
        self.assertIn("Paciente geriatrico", reader.pages[0].extract_text())

        archivo = SimpleUploadedFile(
            "historia_digital.pdf",
            pdf_digital,
            content_type="application/pdf",
        )
        resultado = validar_y_leer_bytes_pdf(archivo)
        self.assertEqual(resultado, pdf_digital)
        self.assertEqual(archivo.tell(), 0)

    def test_acepta_pdf_escaneado_con_texto_en_imagen_no_extraible_por_pypdf(self):
        texto_escaneado = (
            "ANTECEDENTES: Hipertensión arterial y EPOC en seguimiento geriátrico.\n"
            "ALERGIAS: Penicilina.\n"
            "OBSERVACIONES: Marcha asistida con caminador y control de signos vitales."
        )
        pdf_escaneado, meta = construir_pdf_escaneado_con_imagen_texto(
            texto_escaneado,
            retornar_metadatos=True,
        )
        self.assertLessEqual(meta["max_ancho_px_medido"], meta["max_ancho_px_permitido"])
        self.assertLessEqual(meta["max_y_dibujado"], meta["y_limite_inferior"])

        reader = PdfReader(io.BytesIO(pdf_escaneado))
        self.assertEqual(len(reader.pages), meta["num_paginas"])
        for pagina in reader.pages:
            self.assertIn("/XObject", pagina["/Resources"])
            self.assertEqual((pagina.extract_text() or "").strip(), "")

        resultado = validar_y_leer_bytes_pdf(
            io.BytesIO(pdf_escaneado),
            nombre_archivo="historia_escaneada.pdf",
            content_type="application/pdf",
        )
        self.assertEqual(resultado, pdf_escaneado)

    def test_rechaza_archivos_no_pdf_vacios_corruptos_o_cifrados(self):
        with self.assertRaises(ArchivoPdfInvalidoError):
            validar_y_leer_bytes_pdf(None)

        with self.assertRaises(ArchivoPdfInvalidoError):
            validar_y_leer_bytes_pdf(b"")

        # Imagen disfrazada o extensión inválida
        with self.assertRaises(ArchivoPdfInvalidoError):
            validar_y_leer_bytes_pdf(
                b"\x89PNG\r\n\x1a\ncontenido",
                nombre_archivo="radiografia.png",
                content_type="image/png",
            )

        # Cabecera %PDF- pero estructura interna corrupta
        with self.assertRaises(ArchivoPdfInvalidoError):
            validar_y_leer_bytes_pdf(
                b"%PDF-1.7 archivo truncado corrupto sin xref",
                nombre_archivo="corrupto.pdf",
                content_type="application/pdf",
            )

        # PDF protegido con contraseña
        pdf_cifrado = construir_pdf_protegido_con_password()
        with self.assertRaises(ArchivoPdfInvalidoError):
            validar_y_leer_bytes_pdf(
                pdf_cifrado,
                nombre_archivo="protegido.pdf",
                content_type="application/pdf",
            )

    @patch("servicios.cloudinary_service.subir_documento")
    @patch("core.services.gemini_service.genai.Client")
    def test_limite_tamano_inline_pdf_rechaza_sin_subir_a_cloudinary_ni_llamar_gemini(
        self,
        mock_client_cls,
        mock_cloudinary,
    ):
        exceso_bytes = b"%PDF-1.4\n" + (b"0" * LIMITE_INLINE_PDF_BYTES)
        self.assertGreater(len(exceso_bytes), LIMITE_INLINE_PDF_BYTES)

        archivo_grande = SimpleUploadedFile(
            "historia_pesada.pdf",
            exceso_bytes,
            content_type="application/pdf",
        )

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}),
            self.assertRaises(TamanoPdfExcedidoError),
        ):
            extraer_historia_clinica_pdf(archivo_grande)

        mock_client_cls.assert_not_called()
        mock_cloudinary.assert_not_called()

    def test_esquema_pydantic_es_100_compatible_con_transformador_schema_de_google_genai(self):
        from google import genai
        from google.genai._transformers import t_schema

        cliente_local = genai.Client(api_key="dummy-offline-key")
        esquema_sdk = t_schema(cliente_local._api_client, ExtraccionHistoriaClinicaSchema)
        self.assertEqual(esquema_sdk.type, types.Type.OBJECT)
        self.assertIn("documento_legible", esquema_sdk.properties)
        self.assertIn("antecedentes", esquema_sdk.properties)
        self.assertIn("alergias", esquema_sdk.properties)
        self.assertIn("observaciones", esquema_sdk.properties)
        self.assertIn("signos_vitales_medidos", esquema_sdk.properties)
        self.assertIn("rangos_vitales", esquema_sdk.properties)
        self.assertTrue(esquema_sdk.properties["rangos_vitales"].nullable)
        self.assertTrue(esquema_sdk.properties["signos_vitales_medidos"].nullable)


class ExtraccionMultimodalGeminiTests(SimpleTestCase):
    """Pruebas con mocks del flujo completo de extracción clínica en extraer_historia_clinica_pdf()."""

    def _preparar_mock_cliente(self, mock_client_cls, respuestas_o_excepciones):
        instancia_cliente = MagicMock()
        mock_client_cls.return_value = instancia_cliente
        instancia_cliente.models.generate_content.side_effect = respuestas_o_excepciones
        return instancia_cliente

    @patch("core.services.gemini_service.genai.Client")
    def test_pdf_digital_en_memoria_envia_bytes_originales_multimodal_y_prompt_con_15_registros(
        self,
        mock_client_cls,
    ):
        pdf_bytes = construir_pdf_digital_con_texto(
            "Antecedentes: HTA y EPOC. Toma 10/10/2026 TA 147/93 mmHg FC 85 lpm SpO2 95%. Sin metas prescritas."
        )
        reader_digital = PdfReader(io.BytesIO(pdf_bytes))
        self.assertIn("Antecedentes: HTA y EPOC", reader_digital.pages[0].extract_text())

        payload_mock = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "Hipertensión arterial y enfermedad pulmonar obstructiva crónica (EPOC).",
            "alergias": "",
            "observaciones": "Cinco registros históricos sin rangos mínimos ni máximos prescritos.",
            "tiene_mediciones_signos_vitales": True,
            "signos_vitales_medidos": {
                "presion_sistolica": 147.0,
                "presion_diastolica": 93.0,
                "frecuencia_cardiaca": 85.0,
                "frecuencia_respiratoria": 18.0,
                "temperatura": 36.5,
                "saturacion_oxigeno": 95.0,
                "peso": 67.9,
                "detalle_medicion": "Última toma 10/10/2026: TA 147/93 mmHg, FC 85 lpm, FR 18 rpm, Temp 36.5 °C, SpO2 95%, Peso 67.9 kg.",
            },
            "tiene_referencias_explicitas": False,
            "rangos_vitales": None,
        }
        cliente_mock = self._preparar_mock_cliente(
            mock_client_cls,
            [simular_respuesta_gemini(payload_mock)],
        )

        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-key-ficticia", "GEMINI_MODEL": ""},
        ):
            resultado = extraer_historia_clinica_pdf(
                io.BytesIO(pdf_bytes),
                nombre_archivo="historia_digital_memoria.pdf",
                content_type="application/pdf",
            )

        self.assertEqual(cliente_mock.models.generate_content.call_count, 1)
        llamada = cliente_mock.models.generate_content.call_args.kwargs
        self.assertEqual(llamada["model"], "gemini-3.8-flash")

        contenidos = llamada["contents"]
        self.assertEqual(len(contenidos), 2)
        parte_pdf, prompt_enviado = contenidos[0], contenidos[1]
        self.assertIsInstance(parte_pdf, types.Part)
        self.assertEqual(parte_pdf.inline_data.mime_type, "application/pdf")
        self.assertEqual(parte_pdf.inline_data.data, pdf_bytes)

        # Verifica que los 15 registros del dataset se incluyeron como guía y se prohibió copiarlos
        for i in range(1, 16):
            self.assertIn(f"REG-{i:03d}", prompt_enviado)
        self.assertIn("NUNCA copies", prompt_enviado)

        config_usada = llamada["config"]
        self.assertEqual(config_usada.response_mime_type, "application/json")
        self.assertIs(config_usada.response_schema, ExtraccionHistoriaClinicaSchema)
        self.assertEqual(config_usada.max_output_tokens, MAX_OUTPUT_TOKENS_EXTRACCION)
        self.assertEqual(
            config_usada.thinking_config.thinking_level,
            types.ThinkingLevel.LOW,
        )
        self.assertIsNone(config_usada.thinking_config.thinking_budget)

        self.assertIsNone(resultado["rangos_vitales"])
        self.assertEqual(resultado["alergias"], "")
        self.assertEqual(resultado["signos_vitales_medidos"]["presion_sistolica"], 147.0)

    @patch("core.services.gemini_service.genai.Client")
    def test_pdf_escaneado_con_imagen_sin_texto_pypdf_envia_bytes_originales_y_extrae_textos_extensos(
        self,
        mock_client_cls,
    ):
        antecedentes_extensos = (
            "1. Hipertensión arterial crónica de 22 años de evolución en manejo médico continuo. "
            "2. Diabetes mellitus tipo 2 insulinorrequiriente con nefropatía estadio 3a. "
            "3. Antecedente quirúrgico de reemplazo total de cadera derecha (2018) y facoemulsificación bilateral (2021). "
            "4. Hipotiroidismo primario suplido con levotiroxina. "
        ) * 12  # > 3.600 caracteres (muy superior al antiguo corte de 200 caracteres)

        alergias_literales = (
            "Alergia severa documentada a penicilinas y betalactámicos (angioedema en 2014); "
            "intolerancia gastrointestinal severa a AINEs (ibuprofeno, naproxeno) y medios de contraste yodados."
        )
        observaciones_extensas = (
            "Paciente alerta, orientada parcialmente en tiempo, marcha asistida con caminador de cuatro apoyos, "
            "requiere vigilancia estricta del riesgo de caídas en transferencias cama-silla y control de piel en zona sacra. "
        ) * 10  # > 2.100 caracteres

        documento_completo_escaneado = (
            "HISTORIA CLÍNICA GERIÁTRICA ESCANEADA\n\n"
            f"ANTECEDENTES:\n{antecedentes_extensos}\n\n"
            f"ALERGIAS:\n{alergias_literales}\n\n"
            f"OBSERVACIONES CLÍNICAS:\n{observaciones_extensas}"
        )

        pdf_escaneado, meta_escaneo = construir_pdf_escaneado_con_imagen_texto(
            documento_completo_escaneado,
            retornar_metadatos=True,
        )

        # 1. Comprueba ajuste horizontal y distribución multipágina automática del 100% del contenido
        self.assertGreaterEqual(meta_escaneo["num_paginas"], 2)
        self.assertLessEqual(
            meta_escaneo["max_ancho_px_medido"],
            meta_escaneo["max_ancho_px_permitido"],
        )
        self.assertLessEqual(
            meta_escaneo["max_y_dibujado"],
            meta_escaneo["y_limite_inferior"],
        )
        texto_reconstruido_dibujado = " ".join(
            linea for linea in meta_escaneo["lineas_dibujadas"] if linea
        )
        self.assertEqual(
            texto_reconstruido_dibujado.split(),
            documento_completo_escaneado.split(),
        )

        # 2. Comprueba que cada página tiene su imagen embebida y pypdf NO puede extraer capa de texto
        reader_escaneado = PdfReader(io.BytesIO(pdf_escaneado))
        self.assertEqual(len(reader_escaneado.pages), meta_escaneo["num_paginas"])
        for pagina in reader_escaneado.pages:
            self.assertIn("/XObject", pagina["/Resources"])
        texto_extraido_pypdf = "".join(
            (p.extract_text() or "").strip() for p in reader_escaneado.pages
        )
        self.assertEqual(texto_extraido_pypdf, "")

        self.assertGreater(len(antecedentes_extensos), 3000)
        self.assertGreater(len(observaciones_extensas), 2000)

        payload_mock = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": antecedentes_extensos,
            "alergias": alergias_literales,
            "observaciones": observaciones_extensas,
            "tiene_mediciones_signos_vitales": False,
            "signos_vitales_medidos": None,
            "tiene_referencias_explicitas": False,
            "rangos_vitales": None,
        }
        cliente_mock = self._preparar_mock_cliente(
            mock_client_cls,
            [simular_respuesta_gemini(payload_mock)],
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}):
            resultado = extraer_historia_clinica_pdf(
                pdf_escaneado,
                nombre_archivo="escaneo_4_paginas.pdf",
                content_type="application/pdf",
            )

        # Comprueba que el servicio envió a Gemini exactamente los bytes originales del PDF escaneado con imagen
        self.assertEqual(cliente_mock.models.generate_content.call_count, 1)
        parte_pdf_enviada = cliente_mock.models.generate_content.call_args.kwargs["contents"][0]
        self.assertIsInstance(parte_pdf_enviada, types.Part)
        self.assertEqual(parte_pdf_enviada.inline_data.mime_type, "application/pdf")
        self.assertEqual(parte_pdf_enviada.inline_data.data, pdf_escaneado)

        self.assertEqual(resultado["antecedentes"], antecedentes_extensos.strip())
        self.assertGreater(len(resultado["antecedentes"]), 3000)
        self.assertEqual(resultado["alergias"], alergias_literales)
        self.assertEqual(resultado["observaciones"], observaciones_extensas.strip())
        self.assertGreater(len(resultado["observaciones"]), 2000)

    @patch("core.services.gemini_service.genai.Client")
    def test_historia_sin_signos_vitales_no_genera_mediciones_ni_rangos_y_conserva_negacion_literal(
        self,
        mock_client_cls,
    ):
        pdf_bytes = construir_pdf_digital_con_texto("Nota de ingreso sin toma de signos")
        payload_mock = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "Osteoartrosis generalizada.",
            "alergias": "Niega alergias medicamentosas o alimentarias.",
            "observaciones": "",
            "tiene_mediciones_signos_vitales": False,
            # Incluso si el modelo enviara una estructura vacía con puros None, debe quedar en None:
            "signos_vitales_medidos": {
                "presion_sistolica": None,
                "presion_diastolica": None,
                "frecuencia_cardiaca": None,
                "frecuencia_respiratoria": None,
                "temperatura": None,
                "saturacion_oxigeno": None,
                "peso": None,
                "detalle_medicion": "",
            },
            "tiene_referencias_explicitas": False,
            "rangos_vitales": None,
        }
        self._preparar_mock_cliente(
            mock_client_cls,
            [simular_respuesta_gemini(payload_mock)],
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}):
            resultado = extraer_historia_clinica_pdf(pdf_bytes)

        self.assertFalse(resultado["tiene_mediciones_signos_vitales"])
        self.assertIsNone(resultado["signos_vitales_medidos"])
        self.assertFalse(resultado["tiene_referencias_explicitas"])
        self.assertIsNone(resultado["rangos_vitales"])
        self.assertEqual(
            resultado["alergias"],
            "Niega alergias medicamentosas o alimentarias.",
        )
        self.assertEqual(resultado["observaciones"], "")

    @patch("core.services.gemini_service.genai.Client")
    def test_historia_con_mediciones_pero_sin_referencias_no_inventa_rangos(
        self,
        mock_client_cls,
    ):
        pdf_bytes = construir_pdf_digital_con_texto("Paciente con EPOC, TA 130/80, SpO2 91%")
        payload_mock = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "EPOC GOLD B e hipertensión arterial.",
            "alergias": "",
            "observaciones": "Control respiratorio estable.",
            "tiene_mediciones_signos_vitales": True,
            "signos_vitales_medidos": {
                "presion_sistolica": 130.0,
                "presion_diastolica": 80.0,
                "frecuencia_cardiaca": 76.0,
                "frecuencia_respiratoria": 19.0,
                "temperatura": 36.4,
                "saturacion_oxigeno": 91.0,
                "peso": 64.0,
                "detalle_medicion": "TA 130/80 mmHg, FC 76 lpm, FR 19 rpm, Temp 36.4 °C, SpO2 91%.",
            },
            "tiene_referencias_explicitas": False,
            # Incluso si viniera un objeto sin números, se descarta como None:
            "rangos_vitales": {
                "sistolica_min": None,
                "sistolica_max": None,
                "diastolica_min": None,
                "diastolica_max": None,
                "fc_min": None,
                "fc_max": None,
                "fr_min": None,
                "fr_max": None,
                "temp_min": None,
                "temp_max": None,
                "sat_min": None,
                "sat_max": None,
                "resumen_condicion": "Sin metas explícitas en el PDF.",
            },
        }
        self._preparar_mock_cliente(
            mock_client_cls,
            [
                simular_respuesta_gemini(payload_mock),
                simular_respuesta_gemini(payload_mock),
            ],
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}):
            resultado = extraer_historia_clinica_pdf(pdf_bytes)
            compat_rangos = analizar_pdf_geriatrico(pdf_bytes)

        self.assertTrue(resultado["tiene_mediciones_signos_vitales"])
        self.assertEqual(resultado["signos_vitales_medidos"]["saturacion_oxigeno"], 91.0)
        self.assertFalse(resultado["tiene_referencias_explicitas"])
        self.assertIsNone(resultado["rangos_vitales"])
        self.assertIsNone(compat_rangos)

    @patch("core.services.gemini_service.genai.Client")
    def test_historia_con_mediciones_y_referencias_explicitas_separa_ambos_y_es_compatible_con_evaluador(
        self,
        mock_client_cls,
    ):
        pdf_bytes = construir_pdf_digital_con_texto(
            "EPOC avanzado e ICC. Meta explicita: mantener SpO2 entre 88% y 92%, FC maxima 65 lpm."
        )
        payload_mock = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "EPOC severo e insuficiencia cardíaca congestiva.",
            "alergias": "Niega alergias.",
            "observaciones": "Oxígeno suplementario por cánula nasal a 1 L/min.",
            "tiene_mediciones_signos_vitales": True,
            "signos_vitales_medidos": {
                "presion_sistolica": 124.0,
                "presion_diastolica": 76.0,
                "frecuencia_cardiaca": 59.0,
                "frecuencia_respiratoria": 18.0,
                "temperatura": 36.5,
                "saturacion_oxigeno": 90.0,
                "peso": None,
                "detalle_medicion": "Ingreso: TA 124/76 mmHg, FC 59 lpm, SpO2 90%.",
            },
            "tiene_referencias_explicitas": True,
            "rangos_vitales": {
                "sistolica_min": None,
                "sistolica_max": None,
                "diastolica_min": None,
                "diastolica_max": None,
                "fc_min": None,
                "fc_max": 65.0,
                "fr_min": None,
                "fr_max": None,
                "temp_min": None,
                "temp_max": None,
                # Intencionalmente invertido para probar normalización min <= max cuando ambos existen:
                "sat_min": 92.0,
                "sat_max": 88.0,
                "resumen_condicion": "Meta explícita prescrita: mantener SpO2 88-92% y FC menor a 65 lpm.",
            },
        }
        self._preparar_mock_cliente(
            mock_client_cls,
            [
                simular_respuesta_gemini(payload_mock),
                simular_respuesta_gemini(payload_mock),
            ],
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}):
            resultado = extraer_historia_clinica_pdf(pdf_bytes)
            rangos_compat = analizar_pdf_geriatrico(pdf_bytes)

        self.assertTrue(resultado["tiene_mediciones_signos_vitales"])
        self.assertTrue(resultado["tiene_referencias_explicitas"])
        self.assertEqual(resultado["signos_vitales_medidos"]["frecuencia_cardiaca"], 59.0)

        rangos = resultado["rangos_vitales"]
        self.assertIsNotNone(rangos)
        self.assertEqual(rangos, rangos_compat)
        self.assertEqual(rangos["sat_min"], 88.0)
        self.assertEqual(rangos["sat_max"], 92.0)
        self.assertIsNone(rangos["fc_min"])
        self.assertEqual(rangos["fc_max"], 65.0)
        self.assertIsNone(rangos["sistolica_min"])
        self.assertIsNone(rangos["temp_max"])

        # Comprobación en memoria con evaluar_rangos_signos_vitales() SIN tocar el evaluador:
        paciente_mem = Pacientes(id_paciente=999, nombre="Test", apellido="EPOC")
        bitacora_mem = Bitacora(id_bitacora=1, id_paciente=paciente_mem)
        signo_normal = SignosVitales(
            id_bitacora=bitacora_mem,
            presion_sistolica="138",
            presion_diastolica="84",
            frecuencia_cardiaca="60",
            frecuencia_respiratoria="18",
            temperatura="36.6",
            saturacion_oxigeno="90",
        )
        signo_sobreoxigenado = SignosVitales(
            id_bitacora=bitacora_mem,
            presion_sistolica="138",
            presion_diastolica="84",
            frecuencia_cardiaca="78",
            frecuencia_respiratoria="18",
            temperatura="36.6",
            saturacion_oxigeno="98",
        )

        historia_con_metas = HistoriaClinicas(
            id_historia_clinica=10,
            id_paciente=paciente_mem,
            rangos_vitales_json=rangos,
        )
        with patch("core.serializers.HistoriaClinicas.objects") as mock_qs:
            mock_qs.filter.return_value.order_by.return_value.first.return_value = historia_con_metas
            self.assertIsNone(evaluar_rangos_signos_vitales(signo_normal))
            alerta = evaluar_rangos_signos_vitales(signo_sobreoxigenado)
            self.assertIsNotNone(alerta)
            self.assertIn("Frecuencia cardíaca elevada", alerta)
            self.assertIn("Saturación de oxígeno elevada", alerta)
            self.assertNotIn("Presión sistólica", alerta)

            # Si el PDF no tenía referencias (rangos_vitales_json = None), no genera alerta falsa:
            mock_qs.filter.return_value.order_by.return_value.first.return_value = None
            self.assertIsNone(evaluar_rangos_signos_vitales(signo_sobreoxigenado))

    @patch("core.services.gemini_service.genai.Client")
    def test_detecta_respuestas_incompletas_truncamientos_json_invalido_y_documento_ilegible(
        self,
        mock_client_cls,
    ):
        pdf_bytes = construir_pdf_paginas_en_blanco(num_paginas=1)
        payload_completo = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "HTA",
            "alergias": "",
            "observaciones": "",
            "tiene_mediciones_signos_vitales": False,
            "signos_vitales_medidos": None,
            "tiene_referencias_explicitas": False,
            "rangos_vitales": None,
        }

        casos_invalidos = [
            # 1. Truncado por MAX_TOKENS incluso si el payload pareciera JSON válido
            simular_respuesta_gemini(
                payload_completo,
                finish_reason=types.FinishReason.MAX_TOKENS,
            ),
            # 2. Bloqueado por SAFETY en finish_reason
            simular_respuesta_gemini(
                payload_completo,
                finish_reason=types.FinishReason.SAFETY,
            ),
            # 3. Sin candidatos
            simular_respuesta_gemini(None, sin_candidatos=True),
            # 4. Bloqueo en prompt_feedback
            simular_respuesta_gemini(payload_completo, block_reason="SAFETY"),
            # 5. Texto vacío con STOP
            simular_respuesta_gemini("", finish_reason=types.FinishReason.STOP),
            # 6. JSON truncado a mitad de cadena
            simular_respuesta_gemini(
                '{"documento_legible": true, "antecedentes": "Paciente con antecedente trunca',
                finish_reason=types.FinishReason.STOP,
            ),
            # 7. JSON parcial al que le faltan campos clínicos obligatorios
            simular_respuesta_gemini(
                {"documento_legible": True, "antecedentes": "Solo antecedentes sin demás campos"},
                finish_reason=types.FinishReason.STOP,
            ),
        ]

        self._preparar_mock_cliente(mock_client_cls, casos_invalidos)

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}):
            for idx in range(len(casos_invalidos)):
                with self.subTest(caso=idx), self.assertRaises(RespuestaGeminiIncompletaError):
                    extraer_historia_clinica_pdf(pdf_bytes)

        # 8. Documento escaneado en blanco / ilegible -> DocumentoClinicoIlegibleError
        self._preparar_mock_cliente(
            mock_client_cls,
            [
                simular_respuesta_gemini(
                    {
                        "documento_legible": False,
                        "motivo_ilegible": "Páginas escaneadas completamente en blanco.",
                        "antecedentes": "",
                        "alergias": "",
                        "observaciones": "",
                        "tiene_mediciones_signos_vitales": False,
                        "signos_vitales_medidos": None,
                        "tiene_referencias_explicitas": False,
                        "rangos_vitales": None,
                    }
                )
            ],
        )
        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-ficticia"}),
            self.assertRaises(DocumentoClinicoIlegibleError),
        ):
            extraer_historia_clinica_pdf(pdf_bytes)

    @patch("core.services.gemini_service.genai.Client")
    def test_modelos_reales_compatibilidad_thinking_y_fallback_ante_errores_api(
        self,
        mock_client_cls,
    ):
        # 1. Verificar configuración exacta: principal gemini-3.8-flash y alternativo gemini-3.5-flash-lite
        self.assertEqual(MODELO_GEMINI_PRINCIPAL, "gemini-3.8-flash")
        self.assertEqual(MODELOS_GEMINI_FALLBACK, ("gemini-3.5-flash-lite",))
        self.assertFalse(MODELO_GEMINI.startswith("gemini-2.5"))

        # 2. Verificar que thinking_level=LOW funciona en ambos modelos (y sin thinking_budget)
        for modelo_3x in ("gemini-3.8-flash", "gemini-3.5-flash-lite"):
            cfg = construir_thinking_config_compatible(modelo_3x)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.thinking_level, types.ThinkingLevel.LOW)
            self.assertIsNone(cfg.thinking_budget)

        self.assertIsNone(construir_thinking_config_compatible("gemini-2.5-flash"))

        # 3. Probar redirección automática desde GEMINI_MODEL=gemini-2.5-flash -> gemini-3.8-flash
        #    y fallback a gemini-3.5-flash-lite ante error 503
        pdf_bytes = construir_pdf_digital_con_texto("Prueba transicion 3.8 y fallback 3.5-lite")
        payload_ok = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "Hipotiroidismo.",
            "alergias": "Ninguna conocida.",
            "observaciones": "Sin novedades.",
            "tiene_mediciones_signos_vitales": False,
            "signos_vitales_medidos": None,
            "tiene_referencias_explicitas": False,
            "rangos_vitales": None,
        }

        err_503 = genai_errors.ServerError(503, {"error": {"message": "Service Unavailable"}})

        cliente_mock = self._preparar_mock_cliente(
            mock_client_cls,
            [
                err_503,  # falla gemini-3.8-flash
                simular_respuesta_gemini(payload_ok),  # responde gemini-3.5-flash-lite
            ],
        )

        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-key-ficticia", "GEMINI_MODEL": "gemini-2.5-flash"},
        ):
            resultado = extraer_historia_clinica_pdf(pdf_bytes)

        self.assertEqual(resultado["antecedentes"], "Hipotiroidismo.")
        self.assertEqual(cliente_mock.models.generate_content.call_count, 2)

        llamadas = cliente_mock.models.generate_content.call_args_list
        # Aunque GEMINI_MODEL tenía gemini-2.5-flash, usó gemini-3.8-flash y luego gemini-3.5-flash-lite
        self.assertEqual(llamadas[0].kwargs["model"], "gemini-3.8-flash")
        self.assertEqual(
            llamadas[0].kwargs["config"].thinking_config.thinking_level,
            types.ThinkingLevel.LOW,
        )
        self.assertIsNone(llamadas[0].kwargs["config"].thinking_config.thinking_budget)

        self.assertEqual(llamadas[1].kwargs["model"], "gemini-3.5-flash-lite")
        self.assertEqual(
            llamadas[1].kwargs["config"].thinking_config.thinking_level,
            types.ThinkingLevel.LOW,
        )
        self.assertIsNone(llamadas[1].kwargs["config"].thinking_config.thinking_budget)

        # 4. Reintento limpio sin thinking_config si un modelo rechaza thinking con HTTP 400
        err_400_thinking = genai_errors.ClientError(
            400,
            {"error": {"message": "Invalid value for thinking_config / thinking_level"}},
        )
        cliente_retry_thinking = self._preparar_mock_cliente(
            mock_client_cls,
            [
                err_400_thinking,
                simular_respuesta_gemini(payload_ok),
            ],
        )
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-key-ficticia", "GEMINI_MODEL": "gemini-3.8-flash"},
        ):
            res_retry = extraer_historia_clinica_pdf(pdf_bytes)
        self.assertEqual(res_retry["antecedentes"], "Hipotiroidismo.")
        self.assertEqual(cliente_retry_thinking.models.generate_content.call_count, 2)
        self.assertIsNone(
            cliente_retry_thinking.models.generate_content.call_args_list[1].kwargs["config"].thinking_config
        )

        # 5. Si falta GEMINI_API_KEY o si ambos modelos fallan, lanza RuntimeError controlado
        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": ""}),
            self.assertRaises(RuntimeError),
        ):
            extraer_historia_clinica_pdf(pdf_bytes)

        self._preparar_mock_cliente(
            mock_client_cls,
            [err_503, err_503],
        )
        with (
            patch.dict(
                "os.environ",
                {"GEMINI_API_KEY": "test-key-ficticia", "GEMINI_MODEL": "gemini-3.8-flash"},
            ),
            self.assertRaises(RuntimeError),
        ):
            extraer_historia_clinica_pdf(pdf_bytes)


class AusenciaRangosEndpointsCompatibilidadTests(BaseTablasHistoriaEnMemoriaTestCase):
    """
    Verifica en SQLite en memoria que la ausencia de rangos (rangos_vitales = None)
    del adaptador analizar_pdf_geriatrico() funciona sin errores en los endpoints actuales.
    """

    @patch("core.views.subir_documento")
    @patch("core.services.gemini_service.genai.Client")
    def test_ausencia_de_rangos_no_falla_en_guardar_historia_ni_en_endpoints_con_paciente_nuevo(
        self,
        mock_client_cls,
        mock_cloudinary,
    ):
        mock_cloudinary.return_value = {
            "secure_url": "https://res.cloudinary.com/test-cloud-local/raw/upload/sin_rangos.pdf",
            "public_id": "geriapp/documentos_historia_clinica/sin_rangos.pdf",
        }

        payload_sin_rangos = {
            "documento_legible": True,
            "motivo_ilegible": "",
            "antecedentes": "Artrosis de rodilla derecha.",
            "alergias": "Niega alergias.",
            "observaciones": "Control geriátrico sin metas numéricas personalizadas.",
            "tiene_mediciones_signos_vitales": True,
            "signos_vitales_medidos": {
                "presion_sistolica": 126.0,
                "presion_diastolica": 78.0,
                "frecuencia_cardiaca": 72.0,
                "frecuencia_respiratoria": 16.0,
                "temperatura": 36.5,
                "saturacion_oxigeno": 96.0,
                "peso": 65.0,
                "detalle_medicion": "TA 126/78 mmHg, FC 72 lpm.",
            },
            "tiene_referencias_explicitas": False,
            "rangos_vitales": None,
        }

        instancia_cliente = MagicMock()
        mock_client_cls.return_value = instancia_cliente
        instancia_cliente.models.generate_content.side_effect = [
            simular_respuesta_gemini(payload_sin_rangos),
            simular_respuesta_gemini(payload_sin_rangos),
        ]

        # Paciente nuevo en Sede Norte SIN fila previa en HistoriaClinicas
        paciente_sin_historia = self._crear_paciente(
            id_paciente=590,
            nombre="Roberto",
            apellido="SinHistoria",
            documento="2990",
            sede=self.sede_norte,
            habitacion_id=self.hab_norte.id_habitacion,
        )
        self.assertFalse(
            HistoriaClinicas.objects.filter(id_paciente=paciente_sin_historia).exists()
        )

        # 1. Función directa _guardar_rangos_historia_clinica con rangos_json=None en paciente sin historia
        historia_creada = _guardar_rangos_historia_clinica(paciente_sin_historia, None)
        self.assertIsNotNone(historia_creada.id_historia_clinica)
        self.assertEqual(historia_creada.antecedentes, "")
        self.assertIsNone(historia_creada.rangos_vitales_json)

        # Eliminar esa fila en memoria para probar también el flujo HTTP desde cero sin historia previa
        HistoriaClinicas.objects.filter(id_paciente=paciente_sin_historia).delete()

        pdf_bytes = construir_pdf_digital_con_texto("Historia sin rangos prescritos")
        cliente_admin = self._cliente_autenticado(self.admin_norte)

        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-key-ficticia", "GEMINI_MODEL": "gemini-3.8-flash"},
        ):
            # 2. POST /api/procesar-historia-pdf/<id_paciente>/ con paciente sin historia previa -> 200 OK
            archivo_1 = SimpleUploadedFile(
                "sin_rangos_1.pdf",
                pdf_bytes,
                content_type="application/pdf",
            )
            res_proc = cliente_admin.post(
                f"/api/procesar-historia-pdf/{paciente_sin_historia.id_paciente}/",
                {"archivo": archivo_1},
                format="multipart",
            )
            self.assertEqual(res_proc.status_code, status.HTTP_200_OK)
            self.assertIsNone(res_proc.json()["rangos_vitales_json"])

            # 3. POST /api/documentos_historia_clinica/ con ausencia de rangos -> 201 Created sin ia_error
            archivo_2 = SimpleUploadedFile(
                "sin_rangos_2.pdf",
                pdf_bytes,
                content_type="application/pdf",
            )
            res_doc = cliente_admin.post(
                "/api/documentos_historia_clinica/",
                {
                    "id_paciente": paciente_sin_historia.id_paciente,
                    "archivo": archivo_2,
                    "nombre_archivo": "sin_rangos_2.pdf",
                    "estado": True,
                },
                format="multipart",
            )
            self.assertEqual(res_doc.status_code, status.HTTP_201_CREATED)
            cuerpo_doc = res_doc.json()
            self.assertIsNone(cuerpo_doc["rangos_vitales_json"])
            self.assertNotIn("ia_error", cuerpo_doc)
