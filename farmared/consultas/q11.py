"""q11 — Vista agregada: ingresos por farmacéutico en el mes actual.

Propósito: cuánto facturó cada farmacéutico en el mes corriente, contando solo
ventas "Completada". Se expone como **vista** (`ingresos_farmaceutico_mes`),
así el reporte se consulta como si fuera una colección y la definición del
cálculo vive en la base, no repetida en cada cliente.

Motor: MongoDB, colecciones `ventas` y `farmaceuticos`. La vista es un pipeline
guardado sobre `ventas`: no almacena datos y se recalcula en cada lectura
(Clase 13). Eso es justamente lo que hace falta acá, porque "el mes actual"
cambia solo.

El mes se calcula dentro de la vista con `$$NOW`, la fecha del servidor al
momento de la consulta, truncada al mes con `$dateTrunc`. Una vista no puede
recibir parámetros, así que no hay otra forma de que "mes actual" siga siendo
el mes actual mañana.

`$$NOW` viene en UTC y la carga guarda cada fecha a las 00:00 UTC del día
(sección 2.1 del informe), así que los dos lados de la comparación están en la
misma referencia. El borde se corre tres horas: entre las 21:00 y las 00:00 del
último día del mes en hora argentina, el servidor ya considera el mes siguiente.

Para las pruebas, `ejecutar(hoy=...)` no usa la vista: corre el mismo pipeline
con el mes fijo, de modo que el resultado sea reproducible. Las dos variantes
comparten las etapas de agregación, así que no pueden quedar desalineadas.

Parámetros: `hoy` (opcional): mes de referencia. Sin este parámetro se lee la
vista; con él se corre el pipeline equivalente sobre `ventas`.
`recrear` (opcional): vuelve a escribir la definición de la vista.

Retorna la lista ordenada por ingresos (de mayor a menor) y por id. Cada
elemento tiene `_id` (el id del farmacéutico), `ingresos`, `ventas` y
`farmaceutico` con el documento completo.

Uso desde la terminal:

    python -m farmared.consultas.q11
    python -m farmared.consultas.q11 --hoy 2026-11-14
    python -m farmared.consultas.q11 --recrear
"""

import argparse
import sys
from datetime import date

from pymongo.errors import CollectionInvalid

from farmared import fechas
from farmared.conexiones import get_mongo
from farmared.salida import imprimir

VISTA = "ingresos_farmaceutico_mes"


def _agregacion() -> list[dict]:
    """Etapas comunes: total por farmacéutico y sus datos. Las comparte la vista."""
    return [
        {"$group": {
            "_id": "$id_farmaceutico",
            "ingresos": {"$sum": "$total"},
            "ventas": {"$sum": 1},
        }},
        {"$lookup": {
            "from": "farmaceuticos",
            "localField": "_id",
            "foreignField": "_id",
            "as": "farmaceutico",
        }},
        {"$set": {"farmaceutico": {"$ifNull": [{"$first": "$farmaceutico"}, None]}}},
        {"$sort": {"ingresos": -1, "_id": 1}},
    ]


def pipeline_vista() -> list[dict]:
    """Definición de la vista: el mes sale de `$$NOW` en cada lectura."""
    inicio = {"$dateTrunc": {"date": "$$NOW", "unit": "month"}}
    siguiente = {"$dateAdd": {"startDate": inicio, "unit": "month", "amount": 1}}
    return [
        {"$match": {"estado": "Completada", "$expr": {"$and": [
            {"$gte": ["$fecha", inicio]},
            {"$lt": ["$fecha", siguiente]},
        ]}}},
        *_agregacion(),
    ]


def pipeline(hoy: date) -> list[dict]:
    """El mismo cálculo con el mes de `hoy` fijo, para pruebas reproducibles."""
    desde = fechas.a_mongo(hoy.replace(day=1))
    # Mes siguiente, sin depender de cuántos días tiene el actual.
    hasta = fechas.a_mongo(date(hoy.year + hoy.month // 12, hoy.month % 12 + 1, 1))
    return [
        # Sin `$expr`: este filtro de rango sí usa el índice `ventas {fecha}`.
        {"$match": {"estado": "Completada", "fecha": {"$gte": desde, "$lt": hasta}}},
        *_agregacion(),
    ]


def crear_vista(recrear: bool = False) -> bool:
    """Crea la vista si falta. Con `recrear`, reescribe su definición. True si la tocó."""
    db = get_mongo()
    if recrear and VISTA in db.list_collection_names():
        db.command("collMod", VISTA, viewOn="ventas", pipeline=pipeline_vista())
        return True
    try:
        db.create_collection(VISTA, viewOn="ventas", pipeline=pipeline_vista())
    except CollectionInvalid:
        return False
    return True


def ejecutar(hoy: date | None = None, recrear: bool = False) -> list[dict]:
    """Ingresos por farmacéutico del mes actual, leídos de la vista."""
    db = get_mongo()
    if hoy is not None:
        return list(db.ventas.aggregate(pipeline(hoy)))
    crear_vista(recrear)
    # El orden lo define el `$sort` final de la vista.
    return list(db[VISTA].find())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q11",
                                     description="Vista de ingresos por farmacéutico en el mes actual")
    parser.add_argument("--hoy", type=date.fromisoformat,
                        help="mes de referencia AAAA-MM-DD; corre el pipeline sin usar la vista")
    parser.add_argument("--recrear", action="store_true", help="reescribe la definición de la vista")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.hoy, args.recrear))
    return 0


if __name__ == "__main__":
    sys.exit(main())
