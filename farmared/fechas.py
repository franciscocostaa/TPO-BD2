"""Fecha de hoy y conversión de fechas para las consultas.

La carga guarda cada fecha del CSV como `Date` de MongoDB a las 00:00 UTC de
ese día. Para comparar con "hoy", la fecha de hoy se convierte de la misma
forma con `a_mongo`.

"Hoy" es el día en la hora de la red de farmacias (`ZONA_HORARIA`), no en UTC.
El contenedor corre con `TZ` en esa zona, así que `date.today()` ya la usa; la
vista de q11, que calcula el mes dentro de MongoDB, la recibe explícitamente.
"""

import os
from datetime import date, datetime

ZONA_HORARIA = os.environ.get("TZ", "America/Argentina/Buenos_Aires")


def hoy() -> date:
    """Fecha del sistema en `ZONA_HORARIA` (el contenedor corre con esa `TZ`)."""
    return date.today()


def a_mongo(dia: date) -> datetime:
    """`dia` a las 00:00, como guarda la carga las fechas en MongoDB."""
    return datetime(dia.year, dia.month, dia.day)
