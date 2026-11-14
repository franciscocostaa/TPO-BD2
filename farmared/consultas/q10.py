"""q10 — Clientes atendidos en una sucursal, a través del farmacéutico.

Propósito: dada una sucursal, listar todos los clientes que compraron en ella.
El vínculo se recorre **por el farmacéutico que registró la venta**, como pide
la consulta, y se incluyen los farmacéuticos dados de baja: una venta vieja
sigue habiendo ocurrido en esa sucursal aunque quien la registró ya no trabaje.

Motor: MongoDB, colecciones `farmaceuticos`, `ventas` y `clientes`. El pipeline
arranca en `farmaceuticos` filtrando por `id_sucursal` (índice que crea la
carga) y de ahí salta a las ventas de cada uno con `$lookup`, que funciona como
un *left outer join* (Clase 13, pp. 21–24). Recién después agrupa por cliente,
así cada uno aparece una sola vez aunque lo hayan atendido varios
farmacéuticos.

El recorrido no usa `ventas.id_sucursal`, que la venta guarda copiada del
farmacéutico: la consulta pide explícitamente pasar por el farmacéutico, y así
el resultado es el mismo incluso si un farmacéutico cambió de sucursal.

Parámetros: `id_sucursal` (por ejemplo, "S001").

Retorna `{"sucursal": <documento>, "clientes": [...]}`. Cada cliente trae su
documento completo en `cliente`, `ventas` (cuántas le registraron en esa
sucursal), `ultima_compra` y `farmaceuticos` (quiénes lo atendieron).

Lanza `ErrorDeValidacion` si la sucursal no existe.

Uso desde la terminal:

    python -m farmared.consultas.q10 S001
"""

import argparse
import sys

from farmared.conexiones import get_mongo
from farmared.errores import ErrorDeValidacion
from farmared.salida import imprimir


def pipeline(id_sucursal: str) -> list[dict]:
    """Pipeline sobre `farmaceuticos` que llega a los clientes por sus ventas."""
    return [
        # Activos o no: la consulta pide incluir a los dados de baja.
        {"$match": {"id_sucursal": id_sucursal}},
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_farmaceutico",
            "as": "ventas",
            "pipeline": [{"$project": {"id_cliente": 1, "fecha": 1, "estado": 1}}],
        }},
        # Un farmacéutico sin ventas no aporta clientes y acá desaparece.
        {"$unwind": "$ventas"},
        {"$group": {
            "_id": "$ventas.id_cliente",
            "ventas": {"$sum": 1},
            "ultima_compra": {"$max": "$ventas.fecha"},
            "farmaceuticos": {"$addToSet": "$_id"},
        }},
        {"$set": {"farmaceuticos": {"$sortArray": {"input": "$farmaceuticos", "sortBy": 1}}}},
        {"$lookup": {
            "from": "clientes",
            "localField": "_id",
            "foreignField": "_id",
            "as": "cliente",
        }},
        {"$set": {"cliente": {"$ifNull": [{"$first": "$cliente"}, None]}}},
        {"$sort": {"_id": 1}},
    ]


def ejecutar(id_sucursal: str) -> dict:
    """Sucursal y los clientes atendidos en ella, vía el farmacéutico de cada venta."""
    db = get_mongo()
    sucursal = db.sucursales.find_one({"_id": id_sucursal})
    if sucursal is None:
        raise ErrorDeValidacion(f"no existe la sucursal {id_sucursal}")
    return {"sucursal": sucursal, "clientes": list(db.farmaceuticos.aggregate(pipeline(id_sucursal)))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q10",
                                     description="Clientes atendidos en una sucursal")
    parser.add_argument("id_sucursal", help="id de la sucursal, por ejemplo S001")
    args = parser.parse_args(argv)
    try:
        resultado = ejecutar(args.id_sucursal)
    except ErrorDeValidacion as error:
        print(f"✘ {error}")
        return 1
    imprimir(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
