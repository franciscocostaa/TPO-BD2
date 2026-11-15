"""q03 — Historial completo de un cliente: ventas y recetas por fecha.

Propósito: dado un cliente, listar todas sus ventas (en cualquier estado) y
todas sus recetas en una única línea de tiempo, de la más antigua a la más
reciente. También funciona con clientes dados de baja: la baja es lógica y
su historial se conserva.

Motor: MongoDB, colecciones `clientes`, `ventas`, `recetas` y `productos`.
Ventas y recetas referencian al cliente (`id_cliente`). Las dos se combinan en
un único pipeline con `$unionWith`, que agrega al resultado los documentos de
otra colección, y se ordenan juntas en la base. Los filtros usan los índices
`ventas {id_cliente, fecha}` y `recetas {id_cliente}` que crea la carga.

El historial recorre cliente → receta → venta → producto: cada venta trae su
`id_receta` y sus ítems embebidos, y un `$lookup` a `productos` agrega a cada
ítem el nombre y la condición de venta del producto.

Parámetros: `id_cliente` (por ejemplo, "C001").

Retorna `{"cliente": <documento del cliente>, "historial": [...]}`. Cada
elemento del historial es el documento de la venta o de la receta con
`registro` ("venta" o "receta") y `fecha` (en las recetas, la fecha de
emisión). Los ítems de las ventas suman `producto` y `condicion_venta`. Si una venta y una receta son del mismo día, la receta va primero,
porque se emite antes de dispensarse.

Lanza `ErrorDeValidacion` si el cliente no existe.

Uso desde la terminal:

    python -m farmared.consultas.q03 C001
"""

import argparse
import sys

from farmared.conexiones import get_mongo
from farmared.errores import ErrorDeValidacion
from farmared.salida import imprimir


def pipeline(id_cliente: str) -> list[dict]:
    """Pipeline sobre `ventas` que suma las recetas del cliente y ordena todo por fecha."""
    return [
        {"$match": {"id_cliente": id_cliente}},
        # Productos de los ítems, en un solo $lookup por venta.
        {"$lookup": {
            "from": "productos",
            "localField": "items.id_producto",
            "foreignField": "_id",
            "as": "productos",
            "pipeline": [{"$project": {"nombre": 1, "condicion_venta": 1}}],
        }},
        {"$set": {
            "registro": "venta",
            "items": {"$map": {"input": "$items", "as": "item", "in": {"$mergeObjects": [
                "$$item",
                {"$let": {
                    "vars": {"p": {"$first": {"$filter": {
                        "input": "$productos", "as": "p", "cond": {"$eq": ["$$p._id", "$$item.id_producto"]}}}}},
                    "in": {"producto": "$$p.nombre", "condicion_venta": "$$p.condicion_venta"},
                }},
            ]}}},
        }},
        {"$unset": "productos"},
        {"$unionWith": {
            "coll": "recetas",
            "pipeline": [
                {"$match": {"id_cliente": id_cliente}},
                {"$set": {"registro": "receta", "fecha": "$fecha_emision"}},
                {"$unset": "fecha_emision"},
            ],
        }},
        {"$unset": "id_cliente"},
        # "receta" < "venta": en el mismo día, la receta queda antes.
        {"$sort": {"fecha": 1, "registro": 1, "_id": 1}},
    ]


def ejecutar(id_cliente: str) -> dict:
    """Cliente y su historial de ventas y recetas en orden cronológico."""
    db = get_mongo()
    cliente = db.clientes.find_one({"_id": id_cliente})
    if cliente is None:
        raise ErrorDeValidacion(f"no existe el cliente {id_cliente}")
    return {"cliente": cliente, "historial": list(db.ventas.aggregate(pipeline(id_cliente)))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q03",
                                     description="Historial de un cliente: ventas y recetas por fecha")
    parser.add_argument("id_cliente", help="id del cliente, por ejemplo C001")
    args = parser.parse_args(argv)
    try:
        resultado = ejecutar(args.id_cliente)
    except ErrorDeValidacion as error:
        print(f"✘ {error}")
        return 1
    imprimir(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
