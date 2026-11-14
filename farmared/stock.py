"""Stock por lote en Redis (ver `docs/informe.md`, sección 2).

Claves:

- `lote:{id_lote}`: hash con `id_producto`, `id_sucursal`, `nro_lote`, `unidades` y `vencimiento`.
- `stock:{id_sucursal}:{id_producto}`: sorted set de lotes con score = vencimiento como AAAAMMDD.
- `lotes:unidades`: sorted set de todos los lotes con score = unidades.
- `ventas:descontadas`: set de las ventas cuyo stock ya se descontó.
- `descuento:{id_venta}`: hash `id_lote` → unidades que se descontaron de ese lote para la venta.

Las unidades solo cambian dentro de los scripts Lua `descontar` y `reponer`,
que actualizan el hash del lote y `lotes:unidades` juntos. Redis ejecuta cada
script de forma atómica, sin atender a otro cliente en el medio (Clase 17, p. 31).
"""

import json
from datetime import date
from functools import cache

from farmared.conexiones import get_redis
from farmared.errores import ErrorDeValidacion

LOTES_UNIDADES = "lotes:unidades"
VENTAS_DESCONTADAS = "ventas:descontadas"


def clave_lote(id_lote: str) -> str:
    return f"lote:{id_lote}"


def clave_stock(id_sucursal: str, id_producto: str) -> str:
    return f"stock:{id_sucursal}:{id_producto}"


def clave_descuento(id_venta: str) -> str:
    return f"descuento:{id_venta}"


def score_fecha(fecha: date) -> int:
    """Fecha como entero AAAAMMDD, para ordenar y filtrar lotes por vencimiento."""
    return fecha.year * 10000 + fecha.month * 100 + fecha.day


def escribir_lote(pipe, id_lote: str, id_producto: str, id_sucursal: str,
                  nro_lote: str, unidades: int, vencimiento: date) -> None:
    """Encola en `pipe` la escritura de un lote en las tres claves."""
    pipe.hset(clave_lote(id_lote), mapping={
        "id_producto": id_producto,
        "id_sucursal": id_sucursal,
        "nro_lote": nro_lote,
        "unidades": unidades,
        "vencimiento": vencimiento.isoformat(),
    })
    pipe.zadd(clave_stock(id_sucursal, id_producto), {id_lote: score_fecha(vencimiento)})
    pipe.zadd(LOTES_UNIDADES, {id_lote: unidades})


# KEYS: ventas:descontadas, descuento:{id_venta}, lotes:unidades, stock:{sucursal}:{producto}...
# ARGV: id_venta, hoy (AAAAMMDD), cantidad pedida de cada producto, en el orden de KEYS[4..].
#
# Primera pasada: arma el plan FEFO de todos los productos sin escribir nada.
# Los lotes con vencimiento anterior a hoy quedan fuera del ZRANGEBYSCORE.
# Si algún producto no alcanza, devuelve los faltantes y no toca ningún lote.
# Segunda pasada: aplica el plan y registra la venta como descontada.
_DESCONTAR = """
local descontadas, descuento, por_unidades = KEYS[1], KEYS[2], KEYS[3]
local id_venta, hoy = ARGV[1], ARGV[2]

if redis.call('SISMEMBER', descontadas, id_venta) == 1 then
  return cjson.encode({estado = 'ya_descontada'})
end

local plan, faltantes = {}, {}
for i = 4, #KEYS do
  local pedido = tonumber(ARGV[i - 1])
  local restante = pedido
  for _, id_lote in ipairs(redis.call('ZRANGEBYSCORE', KEYS[i], hoy, '+inf')) do
    if restante == 0 then break end
    local lote = redis.call('HMGET', 'lote:' .. id_lote, 'unidades', 'id_producto', 'vencimiento')
    local unidades = tonumber(lote[1])
    local toma = math.min(unidades, restante)
    if toma > 0 then
      table.insert(plan, {id_lote = id_lote, id_producto = lote[2], vencimiento = lote[3],
                          antes = unidades, descontadas = toma})
      restante = restante - toma
    end
  end
  if restante > 0 then
    table.insert(faltantes, {stock = KEYS[i], pedido = pedido, disponible = pedido - restante})
  end
end

if #faltantes > 0 then
  return cjson.encode({estado = 'insuficiente', faltantes = faltantes})
end

for _, paso in ipairs(plan) do
  paso.despues = redis.call('HINCRBY', 'lote:' .. paso.id_lote, 'unidades', -paso.descontadas)
  redis.call('ZADD', por_unidades, paso.despues, paso.id_lote)
  redis.call('HSET', descuento, paso.id_lote, paso.descontadas)
end
redis.call('SADD', descontadas, id_venta)
return cjson.encode({estado = 'ok', lotes = plan})
"""

# KEYS: ventas:descontadas, descuento:{id_venta}, lotes:unidades
# ARGV: id_venta
#
# Devuelve a cada lote lo que se le descontó a la venta y la desmarca. Sin
# `descuento:{id_venta}` no hace nada: así no desmarca una venta de la carga,
# cuyo descuento no está registrado.
_REPONER = """
local descontadas, descuento, por_unidades = KEYS[1], KEYS[2], KEYS[3]
local asignacion = redis.call('HGETALL', descuento)
for i = 1, #asignacion, 2 do
  local id_lote = asignacion[i]
  local quedan = redis.call('HINCRBY', 'lote:' .. id_lote, 'unidades', tonumber(asignacion[i + 1]))
  redis.call('ZADD', por_unidades, quedan, id_lote)
end
if #asignacion > 0 then
  redis.call('DEL', descuento)
  redis.call('SREM', descontadas, ARGV[1])
end
return #asignacion / 2
"""


@cache
def _script(codigo: str):
    return get_redis().register_script(codigo)


def descontar(id_venta: str, id_sucursal: str, cantidades: dict[str, int], hoy: date) -> list[dict]:
    """Descuenta `cantidades` (id_producto → unidades) de los lotes vigentes de
    `id_sucursal`, por FEFO, todo o nada.

    Retorna los lotes tocados con `_id`, `id_producto`, `vencimiento`, `antes`,
    `descontadas` y `despues`, en el orden en que se consumieron. Lanza `ErrorDeValidacion` sin tocar ningún
    lote si la venta ya se descontó o si el stock vigente no alcanza para algún
    producto.
    """
    productos = list(cantidades)
    claves = [VENTAS_DESCONTADAS, clave_descuento(id_venta), LOTES_UNIDADES,
              *(clave_stock(id_sucursal, p) for p in productos)]
    argumentos = [id_venta, score_fecha(hoy), *(cantidades[p] for p in productos)]
    resultado = json.loads(_script(_DESCONTAR)(keys=claves, args=argumentos))

    if resultado["estado"] == "ya_descontada":
        raise ErrorDeValidacion(f"el stock de la venta {id_venta} ya se descontó")
    if resultado["estado"] == "insuficiente":
        detalle = "; ".join(
            f"{f['stock'].rsplit(':', 1)[1]}: pide {f['pedido']}, hay {f['disponible']}"
            for f in resultado["faltantes"]
        )
        raise ErrorDeValidacion(f"stock vigente insuficiente en {id_sucursal} ({detalle})")
    return [
        {"_id": paso["id_lote"], "id_producto": paso["id_producto"],
         "vencimiento": date.fromisoformat(paso["vencimiento"]),
         "antes": paso["antes"], "descontadas": paso["descontadas"], "despues": paso["despues"]}
        for paso in resultado["lotes"]
    ]


def reponer(id_venta: str) -> int:
    """Devuelve a los lotes lo que `descontar` les quitó a `id_venta`.

    Es la compensación de q14 cuando MongoDB no confirma la venta. Retorna la
    cantidad de lotes repuestos (0 si la venta no tenía un descuento registrado).
    """
    claves = [VENTAS_DESCONTADAS, clave_descuento(id_venta), LOTES_UNIDADES]
    return _script(_REPONER)(keys=claves, args=[id_venta])
