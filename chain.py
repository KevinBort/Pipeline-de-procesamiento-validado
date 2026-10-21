"""Pipeline de extracción de entidades técnicas con LangChain (LCEL).

Flujo:  texto -> prompt -> modelo (salida estructurada) -> verificación -> objeto validado
Si la respuesta está cortada o no cumple el esquema, se reintenta automáticamente.
"""

import logging
import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda

from schemas import EntidadesTecnicas

load_dotenv()
logger = logging.getLogger(__name__)


class RespuestaNoUtilizable(Exception):
    """La respuesta del modelo está cortada o no cumple el esquema."""


# ----------------------------------------------------------------------
# 1. Modelo: OpenAI o Anthropic, según el .env
# ----------------------------------------------------------------------
def crear_modelo():
    proveedor = os.getenv("LLM_PROVIDER", "openai").lower()
    nombre = os.getenv("LLM_MODEL")
    if not nombre:
        raise ValueError("Falta LLM_MODEL en el archivo .env")

    if proveedor == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=nombre, temperature=0, max_tokens=1024, timeout=30)
    if proveedor == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=nombre, temperature=0, max_tokens=1024, timeout=30)
    raise ValueError(f"LLM_PROVIDER inválido: {proveedor!r} (usa 'openai' o 'anthropic')")


# ----------------------------------------------------------------------
# 2. Prompt template: instrucciones fijas + variable {texto}
# ----------------------------------------------------------------------
PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Eres un analista técnico. Extrae información del texto que te dará el usuario.\n"
            "Reglas:\n"
            "- tecnologias: solo tecnologías mencionadas explícitamente en el texto. "
            "No inventes ninguna.\n"
            "- nivel_de_criticidad: 'alta' si hay caídas, pérdida de datos o riesgo de "
            "seguridad; 'media' si hay degradación de rendimiento o fallos intermitentes; "
            "'baja' en cualquier otro caso.\n"
            "- resumen_tecnico: una o dos frases, en español.",
        ),
        ("human", "Texto a analizar:\n\n{texto}"),
    ]
)


# ----------------------------------------------------------------------
# 3. Verificación: ¿la respuesta está completa y es válida?
# ----------------------------------------------------------------------
def verificar(resultado: dict) -> EntidadesTecnicas:
    """Recibe {'raw', 'parsed', 'parsing_error'} y devuelve el objeto o lanza error."""
    metadatos = resultado["raw"].response_metadata
    motivo = metadatos.get("finish_reason") or metadatos.get("stop_reason")

    if motivo in ("length", "max_tokens"):
        logger.warning("Respuesta cortada por límite de tokens (%s)", motivo)
        raise RespuestaNoUtilizable(f"respuesta cortada ({motivo})")

    if resultado["parsing_error"] is not None or resultado["parsed"] is None:
        logger.warning("Respuesta inválida: %s", resultado["parsing_error"])
        raise RespuestaNoUtilizable(f"no cumple el esquema: {resultado['parsing_error']}")

    logger.info("Validación OK (finish_reason=%s)", motivo)
    return resultado["parsed"]


# ----------------------------------------------------------------------
# 4. Cadena LCEL con reintentos
# ----------------------------------------------------------------------
def construir_cadena(model) -> Runnable:
    estructurado = model.with_structured_output(EntidadesTecnicas, include_raw=True)

    # El reintento envuelve modelo + verificación: así un fallo de formato
    # vuelve a llamar al modelo (si solo envolviera al modelo, no se enteraría).
    extractor = (estructurado | RunnableLambda(verificar)).with_retry(
        retry_if_exception_type=(RespuestaNoUtilizable,),
        stop_after_attempt=3,
    )
    return PROMPT | extractor


@lru_cache(maxsize=1)
def _cadena_por_defecto() -> Runnable:
    return construir_cadena(crear_modelo())


# ----------------------------------------------------------------------
# 5. Función pública asíncrona
# ----------------------------------------------------------------------
async def process_text(text: str, cadena: Runnable | None = None) -> EntidadesTecnicas:
    """Devuelve las entidades validadas.

    Lanza RespuestaNoUtilizable si, tras los reintentos, no hay respuesta válida.
    """
    if cadena is None:
        cadena = _cadena_por_defecto()

    logger.info("Procesando texto de %d caracteres", len(text))
    try:
        resultado = await cadena.ainvoke({"texto": text})
    except RespuestaNoUtilizable as e:
        logger.error("Sin resultado válido tras los reintentos: %s", e)
        raise

    logger.info("Resultado: %s", resultado.model_dump_json())
    return resultado
