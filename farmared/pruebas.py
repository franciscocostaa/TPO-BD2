"""Pruebas de consistencia de los servicios de escritura: `python -m farmared.pruebas`.

Cada escenario parte de una carga limpia, ejecuta q13, q14 o q15 y compara el
estado de las dos bases con el de antes: clientes, recetas y ventas en MongoDB,
y lotes, `lotes:unidades`, `ventas:descontadas` y `descuento:*` en Redis.

Las fallas de infraestructura no se pueden provocar desde la terminal, así que
se simulan reemplazando por un momento una función: la confirmación de la
transacción de MongoDB, o q15 dentro de q14.

Al terminar vuelve a cargar los datos, así que deja las bases como después de
`python -m farmared.carga`. Retorna 0 si pasan todos los escenarios.
"""

import contextlib
import io
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest import mock

from pymongo.client_session import ClientSession
from pymongo.errors import AutoReconnect, OperationFailure

from farmared import carga, stock
from farmared.conexiones import get_mongo, get_redis
from farmared.consultas import q13, q14, q15
from farmared.errores import ErrorDeValidacion

# Fecha fija: los lotes vigentes no cambian según el día en que se corran las pruebas.
HOY = date(2026, 11, 15)


def cargar() -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        if carga.main() != 0:
            raise RuntimeError("la carga falló")


def estado() -> dict:
    """Todo lo que un servicio de escritura puede modificar."""
    db, r = get_mongo(), get_redis()
    return {
        "mongo": {c: list(db[c].find().sort("_id", 1)) for c in ("clientes", "recetas", "ventas")},
        "lotes": {k: r.hgetall(k) for k in sorted(r.scan_iter(match="lote:*"))},
        "unidades": r.zrange(stock.LOTES_UNIDADES, 0, -1, withscores=True),
        "descontadas": sorted(r.smembers(stock.VENTAS_DESCONTADAS)),
        "descuentos": sorted(r.scan_iter(match="descuento:*")),
    }


def unidades(id_lote: str) -> int:
    return int(get_redis().hget(stock.clave_lote(id_lote), "unidades"))


def receta(id_receta: str) -> dict:
    return get_mongo().recetas.find_one({"_id": id_receta})


def intentar(funcion, *args, **kwargs):
    """Resultado de la función, o la excepción que lanzó."""
    try:
        return funcion(*args, **kwargs)
    except Exception as error:
        return error


# Cada escenario devuelve el detalle del resultado o lanza AssertionError.

def stock_insuficiente() -> str:
    antes = estado()
    error = intentar(q14.ejecutar, "C014", "F001", [("PRD003", 5), ("PRD006", 500)], "Obra social", "RC014", HOY)
    assert isinstance(error, ErrorDeValidacion), error
    assert estado() == antes, "cambió el estado"
    return f"rechazada ({error}); PRD003 alcanzaba y tampoco se descontó: sin cambios en ninguna base"


def falla_la_confirmacion() -> str:
    antes = estado()

    def confirmar(sesion):
        raise OperationFailure("falla simulada al confirmar")

    with mock.patch.object(ClientSession, "commit_transaction", confirmar):
        error = intentar(q14.ejecutar, "C011", "F001", [("PRD003", 20), ("PRD001", 35)], "Obra social", "RC012", HOY)
    assert isinstance(error, OperationFailure), error
    assert estado() == antes, "cambió el estado"
    return "el script ya había descontado; sin venta, RC012 sin cambios y el stock repuesto"


def respuesta_perdida() -> str:
    original = ClientSession.commit_transaction

    def confirmar(sesion):
        original(sesion)
        raise AutoReconnect("respuesta perdida simulada")

    l033, l005 = unidades("L033"), unidades("L005")
    with mock.patch.object(ClientSession, "commit_transaction", confirmar):
        resultado = intentar(q14.ejecutar, "C011", "F001", [("PRD003", 20)], "Obra social", "RC012", HOY)
    # q14 comprueba que la venta quedó registrada: no compensa y responde con la venta.
    assert isinstance(resultado, dict), resultado
    venta = get_mongo().ventas.find_one({"_id": resultado["venta"]["_id"]})
    assert venta is not None, "la venta no quedó registrada"
    assert receta("RC012")["dispensas_realizadas"] == 1
    assert (unidades("L033"), unidades("L005")) == (l033 - 15, l005 - 5), "el stock no quedó descontado"
    return f"{venta['_id']} registrada, RC012 con 1 dispensa y el stock descontado: no se compensa y q14 responde con la venta"


def error_entre_script_y_confirmacion() -> str:
    antes = estado()
    original = q15.ejecutar

    def descontar_y_fallar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("falla simulada después del script")

    with mock.patch.object(q15, "ejecutar", descontar_y_fallar):
        error = intentar(q14.ejecutar, "C011", "F001", [("PRD003", 20), ("PRD001", 35)], "Obra social", "RC012", HOY)
    assert isinstance(error, RuntimeError), error
    assert estado() == antes, "cambió el estado"
    return "transacción abortada y stock repuesto: sin cambios"


def ultima_dispensa_concurrente() -> str:
    l007 = unidades("L007")
    with ThreadPoolExecutor(8) as ejecutor:
        resultados = list(ejecutor.map(
            lambda _: intentar(q14.ejecutar, "C003", "F006", [("PRD004", 1)], "Obra social", "RC002", HOY), range(8)))
    ok = [r for r in resultados if isinstance(r, dict)]
    rechazos = Counter(str(r) for r in resultados if isinstance(r, ErrorDeValidacion))
    assert len(ok) == 1 and sum(rechazos.values()) == 7, resultados
    final = receta("RC002")
    assert (final["dispensas_realizadas"], final["estado"]) == (3, "Completada"), final
    assert unidades("L007") == l007 - 1
    return f"1 registrada, 7 rechazadas ({next(iter(rechazos))}); RC002 3/3 y L007 descontó 1 unidad"


def ventas_concurrentes_sobre_un_stock() -> str:
    lotes = ("L019", "L020", "L001")  # PRD001 en S001; L019 está vencido
    antes = {lote: unidades(lote) for lote in lotes}
    vigentes = antes["L020"] + antes["L001"]
    with ThreadPoolExecutor(25) as ejecutor:
        resultados = list(ejecutor.map(
            lambda _: intentar(q14.ejecutar, "C014", "F001", [("PRD001", 10)], "Efectivo", None, HOY), range(25)))
    ok = [r for r in resultados if isinstance(r, dict)]
    rechazos = [r for r in resultados if isinstance(r, ErrorDeValidacion)]
    assert len(ok) + len(rechazos) == 25, resultados
    assert len(ok) == vigentes // 10, f"{len(ok)} registradas con {vigentes} unidades vigentes"
    despues = {lote: unidades(lote) for lote in lotes}
    assert despues == {"L019": antes["L019"], "L020": 0, "L001": vigentes % 10}, despues
    ids = [r["venta"]["_id"] for r in ok]
    items = [r["venta"]["items"][0]["id_detalle"] for r in ok]
    assert len(set(ids)) == len(ids) and len(set(items)) == len(items), "ids repetidos"
    return (f"{len(ok)} registradas y {len(rechazos)} rechazadas con {vigentes} unidades vigentes; "
            f"L020 y L001 en 0, L019 (vencido) intacto, ids únicos")


def altas_concurrentes() -> str:
    def alta(dni):
        return intentar(q13.alta, "Prueba", "Concurrente", dni, "prueba@example.com", "1140000000",
                        "Buenos Aires", "Buenos Aires", "Sin cobertura")

    with ThreadPoolExecutor(8) as ejecutor:
        mismo = list(ejecutor.map(lambda _: alta("40999000"), range(8)))
        distintos = list(ejecutor.map(lambda i: alta(f"4099910{i}"), range(8)))
    assert sum(isinstance(r, dict) for r in mismo) == 1, mismo
    assert all(isinstance(r, dict) for r in distintos), distintos
    assert len({r["_id"] for r in distintos}) == 8
    return "mismo DNI: 1 alta y 7 rechazos; DNI distintos: 8 altas con ids distintos"


def q15_no_descuenta_dos_veces() -> str:
    venta = q14.ejecutar("C014", "F001", [("PRD001", 2)], "Efectivo", None, HOY)["venta"]
    antes = estado()
    error = intentar(q15.ejecutar, venta["_id"], HOY)
    assert isinstance(error, ErrorDeValidacion), error
    assert estado() == antes
    return f"q15 sobre {venta['_id']}, recién registrada por q14: rechazada ({error})"


ESCENARIOS = [
    ("Stock insuficiente en uno de dos ítems", stock_insuficiente),
    ("Falla la confirmación en MongoDB después del descuento", falla_la_confirmacion),
    ("La confirmación se aplica pero la respuesta se pierde", respuesta_perdida),
    ("Error entre el script y la confirmación", error_entre_script_y_confirmacion),
    ("8 ventas simultáneas sobre la última dispensa de RC002", ultima_dispensa_concurrente),
    ("25 ventas simultáneas de 10 unidades de PRD001 en S001", ventas_concurrentes_sobre_un_stock),
    ("8 altas simultáneas de q13", altas_concurrentes),
    ("q15 sobre una venta ya descontada", q15_no_descuenta_dos_veces),
]


def main() -> int:
    fallas = 0
    for nombre, escenario in ESCENARIOS:
        cargar()
        try:
            print(f"✔ {nombre}: {escenario()}")
        except AssertionError as error:
            fallas += 1
            print(f"✘ {nombre}: {error}")
    cargar()
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
