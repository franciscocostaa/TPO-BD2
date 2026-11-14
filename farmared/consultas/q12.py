"""q12 — Clientes sin ventas registradas en el último año.

Propósito: detectar clientes inactivos, para recontactarlos. Aparecen tanto los
que nunca compraron como los que compraron por última vez hace más de un año.
Se listan también los clientes dados de baja: la baja es lógica y siguen en la
colección.

Cuentan las ventas en **cualquier estado**. Una venta "Pendiente" o "Anulada"
igual quedó registrada a nombre del cliente, que es lo que la consulta pregunta.
Es una de las dudas anotadas para la cátedra (`docs/division.md`); si la
respuesta fuera que no cuentan, el cambio es agregar `"estado": {"$ne":
"Anulada"}` al `pipeline` del primer `$lookup`.

Motor: MongoDB, colecciones `clientes` y `ventas`. Es una **anti-unión**: el
pipeline arranca en `clientes` y busca ventas de la ventana con `$lookup`, que
funciona como un *left outer join* (Clase 13, pp. 21–24), y se queda con los
que quedaron con el arreglo vacío. Arrancar en `ventas` no serviría: una
agregación sobre `ventas` nunca devuelve a un cliente que no compró.

El `pipeline` del `$lookup` corta en `$limit: 1`, porque solo hace falta saber
si existe al menos una venta, no traerlas todas. Usa el índice
`ventas {id_cliente, fecha}` que crea la carga.

Un segundo `$lookup`, ya sobre los clientes que cumplen, trae la fecha de su
última venta de cualquier época: así se distingue al que nunca compró
(`ultima_venta: null`) del que compró hace mucho.

Parámetros: `hoy` (opcional): por defecto, la fecha del sistema. `dias`
(opcional, por defecto 365): largo de la ventana, que es `[hoy - dias, hoy]`.

Retorna la lista de clientes ordenada por id, con sus campos más
`ultima_venta`.

Uso desde la terminal:

    python -m farmared.consultas.q12
    python -m farmared.consultas.q12 --hoy 2026-11-14
"""

import argparse
import sys
from datetime import date, timedelta

from farmared import fechas
from farmared.conexiones import get_mongo
from farmared.salida import imprimir

DIAS = 365


def pipeline(hoy: date, dias: int = DIAS) -> list[dict]:
    """Pipeline sobre `clientes` que deja solo a los que no tienen ventas en la ventana."""
    desde = fechas.a_mongo(hoy - timedelta(days=dias))
    hasta = fechas.a_mongo(hoy)
    return [
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_cliente",
            "as": "del_anio",
            "pipeline": [
                {"$match": {"fecha": {"$gte": desde, "$lte": hasta}}},
                # Alcanza con saber si hay una.
                {"$limit": 1},
                {"$project": {"_id": 1}},
            ],
        }},
        {"$match": {"del_anio": {"$size": 0}}},
        {"$unset": "del_anio"},
        # Recién acá, sobre los que cumplen: su última venta de cualquier época.
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_cliente",
            "as": "ultima",
            "pipeline": [
                {"$sort": {"fecha": -1}},
                {"$limit": 1},
                {"$project": {"fecha": 1}},
            ],
        }},
        {"$set": {"ultima_venta": {"$ifNull": [{"$first": "$ultima.fecha"}, None]}}},
        {"$unset": "ultima"},
        {"$sort": {"_id": 1}},
    ]


def ejecutar(hoy: date | None = None, dias: int = DIAS) -> list[dict]:
    """Clientes sin ninguna venta registrada en los últimos `dias`."""
    return list(get_mongo().clientes.aggregate(pipeline(hoy or fechas.hoy(), dias)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q12",
                                     description="Clientes sin ventas registradas en el último año")
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia AAAA-MM-DD (por defecto, hoy)")
    parser.add_argument("--dias", type=int, default=DIAS, help=f"largo de la ventana (por defecto {DIAS})")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.hoy, args.dias))
    return 0


if __name__ == "__main__":
    sys.exit(main())
