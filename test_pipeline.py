"""Prueba con un modelo REAL (necesita API key en .env). Cuesta unos centavos."""

import asyncio
import logging

from chain import process_text

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
)

CASOS = {
    "Arquitectura (texto claro)": (
        "Nuestra API en FastAPI consulta una caché en Redis y guarda los pedidos en "
        "PostgreSQL. En horas pico el pool de conexiones a PostgreSQL se agota y las "
        "peticiones empiezan a fallar con timeouts."
    ),
    "Log de error": (
        "ERROR 2026-03-14 03:12:08 sqlalchemy.exc.OperationalError: connection to server "
        "db-prod failed: FATAL: remaining connection slots are reserved. "
        "Worker gunicorn reiniciado 5 veces en 10 minutos."
    ),
    "Texto ambiguo (prueba de estrés)": (
        "Anda lento a veces y no sabemos por qué. Alguien dijo que había que mirarlo."
    ),
}


async def main() -> None:
    for nombre, texto in CASOS.items():
        print(f"\n=== {nombre} ===")
        try:
            resultado = await process_text(texto)
            print(resultado.model_dump_json(indent=2))
        except Exception as e:  # el script de prueba nunca debe caerse
            print(f"SIN RESULTADO: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
