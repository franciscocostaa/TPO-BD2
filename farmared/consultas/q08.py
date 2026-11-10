"""q08 — Lotes con menos de 50 unidades, con producto, sucursal y proveedor.

Propósito: listar los lotes con stock bajo para reponer, indicando el
producto, la sucursal donde están y el proveedor habitual del producto. Se
listan todos, incluidos los vencidos y los que quedaron en 0 (no se borran),
y `vencido` indica si ya no se pueden dispensar.

Motor: Redis + MongoDB. Es la única consulta de lectura que cruza motores:

1. Redis: `ZRANGEBYSCORE lotes:unidades -inf (50` devuelve los ids de los
   lotes con menos de 50 unidades, sin recorrer todos (sorted set con
   score = unidades, Clase 18, pp. 14–15). Después, en un pipeline, se leen
   los hashes `lote:{id}` de esos lotes (Clase 18, pp. 18–19).
2. MongoDB: un `$lookup` trae los productos con su proveedor y un `find`
   trae las sucursales, cada uno con un `$in` sobre los ids de los lotes.
3. La aplicación combina los datos por id.

Parámetros: `umbral` (opcional, por defecto 50): las unidades tienen que ser
estrictamente menores. `hoy` (opcional): para calcular `vencido`; por defecto,
la fecha del sistema.

Retorna la lista de lotes ordenada por unidades y por id. Cada uno tiene
`_id`, `nro_lote`, `unidades`, `vencimiento`, `vencido`, `producto` (`_id`,
`nombre`, `presentacion`), `sucursal` (`_id`, `nombre`, `tipo`, `ciudad`) y
`proveedor` (`_id`, `razon_social`, `cuit`, `telefono`).

Uso desde la terminal:

    python -m farmared.consultas.q08
    python -m farmared.consultas.q08 --umbral 20 --hoy 2026-10-13
"""

import argparse
import sys
from datetime import date

from farmared import fechas, stock
from farmared.conexiones import get_mongo, get_redis
from farmared.salida import imprimir

UMBRAL = 50


def _lotes_bajos(umbral: int) -> list[dict]:
    """Hashes de los lotes con `unidades < umbral`, leídos de Redis."""
    r = get_redis()
    ids = r.zrangebyscore(stock.LOTES_UNIDADES, "-inf", f"({umbral}")
    with r.pipeline(transaction=False) as pipe:
        for id_lote in ids:
            pipe.hgetall(stock.clave_lote(id_lote))
        hashes = pipe.execute()
    return [{"_id": id_lote, **h} for id_lote, h in zip(ids, hashes) if h]


def _productos_con_proveedor(ids: set[str]) -> dict[str, dict]:
    pipeline = [
        {"$match": {"_id": {"$in": sorted(ids)}}},
        {"$lookup": {"from": "proveedores", "localField": "id_proveedor",
                     "foreignField": "_id", "as": "proveedor"}},
        {"$project": {"nombre": 1, "presentacion": 1, "proveedor": {"$first": {"$map": {
            "input": "$proveedor", "as": "p",
            "in": {"_id": "$$p._id", "razon_social": "$$p.razon_social",
                   "cuit": "$$p.cuit", "telefono": "$$p.telefono"},
        }}}}},
    ]
    return {p["_id"]: p for p in get_mongo().productos.aggregate(pipeline)}


def _sucursales(ids: set[str]) -> dict[str, dict]:
    cursor = get_mongo().sucursales.find({"_id": {"$in": sorted(ids)}},
                                         {"nombre": 1, "tipo": 1, "ciudad": 1})
    return {s["_id"]: s for s in cursor}


def ejecutar(umbral: int = UMBRAL, hoy: date | None = None) -> list[dict]:
    """Lotes con `unidades < umbral` con su producto, sucursal y proveedor."""
    hoy = hoy or fechas.hoy()
    lotes = _lotes_bajos(umbral)
    productos = _productos_con_proveedor({lote["id_producto"] for lote in lotes})
    sucursales = _sucursales({lote["id_sucursal"] for lote in lotes})

    resultado = []
    for lote in lotes:
        producto = dict(productos.get(lote["id_producto"]) or {"_id": lote["id_producto"]})
        proveedor = producto.pop("proveedor", None)
        vencimiento = date.fromisoformat(lote["vencimiento"])
        resultado.append({
            "_id": lote["_id"],
            "nro_lote": lote["nro_lote"],
            "unidades": int(lote["unidades"]),
            "vencimiento": vencimiento,
            "vencido": vencimiento < hoy,
            "producto": producto,
            "sucursal": sucursales.get(lote["id_sucursal"], {"_id": lote["id_sucursal"]}),
            "proveedor": proveedor,
        })
    # Las unidades salen del hash, que es el dato que se muestra.
    resultado.sort(key=lambda lote: (lote["unidades"], lote["_id"]))
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q08",
                                     description="Lotes con stock bajo, con producto, sucursal y proveedor")
    parser.add_argument("--umbral", type=int, default=UMBRAL, help=f"unidades, estrictamente menor (por defecto {UMBRAL})")
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia AAAA-MM-DD para `vencido` (por defecto, hoy)")
    args = parser.parse_args(argv)
    imprimir(ejecutar(args.umbral, args.hoy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
