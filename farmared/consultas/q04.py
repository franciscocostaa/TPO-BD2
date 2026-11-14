"""q04 — Clientes con más de una receta registrada, con la cantidad.

Propósito: identificar a los clientes con tratamiento documentado por más de
una receta, indicando cuántas tienen. Cuentan las recetas en cualquier estado
("Vigente", "Completada", "Vencida"): la consulta pide recetas *registradas*,
y una receta vencida también quedó registrada.

Motor: MongoDB, colecciones `recetas` y `clientes`. La receta referencia al
cliente (`id_cliente`), así que el conteo se hace agrupando `recetas` y
recién después se traen los datos del cliente con `$lookup` (Clase 13,
pp. 21–24). Agrupar primero y unir después deja el `$lookup` con un documento
por cliente que cumple, en lugar de uno por receta.

Parámetros: `minimo` (opcional, por defecto 2): cantidad mínima de recetas,
inclusive. Con el valor por defecto, "más de una".

Retorna la lista ordenada por cantidad de recetas (de mayor a menor) y por id.
Cada elemento tiene `_id` (el id del cliente), `cantidad_recetas` y `cliente`
con el documento completo.

Uso desde la terminal:

    python -m farmared.consultas.q04
    python -m farmared.consultas.q04 --minimo 3
"""

import argparse
import sys

from farmared.conexiones import get_mongo
from farmared.salida import imprimir

MINIMO = 2


def pipeline(minimo: int = MINIMO) -> list[dict]:
    """Pipeline sobre `recetas` que cuenta por cliente y filtra por `minimo`."""
    return [
        {"$group": {"_id": "$id_cliente", "cantidad_recetas": {"$sum": 1}}},
        {"$match": {"cantidad_recetas": {"$gte": minimo}}},
        {"$lookup": {
            "from": "clientes",
            "localField": "_id",
            "foreignField": "_id",
            "as": "cliente",
        }},
        {"$set": {"cliente": {"$ifNull": [{"$first": "$cliente"}, None]}}},
        {"$sort": {"cantidad_recetas": -1, "_id": 1}},
    ]


def ejecutar(minimo: int = MINIMO) -> list[dict]:
    """Clientes con al menos `minimo` recetas registradas, con la cantidad."""
    return list(get_mongo().recetas.aggregate(pipeline(minimo)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q04",
                                     description="Clientes con más de una receta registrada")
    parser.add_argument("--minimo", type=int, default=MINIMO,
                        help=f"cantidad mínima de recetas, inclusive (por defecto {MINIMO})")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.minimo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
