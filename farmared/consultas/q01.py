"""q01 — Productos activos con todos los datos de su proveedor.

Propósito: listar el catálogo vigente (`activo: true`) junto con el proveedor
habitual de cada producto.

Motor: MongoDB, colecciones `productos` y `proveedores`. El producto guarda
una referencia (`id_proveedor`) en lugar de embeber al proveedor, porque un
proveedor abastece muchos productos y así sus datos no se repiten (Clase 13).
La relación se resuelve en la base con `$lookup` (Clase 13, pp. 21–24).

Se listan también los productos activos cuyo proveedor está dado de baja: el
producto sigue a la venta y el campo `proveedor.activo` lo indica.

Parámetros: ninguno.

Retorna una lista de documentos ordenada por `_id` del producto. Cada uno tiene
los campos del producto y, en lugar de `id_proveedor`, el documento completo
del proveedor en `proveedor` (`None` si la referencia no existe).

Uso desde la terminal:

    python -m farmared.consultas.q01
"""

import sys

from farmared.conexiones import get_mongo
from farmared.salida import imprimir

PIPELINE = [
    {"$match": {"activo": True}},
    {"$lookup": {
        "from": "proveedores",
        "localField": "id_proveedor",
        "foreignField": "_id",
        "as": "proveedor",
    }},
    # $lookup devuelve un arreglo; cada producto tiene un único proveedor.
    # Si la referencia no existiera, el producto se muestra igual con proveedor nulo.
    {"$set": {"proveedor": {"$ifNull": [{"$first": "$proveedor"}, None]}}},
    {"$unset": "id_proveedor"},
    {"$sort": {"_id": 1}},
]


def ejecutar() -> list[dict]:
    """Productos activos, cada uno con el documento de su proveedor en `proveedor`."""
    return list(get_mongo().productos.aggregate(PIPELINE))


def main() -> int:
    imprimir(ejecutar())
    return 0


if __name__ == "__main__":
    sys.exit(main())
