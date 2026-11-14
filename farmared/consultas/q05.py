"""q05 — Farmacéuticos activos y sus ventas de los últimos 60 días.

Propósito: medir la actividad reciente de cada farmacéutico en funciones. Se
excluyen las ventas anuladas, y **los farmacéuticos con cero ventas aparecen
igual**: son justamente los que interesa ver.

Motor: MongoDB, colecciones `farmaceuticos` y `ventas`. El pipeline arranca en
`farmaceuticos`, no en `ventas`: agrupar las ventas por farmacéutico solo
devolvería a los que vendieron algo, y la consulta pide también a los que no.
`$lookup` funciona como un *left outer join* (Clase 13, pp. 21–24), así que el
que no tiene ventas queda con un arreglo vacío y `$size` le da 0.

La ventana es `[hoy - dias, hoy]`, inclusive en los dos extremos. El
`$lookup` lleva un `pipeline` propio que filtra por fecha y estado del lado de
`ventas`, de modo que se traen solo las ventas de la ventana y no todas las del
farmacéutico; usa el índice `ventas {id_farmaceutico, fecha}` que crea la carga.

Parámetros: `hoy` (opcional): por defecto, la fecha del sistema. Se puede fijar
para que las pruebas den siempre el mismo resultado. `dias` (opcional, por
defecto 60): largo de la ventana.

Retorna la lista de farmacéuticos activos ordenada por cantidad de ventas (de
mayor a menor) y por id. Cada uno trae sus campos más `ventas` con la cantidad.

Uso desde la terminal:

    python -m farmared.consultas.q05
    python -m farmared.consultas.q05 --hoy 2026-11-14
    python -m farmared.consultas.q05 --dias 30
"""

import argparse
import sys
from datetime import date, timedelta

from farmared import fechas
from farmared.conexiones import get_mongo
from farmared.salida import imprimir

DIAS = 60


def pipeline(hoy: date, dias: int = DIAS) -> list[dict]:
    """Pipeline sobre `farmaceuticos` que cuenta las ventas no anuladas de la ventana."""
    desde = fechas.a_mongo(hoy - timedelta(days=dias))
    hasta = fechas.a_mongo(hoy)
    return [
        {"$match": {"activo": True}},
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_farmaceutico",
            "as": "recientes",
            "pipeline": [
                {"$match": {"estado": {"$ne": "Anulada"}, "fecha": {"$gte": desde, "$lte": hasta}}},
                # Solo hace falta contarlas, no traerlas enteras.
                {"$project": {"_id": 1}},
            ],
        }},
        {"$set": {"ventas": {"$size": "$recientes"}}},
        {"$unset": "recientes"},
        {"$sort": {"ventas": -1, "_id": 1}},
    ]


def ejecutar(hoy: date | None = None, dias: int = DIAS) -> list[dict]:
    """Farmacéuticos activos con su cantidad de ventas no anuladas de los últimos `dias`."""
    return list(get_mongo().farmaceuticos.aggregate(pipeline(hoy or fechas.hoy(), dias)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q05",
                                     description="Farmacéuticos activos y sus ventas de los últimos 60 días")
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia AAAA-MM-DD (por defecto, hoy)")
    parser.add_argument("--dias", type=int, default=DIAS, help=f"largo de la ventana (por defecto {DIAS})")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.hoy, args.dias))
    return 0


if __name__ == "__main__":
    sys.exit(main())
