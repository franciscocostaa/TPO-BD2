"""q14 — Registro de una venta "Completada".

Propósito: registrar una venta con sus ítems, validando cliente, farmacéutico,
sucursal, productos y receta; calcular el total; actualizar la receta según
las reglas de dispensa, y descontar el stock con q15. Todo o nada: si algo
falla, no queda ni la venta, ni la receta modificada, ni stock descontado.

Motor: MongoDB + Redis. No hay transacciones entre los dos motores, así que el
todo o nada sale del orden de las operaciones:

1. Abre una transacción de MongoDB. Dentro de ella valida, inserta la venta y
   actualiza la receta, sin confirmar.
2. Llama a q15 con la sesión: el script Lua descuenta el stock en Redis o lo
   rechaza sin tocar ningún lote.
3. Si q15 rechaza o algo falla antes, aborta la transacción: no queda nada.
4. Si q15 descuenta, confirma la transacción.
5. Si la confirmación falla y la venta no quedó registrada, compensa en Redis
   devolviendo a cada lote lo que se le descontó (`stock.reponer`).

Las validaciones leen dentro de la transacción. Si otra venta modifica la misma
receta al mismo tiempo, MongoDB aborta una de las dos por conflicto de
escritura y esta función la reintenta desde cero, volviendo a validar. Los
reintentos ocurren siempre antes del paso 2, así que nunca descuentan stock dos
veces.

Los ids de la venta y de sus ítems salen de la colección `contadores` con un
`$inc` atómico fuera de la transacción, así que dos ventas simultáneas nunca
compiten por el mismo id. Una venta rechazada por stock deja su número sin usar.

Reglas:
- Cliente existente y activo. Con medio de pago "Obra social", el cliente tiene
  que tener cobertura.
- Farmacéutico existente y activo, de una sucursal de tipo "Farmacia".
- Productos existentes y activos, con cantidad entera mayor a 0. El precio de
  cada ítem es el precio de lista vigente y el total es la suma de los ítems.
- Si algún producto es "Bajo receta" o "Bajo receta archivada", hace falta una
  receta existente, "Vigente" y del mismo cliente; si alguno es "Bajo receta
  archivada", la receta tiene que ser de tipo "Archivada". Si ningún producto la
  exige, no se acepta una receta. El tipo de la venta se deriva de esto.
- La venta es una dispensa: suma 1 a `dispensas_realizadas`. Si llega a las
  autorizadas, la receta pasa a "Completada" y `proxima_dispensa` queda vacía;
  si no, `proxima_dispensa` pasa a 30 días después de la venta.

Parámetros: `id_cliente`, `id_farmaceutico`, `items` (lista de
`(id_producto, cantidad)`), `medio_pago`, `id_receta` (opcional) y `hoy`
(opcional, por defecto la fecha del sistema): fecha de la venta y referencia
para los vencimientos.

Retorna `venta` (el documento insertado), `receta` (`antes` y `despues`, o
`None` si la venta no usa receta) y `stock` (el resultado de q15, con las
unidades antes y después de cada lote). Lanza `ErrorDeValidacion` sin modificar
nada si el pedido viola una regla o el stock no alcanza.

Uso desde la terminal:

    python -m farmared.consultas.q14 --cliente C011 --farmaceutico F001 \\
        --item PRD003:20 --item PRD001:35 --medio-pago "Obra social" --receta RC012
"""

import argparse
import random
import sys
import time
from datetime import date, timedelta

from pymongo import ReturnDocument
from pymongo.client_session import ClientSession
from pymongo.errors import PyMongoError

from farmared import fechas, stock
from farmared.conexiones import get_mongo, get_mongo_client
from farmared.consultas import q15
from farmared.errores import ErrorDeValidacion
from farmared.salida import imprimir

MEDIOS_DE_PAGO = {"Efectivo", "Débito", "Crédito", "Transferencia", "Obra social"}
BAJO_RECETA = "Bajo receta"
BAJO_RECETA_ARCHIVADA = "Bajo receta archivada"
DIAS_ENTRE_DISPENSAS = 30
INTENTOS = 10


def _requieren(ids: list[str], que: str) -> str:
    return f"{', '.join(ids)} {'requiere' if len(ids) == 1 else 'requieren'} {que}"


def _reservar(contador: str, cantidad: int) -> int:
    """Reserva `cantidad` números consecutivos de `contador` y devuelve el primero."""
    documento = get_mongo().contadores.find_one_and_update(
        {"_id": contador}, {"$inc": {"ultimo": cantidad}}, return_document=ReturnDocument.AFTER)
    return documento["ultimo"] - cantidad + 1


def _buscar(coleccion: str, _id: str, nombre: str, sesion: ClientSession) -> dict:
    documento = get_mongo()[coleccion].find_one({"_id": _id}, session=sesion)
    if documento is None:
        raise ErrorDeValidacion(f"no existe {nombre} {_id}")
    return documento


def _validar_pedido(items: list[tuple[str, int]], medio_pago: str) -> None:
    if not items:
        raise ErrorDeValidacion("la venta no tiene ítems")
    for id_producto, cantidad in items:
        if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad <= 0:
            raise ErrorDeValidacion(f"cantidad inválida para {id_producto}: {cantidad!r}; tiene que ser un entero mayor a 0")
    if medio_pago not in MEDIOS_DE_PAGO:
        raise ErrorDeValidacion(f"medio de pago inválido: {medio_pago!r}; opciones: {', '.join(sorted(MEDIOS_DE_PAGO))}")


def _validar_receta(id_receta: str | None, cliente: dict, productos: dict[str, dict],
                    sesion: ClientSession) -> dict | None:
    condiciones = {p["condicion_venta"] for p in productos.values()}
    exige = condiciones & {BAJO_RECETA, BAJO_RECETA_ARCHIVADA}
    if not exige:
        if id_receta is not None:
            raise ErrorDeValidacion(f"ningún producto de la venta requiere receta; no se informa {id_receta}")
        return None
    if id_receta is None:
        con_receta = sorted(i for i, p in productos.items() if p["condicion_venta"] in exige)
        raise ErrorDeValidacion(_requieren(con_receta, "receta"))

    receta = _buscar("recetas", id_receta, "la receta", sesion)
    if receta["id_cliente"] != cliente["_id"]:
        raise ErrorDeValidacion(f"la receta {id_receta} es de otro cliente ({receta['id_cliente']})")
    if receta["estado"] != "Vigente":
        raise ErrorDeValidacion(f"la receta {id_receta} no está vigente ({receta['estado']})")
    if receta["dispensas_realizadas"] >= receta["dispensas_autorizadas"]:
        raise ErrorDeValidacion(f"la receta {id_receta} no tiene dispensas disponibles")
    if BAJO_RECETA_ARCHIVADA in exige and receta["tipo"] != "Archivada":
        archivados = sorted(i for i, p in productos.items() if p["condicion_venta"] == BAJO_RECETA_ARCHIVADA)
        raise ErrorDeValidacion(f"{_requieren(archivados, 'receta archivada')}; {id_receta} es {receta['tipo']}")
    return receta


def _dispensar(receta: dict, hoy: date, sesion: ClientSession) -> dict:
    """Registra una dispensa. El filtro por estado y dispensas hace que dos
    ventas concurrentes sobre la misma receta no cuenten la misma dispensa."""
    realizadas = receta["dispensas_realizadas"] + 1
    if realizadas == receta["dispensas_autorizadas"]:
        cambios = {"dispensas_realizadas": realizadas, "estado": "Completada", "proxima_dispensa": None}
    else:
        proxima = fechas.a_mongo(hoy + timedelta(days=DIAS_ENTRE_DISPENSAS))
        cambios = {"dispensas_realizadas": realizadas, "proxima_dispensa": proxima}
    despues = get_mongo().recetas.find_one_and_update(
        {"_id": receta["_id"], "estado": "Vigente", "dispensas_realizadas": receta["dispensas_realizadas"]},
        {"$set": cambios},
        return_document=ReturnDocument.AFTER,
        session=sesion,
    )
    if despues is None:
        raise ErrorDeValidacion(f"la receta {receta['_id']} cambió durante la venta")
    return despues


def _registrar(id_cliente: str, id_farmaceutico: str, items: list[tuple[str, int]], medio_pago: str,
               id_receta: str | None, hoy: date, sesion: ClientSession) -> tuple[dict, dict | None, dict | None]:
    """Valida e inserta la venta y actualiza la receta dentro de la transacción de `sesion`."""
    db = get_mongo()
    cliente = _buscar("clientes", id_cliente, "el cliente", sesion)
    if not cliente["activo"]:
        raise ErrorDeValidacion(f"el cliente {id_cliente} está dado de baja")
    if medio_pago == "Obra social" and cliente["obra_social"] == "Sin cobertura":
        raise ErrorDeValidacion(f"el cliente {id_cliente} no tiene cobertura: no puede pagar con obra social")

    farmaceutico = _buscar("farmaceuticos", id_farmaceutico, "el farmacéutico", sesion)
    if not farmaceutico["activo"]:
        raise ErrorDeValidacion(f"el farmacéutico {id_farmaceutico} está dado de baja")
    sucursal = _buscar("sucursales", farmaceutico["id_sucursal"], "la sucursal", sesion)
    if sucursal["tipo"] != "Farmacia":
        raise ErrorDeValidacion(f"{sucursal['_id']} ({sucursal['nombre']}) es {sucursal['tipo']}: solo se vende en farmacias")

    ids_productos = {id_producto for id_producto, _ in items}
    productos = {p["_id"]: p for p in db.productos.find({"_id": {"$in": sorted(ids_productos)}}, session=sesion)}
    faltantes = sorted(ids_productos - set(productos))
    if faltantes:
        raise ErrorDeValidacion(f"no existe el producto {faltantes[0]}" if len(faltantes) == 1
                                else f"no existen los productos {', '.join(faltantes)}")
    inactivos = sorted(i for i, p in productos.items() if not p["activo"])
    if inactivos:
        raise ErrorDeValidacion(f"producto discontinuado: {inactivos[0]}" if len(inactivos) == 1
                                else f"productos discontinuados: {', '.join(inactivos)}")

    receta = _validar_receta(id_receta, cliente, productos, sesion)

    numero_venta = _reservar("ventas", 1)
    numero_detalle = _reservar("detalle_ventas", len(items))
    detalle = [
        {"id_detalle": f"D{numero_detalle + i:03d}", "id_producto": id_producto,
         "cantidad": cantidad, "precio_unit": productos[id_producto]["precio_unit"]}
        for i, (id_producto, cantidad) in enumerate(items)
    ]
    venta = {
        "_id": f"V{numero_venta:03d}",
        "id_cliente": id_cliente,
        "id_farmaceutico": id_farmaceutico,
        "id_sucursal": sucursal["_id"],
        "id_receta": id_receta,
        "fecha": fechas.a_mongo(hoy),
        "tipo": "Con receta" if receta else "Venta libre",
        "medio_pago": medio_pago,
        "total": sum(item["cantidad"] * item["precio_unit"] for item in detalle),
        "estado": "Completada",
        "items": detalle,
    }
    db.ventas.insert_one(venta, session=sesion)
    receta_despues = _dispensar(receta, hoy, sesion) if receta else None
    return venta, receta, receta_despues


def _confirmar(id_venta: str, sesion: ClientSession) -> None:
    """Confirma la transacción. Si no se puede y la venta no quedó registrada,
    devuelve el stock que q15 ya descontó."""
    try:
        sesion.commit_transaction()
    except PyMongoError:
        # Un commit con resultado incierto puede haberse aplicado igual.
        if get_mongo().ventas.find_one({"_id": id_venta}, {"_id": 1}) is None:
            stock.reponer(id_venta)
            raise


def ejecutar(id_cliente: str, id_farmaceutico: str, items: list[tuple[str, int]], medio_pago: str,
             id_receta: str | None = None, hoy: date | None = None) -> dict:
    """Registra una venta "Completada" y descuenta su stock, todo o nada."""
    hoy = hoy or fechas.hoy()
    items = list(items)
    _validar_pedido(items, medio_pago)

    with get_mongo_client().start_session() as sesion:
        for intento in range(INTENTOS):
            sesion.start_transaction()
            try:
                venta, receta_antes, receta_despues = _registrar(
                    id_cliente, id_farmaceutico, items, medio_pago, id_receta, hoy, sesion)
            except PyMongoError as error:
                sesion.abort_transaction()
                if error.has_error_label("TransientTransactionError"):
                    time.sleep(random.uniform(0, 0.02 * (intento + 1)))
                    continue
                raise
            except BaseException:
                sesion.abort_transaction()
                raise
            break
        else:
            raise RuntimeError(f"no se pudo registrar la venta tras {INTENTOS} conflictos con ventas concurrentes")

        try:
            descuento = q15.ejecutar(venta["_id"], hoy, sesion)
        except BaseException:
            sesion.abort_transaction()
            # Si el script Lua llegó a descontar, se devuelve; si no, no hace nada.
            stock.reponer(venta["_id"])
            raise
        _confirmar(venta["_id"], sesion)

    receta = {"antes": receta_antes, "despues": receta_despues} if receta_antes else None
    return {"venta": venta, "receta": receta, "stock": descuento}


def _item(texto: str) -> tuple[str, int]:
    id_producto, separador, cantidad = texto.partition(":")
    if not separador or not cantidad.lstrip("-").isdigit():
        raise argparse.ArgumentTypeError(f"ítem inválido {texto!r}; formato: PRODUCTO:CANTIDAD")
    return id_producto, int(cantidad)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q14",
                                     description="Registro de una venta Completada con descuento de stock")
    parser.add_argument("--cliente", required=True, dest="id_cliente")
    parser.add_argument("--farmaceutico", required=True, dest="id_farmaceutico")
    parser.add_argument("--item", required=True, action="append", type=_item, dest="items",
                        help="PRODUCTO:CANTIDAD, una vez por ítem")
    parser.add_argument("--medio-pago", required=True, dest="medio_pago")
    parser.add_argument("--receta", dest="id_receta")
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de la venta AAAA-MM-DD (por defecto, hoy)")
    args = parser.parse_args(argv)
    try:
        resultado = ejecutar(**vars(args))
    except ErrorDeValidacion as error:
        print(f"✘ Rechazado: {error}")
        return 1
    imprimir(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
