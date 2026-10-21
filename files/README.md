# Pipeline de extracción de entidades técnicas

Recibe un párrafo de texto técnico (descripción de arquitectura, log de error) y
devuelve un objeto **validado** con las tecnologías mencionadas, el nivel de
criticidad y un resumen técnico. Construido con LangChain (LCEL) y Pydantic.

```
texto -> ChatPromptTemplate -> modelo.with_structured_output -> verificación -> EntidadesTecnicas
                                        \_____________ .with_retry() _____________/
```

## Estructura

| Archivo | Contenido |
|---|---|
| `schemas.py` | Contrato Pydantic: `EntidadesTecnicas` y el enum `NivelCriticidad` |
| `chain.py` | Prompt, modelo, cadena LCEL con reintentos y `process_text()` |
| `test_pipeline.py` | Prueba asíncrona con un modelo real (3 casos, incluido uno ambiguo) |
| `test_offline.py` | Prueba de la lógica de reintentos sin API, con un modelo falso |
| `test_schemas.py` | Prueba del contrato Pydantic, sin modelo |

## Instalación

Requiere Python 3.12 o superior.

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
| `LLM_MODEL` | Nombre del modelo a usar |
| `OPENAI_API_KEY` | Clave de OpenAI (si el proveedor es `openai`) |
| `ANTHROPIC_API_KEY` | Clave de Anthropic (si el proveedor es `anthropic`) |

## Cómo ejecutarlo

```bash
python test_schemas.py     # contrato, sin API
python test_offline.py     # reintentos, sin API
python test_pipeline.py    # modelo real (usa la API key y tiene un costo mínimo)
```

Uso desde código:

```python
import asyncio
from chain import process_text

resultado = asyncio.run(process_text("Nuestra API en FastAPI usa Redis y PostgreSQL..."))
print(resultado.model_dump_json(indent=2))
```

## Ejemplo de salida

Forma del objeto que devuelve el pipeline (ejemplo ilustrativo):

```json
{
  "tecnologias": ["FastAPI", "Redis", "PostgreSQL"],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "API con caché en Redis y persistencia en PostgreSQL; cuello de botella en conexiones concurrentes."
}
```

## Decisiones de diseño

- **Salida estructurada:** `model.with_structured_output(EntidadesTecnicas, include_raw=True)`.
  Con `include_raw=True` se conserva el mensaje original del modelo, lo que permite
  leer el `finish_reason` y detectar respuestas cortadas por límite de tokens.
- **Verificación explícita:** la función `verificar()` rechaza respuestas cortadas
  (`finish_reason` = `length` / `max_tokens`) o que no cumplan el esquema.
- **Reintento:** `.with_retry()` envuelve modelo + verificación, de modo que un
  fallo de formato vuelve a llamar al modelo (hasta 3 intentos, con espera
  exponencial). Solo se reintentan los fallos de formato: los errores permanentes
  (por ejemplo, una API key inválida) fallan de inmediato. Los errores de red y de
  límite de tasa los reintentan por defecto los SDKs de cada proveedor.
- **Restricciones en Python:** que la lista de tecnologías no esté vacía se valida
  con un `field_validator` y no con `min_length`, para no incluir esa restricción en
  el esquema que se envía al modelo (algunos proveedores pueden no aceptar todas las
  palabras clave de un esquema).
- **Temperatura 0:** la extracción debe ser lo más consistente posible. Si tu modelo
  rechaza el parámetro `temperature` (algunos modelos de razonamiento lo hacen),
  quítalo en `crear_modelo()`.
- **Prueba de estrés:** el texto ambiguo del script de prueba no menciona ninguna
  tecnología. Como el prompt prohíbe inventarlas, el modelo debería devolver una
  lista vacía, y el validador la rechaza. El resultado puede ser que el modelo se
  recupere en un reintento o que se agoten los intentos y se lance
  `RespuestaNoUtilizable`: ambos desenlaces son válidos y quedan registrados en los logs.
