"""q13 — ABM de clientes.

Propósito: alta de clientes validando DNI único, modificación de los datos de
contacto y cobertura, y baja lógica (`activo: false`; nunca se borra).

Motor: MongoDB, colección `clientes`. La unicidad del DNI la garantiza el
índice único sobre `dni` (lo crea la carga), así que dos altas simultáneas con
el mismo DNI no pueden quedar ambas registradas.

Cada operación devuelve el documento del cliente tal como quedó, y lanza
`ErrorDeValidacion` sin modificar nada si el pedido viola una regla.

Uso desde la terminal:

    python -m farmared.consultas.q13 alta --nombre Ana --apellido Paz --dni 40111222 \\
        --email ana@example.com --telefono 1140001111 --ciudad "Buenos Aires" \\
        --provincia "Buenos Aires" --obra-social OSDE --nro-afiliado OS-1
    python -m farmared.consultas.q13 modificar C021 --telefono 1140002222
    python -m farmared.consultas.q13 baja C021
"""

import argparse
import re
import sys

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from farmared.conexiones import get_mongo
from farmared.errores import ErrorDeValidacion
from farmared.salida import imprimir

OBRAS_SOCIALES = {"OSDE", "Swiss Medical", "PAMI", "IOMA", "Galeno", "Sin cobertura"}
SIN_COBERTURA = "Sin cobertura"
CAMPOS_MODIFICABLES = ("email", "telefono", "ciudad", "provincia", "obra_social", "nro_afiliado")

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_ID = re.compile(r"C(\d+)")


def _texto(campo: str, valor: str) -> str:
    valor = (valor or "").strip()
    if not valor:
        raise ErrorDeValidacion(f"{campo} no puede estar vacío")
    return valor


def _normalizar(campo: str, valor: str | None) -> str | None:
    """Valida y normaliza un campo de contacto o cobertura."""
    if campo == "nro_afiliado":
        return (valor or "").strip() or None
    valor = _texto(campo, valor)
    if campo == "email" and not _EMAIL.fullmatch(valor):
        raise ErrorDeValidacion(f"email inválido: {valor!r}")
    if campo == "telefono" and not valor.isdigit():
        raise ErrorDeValidacion(f"el teléfono solo admite dígitos: {valor!r}")
    if campo == "obra_social" and valor not in OBRAS_SOCIALES:
        raise ErrorDeValidacion(f"obra social inválida: {valor!r}; opciones: {', '.join(sorted(OBRAS_SOCIALES))}")
    return valor


def _validar_cobertura(obra_social: str, nro_afiliado: str | None) -> None:
    if obra_social == SIN_COBERTURA and nro_afiliado is not None:
        raise ErrorDeValidacion("un cliente sin cobertura no lleva número de afiliado")
    if obra_social != SIN_COBERTURA and nro_afiliado is None:
        raise ErrorDeValidacion(f"falta el número de afiliado de {obra_social}")


def _siguiente_id(clientes) -> str:
    numeros = [int(m[1]) for doc in clientes.find({}, {"_id": 1}) if (m := _ID.fullmatch(doc["_id"]))]
    return f"C{max(numeros, default=0) + 1:03d}"


def _cliente_activo(id_cliente: str) -> dict:
    cliente = get_mongo().clientes.find_one({"_id": id_cliente})
    if cliente is None:
        raise ErrorDeValidacion(f"no existe el cliente {id_cliente}")
    if not cliente["activo"]:
        raise ErrorDeValidacion(f"el cliente {id_cliente} está dado de baja")
    return cliente


def alta(nombre: str, apellido: str, dni: str, email: str, telefono: str,
         ciudad: str, provincia: str, obra_social: str, nro_afiliado: str | None = None) -> dict:
    """Da de alta un cliente activo con el siguiente id de la serie (C021, C022…).

    Parámetros: los campos de `clientes.csv` salvo `id_cliente` y `activo`.
    `nro_afiliado` es obligatorio salvo con `obra_social="Sin cobertura"`, donde debe omitirse.

    Retorna el documento insertado. Rechaza un DNI que no sea de 7 u 8 dígitos o
    que ya esté registrado, aunque sea de un cliente dado de baja.
    """
    dni = _texto("dni", dni)
    if not (dni.isdigit() and 7 <= len(dni) <= 8):
        raise ErrorDeValidacion(f"el DNI debe tener 7 u 8 dígitos: {dni!r}")
    cliente = {
        "nombre": _texto("nombre", nombre),
        "apellido": _texto("apellido", apellido),
        "dni": dni,
        "email": _normalizar("email", email),
        "telefono": _normalizar("telefono", telefono),
        "ciudad": _normalizar("ciudad", ciudad),
        "provincia": _normalizar("provincia", provincia),
        "obra_social": _normalizar("obra_social", obra_social),
        "nro_afiliado": _normalizar("nro_afiliado", nro_afiliado),
        "activo": True,
    }
    _validar_cobertura(cliente["obra_social"], cliente["nro_afiliado"])

    clientes = get_mongo().clientes
    while True:
        documento = {"_id": _siguiente_id(clientes), **cliente}
        try:
            clientes.insert_one(documento)
            return documento
        except DuplicateKeyError as error:
            if "dni" in error.details.get("keyPattern", {}):
                existente = clientes.find_one({"dni": dni})
                estado = "activo" if existente["activo"] else "dado de baja"
                raise ErrorDeValidacion(f"el DNI {dni} ya está registrado ({existente['_id']}, {estado})") from None
            # Otra alta tomó el mismo id al mismo tiempo: se calcula el siguiente y se reintenta.


def modificar(id_cliente: str, **cambios: str | None) -> dict:
    """Modifica datos de contacto y cobertura de un cliente activo.

    Parámetros: `id_cliente` y uno o más de `email`, `telefono`, `ciudad`,
    `provincia`, `obra_social` y `nro_afiliado`. Nombre, apellido y DNI no se
    modifican. Al pasar a "Sin cobertura" hay que vaciar `nro_afiliado`
    (`nro_afiliado=None`); al pasar a una obra social, informarlo.

    Retorna el documento modificado.
    """
    invalidos = sorted(set(cambios) - set(CAMPOS_MODIFICABLES))
    if invalidos:
        raise ErrorDeValidacion(f"no se pueden modificar: {', '.join(invalidos)}")
    if not cambios:
        raise ErrorDeValidacion("no se indicó ningún cambio")
    cambios = {campo: _normalizar(campo, valor) for campo, valor in cambios.items()}
    actual = _cliente_activo(id_cliente)
    resultado = {**actual, **cambios}
    _validar_cobertura(resultado["obra_social"], resultado["nro_afiliado"])

    documento = get_mongo().clientes.find_one_and_update(
        {"_id": id_cliente, "activo": True},
        {"$set": cambios},
        return_document=ReturnDocument.AFTER,
    )
    if documento is None:
        raise ErrorDeValidacion(f"el cliente {id_cliente} se dio de baja durante la modificación")
    return documento


def baja(id_cliente: str) -> dict:
    """Baja lógica: marca al cliente con `activo: false`. Sus ventas y recetas no cambian.

    Parámetros: `id_cliente`. Retorna el documento dado de baja. Rechaza un
    cliente inexistente o ya dado de baja.
    """
    documento = get_mongo().clientes.find_one_and_update(
        {"_id": id_cliente, "activo": True},
        {"$set": {"activo": False}},
        return_document=ReturnDocument.AFTER,
    )
    if documento is None:
        _cliente_activo(id_cliente)
    return documento


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m farmared.consultas.q13", description="ABM de clientes")
    operaciones = parser.add_subparsers(dest="operacion", required=True)

    p_alta = operaciones.add_parser("alta", help="alta de un cliente")
    for campo in ("nombre", "apellido", "dni", "email", "telefono", "ciudad", "provincia"):
        p_alta.add_argument(f"--{campo}", required=True)
    p_alta.add_argument("--obra-social", dest="obra_social", required=True)
    p_alta.add_argument("--nro-afiliado", dest="nro_afiliado")

    p_modificar = operaciones.add_parser("modificar", help="modificación de contacto y cobertura")
    p_modificar.add_argument("id_cliente")
    for campo in CAMPOS_MODIFICABLES:
        p_modificar.add_argument(f"--{campo.replace('_', '-')}", dest=campo,
                                 help='"" para vaciar' if campo == "nro_afiliado" else None)

    p_baja = operaciones.add_parser("baja", help="baja lógica")
    p_baja.add_argument("id_cliente")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = vars(_argumentos(argv))
    operacion = args.pop("operacion")
    try:
        if operacion == "alta":
            resultado = alta(**args)
        elif operacion == "modificar":
            id_cliente = args.pop("id_cliente")
            resultado = modificar(id_cliente, **{c: v for c, v in args.items() if v is not None})
        else:
            resultado = baja(args["id_cliente"])
    except ErrorDeValidacion as error:
        print(f"✘ Rechazado: {error}")
        return 1
    imprimir(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
