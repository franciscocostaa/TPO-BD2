"""q07 — Top 5 de productos más vendidos en unidades.

Propósito: ranking de los productos que más unidades vendieron, contando solo
ventas "Completada": una venta "Pendiente" todavía puede no concretarse y una
"Anulada" no se vendió.

Motor: MongoDB, colecciones `ventas` y `productos`. Los ítems están embebidos
en la venta (`items`), así que las unidades vendidas salen de la misma
colección: `$unwind` abre un documento por ítem y `$group` suma las cantidades
por producto (Clase 13). El `$lookup` con `productos` va **después** del
`$limit`, para unir cinco documentos y no todo el catálogo.

El ranking ordena por unidades y desempata por id de producto. El desempate es
arbitrario, pero hace que el resultado sea siempre el mismo: sin él, dos
productos con las mismas unidades podrían entrar y salir del top 5 entre dos
ejecuciones iguales.

Parámetros: `limite` (opcional, por defecto 5): cuántos productos devolver.

Retorna la lista ordenada de mayor a menor. Cada elemento tiene `_id` (el id
del producto), `unidades` (total vendido), `ventas` (en cuántas ventas
distintas apareció) y `producto` con el documento completo.

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
        {"$sort": {"unidades": -1, "_id": 1}},
        {"$limit": limite},
        {"$lookup": {
            "from": "productos",
            "localField": "_id",
            "foreignField": "_id",
            "as": "producto",
        }},
        {"$set": {"producto": {"$ifNull": [{"$first": "$producto"}, None]}}},
    ]


def ejecutar(limite: int = LIMITE) -> list[dict]:
    """Los `limite` productos con más unidades vendidas en ventas "Completada"."""
    return list(get_mongo().ventas.aggregate(pipeline(limite)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q07",
                                     description="Top 5 de productos más vendidos en unidades")
    parser.add_argument("--limite", type=int, default=LIMITE,
                        help=f"cuántos productos devolver (por defecto {LIMITE})")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.limite))
    return 0


if __name__ == "__main__":
    sys.exit(main())
