"""Carga de los datos: `python -m farmared.carga`.

Lee los CSV de `datos/provistos/` y `datos/adicionales/` (mismos nombres y
encabezados), valida todo antes de escribir y reemplaza el contenido de las
colecciones de MongoDB y del stock en Redis. Es idempotente: cada ejecución
deja exactamente el estado de los CSV y descarta los cambios hechos por los
servicios de escritura.

- MongoDB: índices y, en una única transacción, `delete_many` + `insert_many`
  de cada colección. Si algo falla, no queda una carga a medias.
- Redis: en un único `MULTI`, se borran las claves de stock anteriores, se
  escriben los lotes y se marcan como descontadas las ventas "Completada" de
  los CSV, cuyo stock ya está reflejado en los lotes (ver `farmared/stock.py`).
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from pymongo import ASCENDING

from farmared import stock
from farmared.conexiones import get_mongo, get_mongo_client, get_redis

DATOS = Path(__file__).resolve().parent.parent / "datos"
PROVISTOS = DATOS / "provistos"
ADICIONALES = DATOS / "adicionales"

# Archivo → campo identificador.
ARCHIVOS = {
    "clientes": "id_cliente",
    "sucursales": "id_sucursal",
    "farmaceuticos": "id_farmaceutico",
    "proveedores": "id_proveedor",
    "productos": "id_producto",
    "recetas": "id_receta",
    "ventas": "id_venta",
    "detalle_ventas": "id_detalle",
    "stock_lotes": "id_lote",
}

ENTEROS = {"precio_unit", "unidades", "dispensas_autorizadas", "dispensas_realizadas", "total", "cantidad"}
FECHAS = {"fecha_emision", "proxima_dispensa", "fecha", "vencimiento"}
BOOLEANOS = {"activo"}

# Únicos campos que la consigna permite vacíos.
NULABLES = {("clientes", "nro_afiliado"), ("recetas", "proxima_dispensa"), ("ventas", "id_receta")}

# Relaciones de la consigna (§2.10): (archivo, campo, archivo referenciado).
REFERENCIAS = [
    ("farmaceuticos", "id_sucursal", "sucursales"),
    ("productos", "id_proveedor", "proveedores"),
    ("stock_lotes", "id_producto", "productos"),
    ("stock_lotes", "id_sucursal", "sucursales"),
    ("recetas", "id_cliente", "clientes"),
    ("ventas", "id_cliente", "clientes"),
    ("ventas", "id_farmaceutico", "farmaceuticos"),
    ("ventas", "id_receta", "recetas"),
    ("detalle_ventas", "id_venta", "ventas"),
    ("detalle_ventas", "id_producto", "productos"),
]

UNICOS = [("clientes", "dni"), ("farmaceuticos", "matricula")]

INDICES = {
    "clientes": [([("dni", ASCENDING)], {"unique": True})],
    "farmaceuticos": [
        ([("matricula", ASCENDING)], {"unique": True}),
        ([("id_sucursal", ASCENDING)], {}),
    ],
    "recetas": [
        ([("id_cliente", ASCENDING)], {}),
        ([("tipo", ASCENDING), ("estado", ASCENDING), ("proxima_dispensa", ASCENDING)], {}),
    ],
    "ventas": [
        ([("id_cliente", ASCENDING), ("fecha", ASCENDING)], {}),
        ([("id_farmaceutico", ASCENDING), ("fecha", ASCENDING)], {}),
        ([("fecha", ASCENDING)], {}),
        ([("estado", ASCENDING)], {}),
        ([("items.id_detalle", ASCENDING)], {"unique": True}),
    ],
}


def convertir(campo: str, valor: str):
    """Convierte un valor del CSV según las convenciones de la consigna."""
    if valor == "":
        return None
    if campo in ENTEROS:
        return int(valor)
    if campo in FECHAS:
        return datetime.strptime(valor, "%Y-%m-%d")
    if campo in BOOLEANOS:
        if valor not in ("True", "False"):
            raise ValueError(f"{campo}: booleano inválido {valor!r}")
        return valor == "True"
    return valor


def leer(archivo: str, errores: list[str]) -> dict[str, list[dict]]:
    """Filas de `archivo` por origen. El archivo de `adicionales/` es opcional."""
    filas = {"provistos": [], "adicionales": []}
    encabezado = None
    for origen in (PROVISTOS, ADICIONALES):
        ruta = origen / f"{archivo}.csv"
        if origen is ADICIONALES and not ruta.exists():
            continue
        with ruta.open(encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            if encabezado is None:
                encabezado = lector.fieldnames
            elif lector.fieldnames != encabezado:
                errores.append(f"{origen.name}/{ruta.name}: el encabezado no coincide con el de provistos/")
                continue
            for fila in lector:
                lugar = f"{origen.name}/{ruta.name}, línea {lector.line_num}"
                if None in fila or None in fila.values():
                    errores.append(f"{lugar}: cantidad de columnas incorrecta")
                    continue
                try:
                    filas[origen.name].append({campo: convertir(campo, valor) for campo, valor in fila.items()})
                except ValueError as error:
                    errores.append(f"{lugar}: {error}")
    return filas


def validar(tablas: dict[str, list[dict]]) -> list[str]:
    """Errores de integridad de los datos combinados. Vacío si se pueden cargar."""
    errores = []
    ids = {}
    for archivo, campo_id in ARCHIVOS.items():
        for fila in tablas[archivo]:
            for campo, valor in fila.items():
                if valor is None and (archivo, campo) not in NULABLES:
                    errores.append(f"{archivo} {fila[campo_id]}: {campo} vacío")
        repetidos = Counter(fila[campo_id] for fila in tablas[archivo])
        errores += [f"{archivo}: {campo_id} {valor} repetido" for valor, n in repetidos.items() if n > 1]
        ids[archivo] = set(repetidos)
    for archivo, campo in UNICOS:
        repetidos = Counter(fila[campo] for fila in tablas[archivo])
        errores += [f"{archivo}: {campo} {valor} repetido" for valor, n in repetidos.items() if n > 1]
    if errores:
        return errores

    for archivo, campo, destino in REFERENCIAS:
        for fila in tablas[archivo]:
            valor = fila[campo]
            if valor is not None and valor not in ids[destino]:
                errores.append(f"{archivo} {fila[ARCHIVOS[archivo]]}: {campo} {valor} no existe en {destino}")
    if errores:
        return errores

    items = defaultdict(list)
    for detalle in tablas["detalle_ventas"]:
        items[detalle["id_venta"]].append(detalle)
    cliente_de_receta = {receta["id_receta"]: receta["id_cliente"] for receta in tablas["recetas"]}
    for venta in tablas["ventas"]:
        de_la_venta = items[venta["id_venta"]]
        suma = sum(item["cantidad"] * item["precio_unit"] for item in de_la_venta)
        if not de_la_venta:
            errores.append(f"ventas {venta['id_venta']}: no tiene ítems")
        elif venta["total"] != suma:
            errores.append(f"ventas {venta['id_venta']}: total {venta['total']} ≠ suma de ítems {suma}")
        if venta["id_receta"] is not None and cliente_de_receta[venta["id_receta"]] != venta["id_cliente"]:
            errores.append(f"ventas {venta['id_venta']}: la receta {venta['id_receta']} es de otro cliente")
    for lote in tablas["stock_lotes"]:
        if lote["unidades"] < 0:
            errores.append(f"stock_lotes {lote['id_lote']}: unidades negativas")
    return errores


def con_id(fila: dict, campo_id: str) -> dict:
    """Documento con el id del CSV como `_id` y el resto de los campos sin cambios."""
    return {"_id": fila[campo_id], **{campo: valor for campo, valor in fila.items() if campo != campo_id}}


def ultimo_numero(ids) -> int:
    """Mayor número de una serie de ids como `V016` o `D022`."""
    return max((int(re.fullmatch(r"[A-Z]+(\d+)", i)[1]) for i in ids), default=0)


def documentos(tablas: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Documentos de cada colección de MongoDB según `docs/modelo.md`."""
    docs = {
        nombre: [con_id(fila, ARCHIVOS[nombre]) for fila in tablas[nombre]]
        for nombre in ("clientes", "sucursales", "farmaceuticos", "proveedores", "productos", "recetas")
    }
    sucursal_de = {f["id_farmaceutico"]: f["id_sucursal"] for f in tablas["farmaceuticos"]}
    items = defaultdict(list)
    for d in tablas["detalle_ventas"]:
        items[d["id_venta"]].append({
            "id_detalle": d["id_detalle"],
            "id_producto": d["id_producto"],
            "cantidad": d["cantidad"],
            "precio_unit": d["precio_unit"],
        })
    docs["ventas"] = [
        {
            "_id": v["id_venta"],
            "id_cliente": v["id_cliente"],
            "id_farmaceutico": v["id_farmaceutico"],
            "id_sucursal": sucursal_de[v["id_farmaceutico"]],
            "id_receta": v["id_receta"],
            "fecha": v["fecha"],
            "tipo": v["tipo"],
            "medio_pago": v["medio_pago"],
            "total": v["total"],
            "estado": v["estado"],
            "items": items[v["id_venta"]],
        }
        for v in tablas["ventas"]
    ]
    # Último id usado de cada serie; q14 los incrementa al registrar ventas.
    docs["contadores"] = [
        {"_id": archivo, "ultimo": ultimo_numero(fila[ARCHIVOS[archivo]] for fila in tablas[archivo])}
        for archivo in ("ventas", "detalle_ventas")
    ]
    return docs


def cargar_mongo(docs: dict[str, list[dict]]) -> None:
    db = get_mongo()
    for nombre, indices in INDICES.items():
        for claves, opciones in indices:
            db[nombre].create_index(claves, **opciones)

    def reemplazar(sesion):
        for nombre, lista in docs.items():
            db[nombre].delete_many({}, session=sesion)
            db[nombre].insert_many(lista, session=sesion)

    with get_mongo_client().start_session() as sesion:
        sesion.with_transaction(reemplazar)


def cargar_redis(lotes: list[dict], ventas: list[dict]) -> None:
    r = get_redis()
    anteriores = [*r.scan_iter(match="lote:*"), *r.scan_iter(match="stock:*"),
                  *r.scan_iter(match="descuento:*")]
    completadas = [v["id_venta"] for v in ventas if v["estado"] == "Completada"]
    with r.pipeline(transaction=True) as pipe:
        pipe.delete(stock.LOTES_UNIDADES, stock.VENTAS_DESCONTADAS, *anteriores)
        for lote in lotes:
            stock.escribir_lote(
                pipe, lote["id_lote"], lote["id_producto"], lote["id_sucursal"],
                lote["nro_lote"], lote["unidades"], lote["vencimiento"].date(),
            )
        if completadas:
            pipe.sadd(stock.VENTAS_DESCONTADAS, *completadas)
        pipe.execute()


def main() -> int:
    errores = []
    por_origen = {archivo: leer(archivo, errores) for archivo in ARCHIVOS}
    tablas = {archivo: filas["provistos"] + filas["adicionales"] for archivo, filas in por_origen.items()}
    if not errores:
        errores = validar(tablas)
    if errores:
        print("✘ Carga abortada; no se modificó ninguna base:")
        for error in errores:
            print(f"  - {error}")
        return 1

    cargar_mongo(documentos(tablas))
    cargar_redis(tablas["stock_lotes"], tablas["ventas"])

    destinos = {"detalle_ventas": "MongoDB ventas.items", "stock_lotes": "Redis"}
    for archivo, filas in por_origen.items():
        destino = destinos.get(archivo, f"MongoDB {archivo}")
        print(f"✔ {archivo}: {len(filas['provistos'])} provistos + {len(filas['adicionales'])} adicionales → {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
