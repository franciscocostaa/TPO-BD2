"""q06 — Recetas prolongadas vigentes con la próxima dispensa vencida.

Propósito: listar las recetas de tipo "Tratamiento prolongado" en estado
"Vigente" cuya `proxima_dispensa` es anterior a hoy, con los datos del
cliente. Sirve para detectar pacientes que no volvieron a retirar su
medicación. Una próxima dispensa igual a hoy no está atrasada.

Motor: MongoDB, colecciones `recetas` y `clientes`. La receta referencia al
cliente (`id_cliente`) y se combina con `$lookup` (Clase 13, pp. 21–24). El
filtro usa el índice `recetas {tipo, estado, proxima_dispensa}` que crea la
carga.

Parámetros: `hoy` (opcional): por defecto, la fecha del sistema. Se puede fijar
para que las pruebas den siempre el mismo resultado.

Retorna la lista de recetas ordenada por `proxima_dispensa` (la más atrasada
primero). Cada una tiene sus campos, `dias_de_atraso` y, en lugar de
`id_cliente`, el documento del cliente en `cliente`.

Uso desde la terminal:

    python -m farmared.consultas.q06
    python -m farmared.consultas.q06 --hoy 2026-10-13
"""

import argparse
import sys
from datetime import date

from farmared import fechas
from farmared.conexiones import get_mongo
from farmared.salida import imprimir


def pipeline(hoy: date) -> list[dict]:
    hoy_mongo = fechas.a_mongo(hoy)
    return [
        {"$match": {
            "tipo": "Tratamiento prolongado",
            "estado": "Vigente",
            "proxima_dispensa": {"$lt": hoy_mongo},
        }},
        {"$lookup": {
            "from": "clientes",
            "localField": "id_cliente",
            "foreignField": "_id",
            "as": "cliente",
        }},
        {"$set": {
            "cliente": {"$ifNull": [{"$first": "$cliente"}, None]},
            "dias_de_atraso": {"$dateDiff": {
                "startDate": "$proxima_dispensa", "endDate": hoy_mongo, "unit": "day",
            }},
        }},
        {"$unset": "id_cliente"},
        {"$sort": {"proxima_dispensa": 1, "_id": 1}},
    ]


def ejecutar(hoy: date | None = None) -> list[dict]:
    """Recetas prolongadas vigentes con `proxima_dispensa < hoy`, con su cliente."""
    return list(get_mongo().recetas.aggregate(pipeline(hoy or fechas.hoy())))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q06",
                                     description="Recetas prolongadas vigentes con la próxima dispensa vencida")
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia AAAA-MM-DD (por defecto, hoy)")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.hoy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
