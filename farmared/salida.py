"""Impresión de resultados de las consultas en la terminal."""

import json
from datetime import date, datetime


def _serializar(valor):
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    raise TypeError(f"no se puede imprimir {type(valor).__name__}")


def imprimir(resultado) -> None:
    """Imprime documentos, listas o valores como JSON legible. Las fechas salen como AAAA-MM-DD."""
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=_serializar))
