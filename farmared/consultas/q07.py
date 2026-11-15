"""q07 — Top 5 de productos más vendidos en unidades.

Propósito: ranking de los productos que más unidades vendieron, contando solo
ventas "Completada": una venta "Pendiente" todavía puede no concretarse y una
"Anulada" no se vendió.

Motor: MongoDB, colecciones `ventas` y `productos`. Los ítems están embebidos
en la venta (`items`), así que las unidades vendidas salen de la misma
colección: `$unwind` abre un documento por ítem y `$group` suma las cantidades
por producto (Clase 13). El `$lookup` con `productos` va **después** del
corte, para unir solo los productos del ranking y no todo el catálogo.

El puesto se calcula con `$rank` sobre las unidades, como `RANK()` en SQL:
productos con las mismas unidades comparten el puesto. Se devuelven los de
puesto `<= limite`, así que **un empate en el corte entra completo** y el top 5
puede traer más de cinco productos. Cortar en cinco exactos obligaría a dejar
afuera a uno de los empatados con un criterio arbitrario, como el id. Dentro
del mismo puesto se ordena por id, para que la salida sea siempre la misma.

Parámetros: `limite` (opcional, por defecto 5): último puesto incluido.

Retorna la lista ordenada de mayor a menor. Cada elemento tiene `_id` (el id
del producto), `puesto`, `unidades` (total vendido), `ventas` (en cuántas
ventas distintas apareció) y `producto` con el documento completo.

Uso desde la terminal:

    python -m farmared.consultas.q07
    python -m farmared.consultas.q07 --limite 10
"""

import argparse
import sys

from farmared.conexiones import get_mongo
from farmared.salida import imprimir

LIMITE = 5


def pipeline(limite: int = LIMITE) -> list[dict]:
    """Pipeline sobre `ventas` que suma unidades por producto y corta en `limite`."""
    return [
        {"$match": {"estado": "Completada"}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.id_producto",
            "unidades": {"$sum": "$items.cantidad"},
            # Una venta puede repetir el producto en dos ítems: se cuenta una vez.
            "ventas": {"$addToSet": "$_id"},
        }},
        {"$set": {"ventas": {"$size": "$ventas"}}},
        # Puesto con empates: 10, 10, 8 → 1, 1, 3.
        {"$setWindowFields": {"sortBy": {"unidades": -1}, "output": {"puesto": {"$rank": {}}}}},
        {"$match": {"puesto": {"$lte": limite}}},
        {"$sort": {"puesto": 1, "_id": 1}},
        {"$lookup": {
            "from": "productos",
            "localField": "_id",
            "foreignField": "_id",
            "as": "producto",
        }},
        {"$set": {"producto": {"$ifNull": [{"$first": "$producto"}, None]}}},
    ]


def ejecutar(limite: int = LIMITE) -> list[dict]:
    """Productos hasta el puesto `limite` en unidades vendidas en ventas "Completada", con empates."""
    return list(get_mongo().ventas.aggregate(pipeline(limite)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q07",
                                     description="Top 5 de productos más vendidos en unidades")
    parser.add_argument("--limite", type=int, default=LIMITE,
                        help=f"último puesto incluido; los empatados entran todos (por defecto {LIMITE})")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.limite))
    return 0


if __name__ == "__main__":
    sys.exit(main())
