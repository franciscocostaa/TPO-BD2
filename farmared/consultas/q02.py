"""q02 — Ventas pendientes con el farmacéutico asignado y el total.

Propósito: listar las ventas en estado "Pendiente" (reservas o faltantes a
retirar) con el farmacéutico que las registró (nombre, apellido, matrícula y
sucursal) y el total.

Motor: MongoDB, colecciones `ventas`, `farmaceuticos` y `sucursales`. La venta
referencia al farmacéutico (`id_farmaceutico`) y el farmacéutico a su sucursal
(`id_sucursal`). Las dos relaciones se resuelven en la base con dos `$lookup`
encadenados (Clase 13, pp. 21–24). La sucursal es la del farmacéutico, como
pide la consigna.

Parámetros: ninguno.

Retorna una lista ordenada por fecha y por id. Cada elemento tiene `_id`,
`fecha`, `id_cliente`, `total` y `farmaceutico` con `_id`, `nombre`,
`apellido`, `matricula` y `sucursal` (`_id`, `nombre`, `ciudad`, `provincia`).

Uso desde la terminal:

    python -m farmared.consultas.q02
"""

import sys

from farmared.conexiones import get_mongo
from farmared.salida import imprimir

PIPELINE = [
    {"$match": {"estado": "Pendiente"}},
    {"$lookup": {
        "from": "farmaceuticos",
        "localField": "id_farmaceutico",
        "foreignField": "_id",
        "as": "farmaceutico",
    }},
    {"$set": {"farmaceutico": {"$first": "$farmaceutico"}}},
    {"$lookup": {
        "from": "sucursales",
        "localField": "farmaceutico.id_sucursal",
        "foreignField": "_id",
        "as": "sucursal",
    }},
    {"$project": {
        "fecha": 1,
        "id_cliente": 1,
        "total": 1,
        "farmaceutico": {
            "_id": "$farmaceutico._id",
            "nombre": "$farmaceutico.nombre",
            "apellido": "$farmaceutico.apellido",
            "matricula": "$farmaceutico.matricula",
            "sucursal": {"$ifNull": [{"$first": {"$map": {
                "input": "$sucursal",
                "as": "s",
                "in": {"_id": "$$s._id", "nombre": "$$s.nombre",
                       "ciudad": "$$s.ciudad", "provincia": "$$s.provincia"},
            }}}, None]},
        },
    }},
    {"$sort": {"fecha": 1, "_id": 1}},
]


def ejecutar() -> list[dict]:
    """Ventas "Pendiente" con su farmacéutico, la sucursal de este y el total."""
    return list(get_mongo().ventas.aggregate(PIPELINE))


def main() -> int:
    imprimir(ejecutar())
    return 0


if __name__ == "__main__":
    sys.exit(main())
