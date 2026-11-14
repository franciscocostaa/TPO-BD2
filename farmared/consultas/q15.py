"""q15 — Descuento de stock de una venta registrada.

Propósito: dada una venta "Completada", descontar las unidades de cada
producto de los lotes de la sucursal del farmacéutico, por FEFO (primero el
que vence antes) y salteando los lotes vencidos. Si el stock vigente no
alcanza para algún producto, se rechaza todo y no se modifica ningún lote.

Motor: MongoDB + Redis.

1. MongoDB: lee la venta. Si recibe la sesión de q14, la lee dentro de su
   transacción, donde la venta ya está insertada aunque no confirmada.
2. Redis: el script Lua `descontar` (`farmared/stock.py`) arma el plan FEFO de
   todos los productos y, solo si alcanzan todos, lo aplica. Es una única
   operación atómica (Clase 17, p. 31). En la misma operación marca la venta
   como descontada, así que una venta nunca se descuenta dos veces.

La sucursal es la `id_sucursal` de la venta, que q14 copia del farmacéutico
al registrarla. Si un producto aparece en más de un ítem, se suman sus
cantidades. Un lote vence al final del día de su `vencimiento`.

Parámetros: `id_venta`; `hoy` (opcional, por defecto la fecha del sistema),
para decidir qué lotes están vencidos; `sesion` (opcional), la sesión de
MongoDB de q14.

Retorna `id_venta`, `id_sucursal` y `lotes`: cada lote tocado con `_id`,
`id_producto`, `vencimiento`, `antes`, `descontadas` y `despues`, en el orden
en que se consumieron. Lanza `ErrorDeValidacion` sin modificar nada si la venta
no existe, no está "Completada", ya se descontó o el stock no alcanza.

Uso desde la terminal:

    python -m farmared.consultas.q15 V017
    python -m farmared.consultas.q15 V017 --hoy 2026-11-14
"""

import argparse
import sys
from collections import Counter
from datetime import date

from pymongo.client_session import ClientSession

from farmared import fechas, stock
from farmared.conexiones import get_mongo
from farmared.errores import ErrorDeValidacion
from farmared.salida import imprimir


def ejecutar(id_venta: str, hoy: date | None = None, sesion: ClientSession | None = None) -> dict:
    """Descuenta por FEFO el stock de la venta `id_venta`, todo o nada."""
    hoy = hoy or fechas.hoy()
    venta = get_mongo().ventas.find_one({"_id": id_venta}, session=sesion)
    if venta is None:
        raise ErrorDeValidacion(f"no existe la venta {id_venta}")
    if venta["estado"] != "Completada":
        raise ErrorDeValidacion(f"la venta {id_venta} está {venta['estado']}: solo una venta Completada descuenta stock")

    cantidades = Counter()
    for item in venta["items"]:
        cantidades[item["id_producto"]] += item["cantidad"]
    lotes = stock.descontar(id_venta, venta["id_sucursal"], cantidades, hoy)
    return {"id_venta": id_venta, "id_sucursal": venta["id_sucursal"], "lotes": lotes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q15",
                                     description="Descuento de stock FEFO de una venta registrada")
    parser.add_argument("id_venta")
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia AAAA-MM-DD para los vencimientos (por defecto, hoy)")
    args = parser.parse_args(argv)
    try:
        resultado = ejecutar(args.id_venta, args.hoy)
    except ErrorDeValidacion as error:
        print(f"✘ Rechazado: {error}")
        return 1
    imprimir(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
