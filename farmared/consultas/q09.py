"""q09 — Ventas de venta libre con total menor a $5.000, sin anuladas.

Propósito: listar las ventas de tipo "Venta libre" cuyo total es menor a
$5.000, excluyendo las que están en estado "Anulada". Las "Pendiente" sí se
listan: son ventas registradas, aunque todavía no computen ingresos.

Motor: MongoDB, colección `ventas`. Es un filtro sobre un único documento por
venta: los ítems están embebidos, así que cada resultado ya trae su detalle
sin combinar colecciones (Clase 13).

Parámetros: `tope` (opcional, por defecto 5000): el total tiene que ser
estrictamente menor.

Retorna la lista de ventas completas, con sus ítems, ordenada por fecha y,
dentro del mismo día, por id.

Uso desde la terminal:

    python -m farmared.consultas.q09
"""

import sys

from farmared.conexiones import get_mongo
from farmared.salida import imprimir

TOPE = 5000


def ejecutar(tope: int = TOPE) -> list[dict]:
    """Ventas "Venta libre" no anuladas con `total < tope`."""
    filtro = {"tipo": "Venta libre", "total": {"$lt": tope}, "estado": {"$ne": "Anulada"}}
    return list(get_mongo().ventas.find(filtro).sort([("fecha", 1), ("_id", 1)]))


def main() -> int:
    imprimir(ejecutar())
    return 0


if __name__ == "__main__":
    sys.exit(main())
