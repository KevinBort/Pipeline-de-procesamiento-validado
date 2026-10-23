# Pipeline de extracción de entidades técnicas

Recibe un párrafo de texto técnico (una descripción de arquitectura, un log de error) y devuelve un **objeto validado** con las tecnologías mencionadas, el nivel de criticidad y un resumen técnico. Está construido con LangChain (LCEL) y Pydantic, y si el modelo responde con un formato inválido o incompleto, **reintenta automáticamente**.

```
Texto:  "Nuestra API en FastAPI consulta una caché en Redis y guarda los pedidos en PostgreSQL.
         En horas pico se agotan las conexiones y fallan las peticiones."

Salida: { "tecnologias": ["FastAPI", "Redis", "PostgreSQL"],
          "nivel_de_criticidad": "alta",
          "resumen_tecnico": "API con caché en Redis y persistencia en PostgreSQL; ..." }
```

## Cómo funciona

```
texto -> ChatPromptTemplate -> modelo.with_structured_output -> verificar() -> EntidadesTecnicas
                                      \________________ .with_retry() (hasta 3 intentos) ________________/
```

| Pieza | Qué hace |
|---|---|
| `schemas.py` | El contrato: `EntidadesTecnicas`, con `tecnologias` (lista no vacía), `nivel_de_criticidad` (enum: baja, media, alta) y `resumen_tecnico` |
| `PROMPT` (en `chain.py`) | `ChatPromptTemplate` con las instrucciones fijas y la variable `{texto}` |
| `with_structured_output(..., include_raw=True)` | El modelo responde con la forma del esquema y se conserva el mensaje original, para poder leer por qué terminó |
| `verificar()` | Rechaza respuestas **cortadas** por límite de tokens (`finish_reason` / `stop_reason`) y las que no cumplen el esquema |
| `.with_retry()` | Repite el modelo y la verificación, juntos, hasta 3 intentos |
| `process_text(text)` | Función asíncrona pública: ejecuta la cadena con `.ainvoke()` y deja logs del proceso |

## Requisitos

- Python 3.12 o superior
- Una API key de **OpenAI** o de **Anthropic** (solo para ejecutar `test_pipeline.py` con un modelo real)

## Instalación

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # y completa las variables
```

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `LLM_PROVIDER` | `openai` o `anthropic` |
| `LLM_MODEL` | Nombre del modelo, según la documentación del proveedor |
| `OPENAI_API_KEY` | Clave de OpenAI (si el proveedor es `openai`) |
| `ANTHROPIC_API_KEY` | Clave de Anthropic (si el proveedor es `anthropic`) |

El `.env` no se sube a Git (está en el `.gitignore`). Los comentarios del `.env` deben ir en líneas aparte: un comentario pegado a un valor vacío se interpreta como el valor.

## Cómo ejecutarlo

Uso desde código:

```python
import asyncio
import logging
from chain import process_text

logging.basicConfig(level=logging.INFO)  # para ver los logs de validación y reintentos

texto = "Nuestra API en FastAPI usa Redis y PostgreSQL. En horas pico fallan las peticiones."
resultado = asyncio.run(process_text(texto))
print(resultado.model_dump_json(indent=2))
```

Scripts de prueba:

```bash
python test_schemas.py     # el contrato, sin modelo (instantáneo)
python test_offline.py     # reintentos y verificación con un modelo simulado (unos segundos, sin API)
python test_pipeline.py    # 3 casos con un modelo REAL: necesita API key y consume una pequeña cantidad de crédito
```

## Pruebas

| Script | Qué comprueba | Resultado verificado |
|---|---|---|
| `test_schemas.py` | 1 objeto válido y 6 inválidos (criticidad fuera del enum, lista vacía, lista de textos en blanco, resumen vacío, campo faltante, tipo incorrecto) | Cada caso inválido falla con su mensaje |
| `test_offline.py` | Un modelo simulado con respuestas guionadas | **Caso 1:** falla dos veces y se recupera en la 3ª llamada. **Caso 2:** falla siempre y se rinde tras 3 llamadas con `RespuestaNoUtilizable`. **Caso 3:** acierta a la primera, con una sola llamada |
| `test_pipeline.py` | Un texto claro, un log de error y un **texto ambiguo** (prueba de estrés) contra un modelo real | Depende del modelo y del proveedor elegidos |

El texto ambiguo del tercer caso no menciona ninguna tecnología. Como el prompt prohíbe inventarlas, el modelo debería devolver una lista vacía, que el validador rechaza. Hay dos desenlaces válidos: que el modelo se recupere en un reintento, o que se agoten los 3 intentos y se lance `RespuestaNoUtilizable`. En ambos casos queda registrado en los logs.

## Ejemplo de salida

Forma del objeto que devuelve `process_text` (ejemplo ilustrativo):

```json
{
  "tecnologias": ["FastAPI", "Redis", "PostgreSQL"],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "API con caché en Redis y persistencia en PostgreSQL; cuello de botella en conexiones concurrentes."
}
```

## Estructura del repositorio

| Archivo | Contenido |
|---|---|
| `schemas.py` | Modelo Pydantic `EntidadesTecnicas` y el enum `NivelCriticidad` |
| `chain.py` | Prompt, modelo, cadena LCEL con reintentos y `process_text()` |
| `test_pipeline.py` | Prueba asíncrona con un modelo real |
| `test_offline.py` | Prueba de los reintentos, sin API |
| `test_schemas.py` | Prueba del contrato, sin modelo |
| `.env.example` | Plantilla de configuración, sin valores |
| `requirements.txt` | Dependencias |

## Decisiones de diseño

| Decisión | Motivo |
|---|---|
| **El reintento envuelve modelo + verificación**, no solo el modelo | `.with_retry()` solo reacciona a las excepciones de lo que envuelve. Si solo envolviera al modelo, que no lanza ningún error ante un formato inválido, el fallo de `verificar()` quedaría fuera y nunca se reintentaría. Se comprobó con un modelo simulado: con el reintento solo sobre el modelo, 1 llamada y falla; con el reintento sobre ambos, 3 llamadas y éxito |
| **`include_raw=True`** | Entrega la respuesta original junto con el objeto, lo que permite leer el motivo de finalización y detectar respuestas cortadas por límite de tokens |
| **Solo se reintentan los fallos de formato** (`RespuestaNoUtilizable`) | Los errores permanentes, como una API key inválida, no se arreglan repitiendo: fallan de inmediato. Los de red y límite de tasa los gestionan los SDK de cada proveedor |
| **La lista de tecnologías se valida con un `field_validator`**, no con `min_length` | `min_length` viajaría en el esquema que se envía al modelo y algunos modos de salida estructurada pueden no aceptar todas las restricciones. El validador de Python no viaja en el esquema y corre igual al recibir la respuesta |
| **`temperature=0`** | La extracción debe ser lo más consistente posible |
| **`ChatPromptTemplate` en lugar de f-strings** | El prompt es modular y LangChain gestiona sus variables |
| **`process_text` lanza `RespuestaNoUtilizable`** si se agotan los reintentos | Quien la llame decide qué hacer; no se devuelve un objeto a medias |
| **Logs con `logging`** | El módulo emite los mensajes (validación correcta, respuesta inválida, respuesta cortada, error final) y el script que lo usa decide cuáles ver |
| **Las dependencias del modelo se cargan según el proveedor** | Solo hace falta tener instalado el paquete del proveedor que se usa |

## Limitaciones

- **El comportamiento con un modelo real depende del proveedor y del modelo.** La lógica de verificación y reintentos se comprueba con un modelo simulado (`test_offline.py`); `test_pipeline.py` es la prueba contra un modelo real.
- **Reintentar el mismo prompt con `temperature=0` puede repetir el mismo resultado.** El reintento sirve sobre todo para fallos esporádicos de formato.
- **El nombre de las tecnologías no se normaliza.** `postgres` y `PostgreSQL` salen como dos textos distintos, y los duplicados no se eliminan.
- **Algunos modelos pueden no aceptar el parámetro `temperature`.** En ese caso, hay que quitarlo en `crear_modelo()`.
- **El validador no comprueba** que las tecnologías aparezcan realmente en el texto: eso lo pide el prompt, pero no se verifica por código.# Pipeline-de-procesamiento-validado
