"""Fecha de hoy y conversión de fechas para las consultas (ver `docs/modelo.md`).

La carga guarda cada fecha del CSV como `Date` de MongoDB a las 00:00 UTC de
ese día. Para comparar con "hoy", la fecha de hoy se convierte de la misma
forma con `a_mongo`.
"""

from datetime import date, datetime


def hoy() -> date:
    """Fecha del sistema. El contenedor corre con TZ=America/Argentina/Buenos_Aires."""
    return date.today()


def a_mongo(dia: date) -> datetime:
    """`dia` a las 00:00, como guarda la carga las fechas en MongoDB."""
    return datetime(dia.year, dia.month, dia.day)
