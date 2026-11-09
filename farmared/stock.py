"""Claves del stock por lote en Redis (ver `docs/modelo.md`).

- `lote:{id_lote}`: hash con `id_producto`, `id_sucursal`, `nro_lote`, `unidades` y `vencimiento`.
- `stock:{id_sucursal}:{id_producto}`: sorted set de lotes con score = vencimiento como AAAAMMDD.
- `lotes:unidades`: sorted set de todos los lotes con score = unidades.
"""

from datetime import date

LOTES_UNIDADES = "lotes:unidades"


def clave_lote(id_lote: str) -> str:
    return f"lote:{id_lote}"


def clave_stock(id_sucursal: str, id_producto: str) -> str:
    return f"stock:{id_sucursal}:{id_producto}"


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
