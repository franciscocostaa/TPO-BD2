"""Errores compartidos por los servicios de escritura."""


class ErrorDeValidacion(Exception):
    """El pedido viola una regla de negocio y se rechaza sin modificar datos."""
