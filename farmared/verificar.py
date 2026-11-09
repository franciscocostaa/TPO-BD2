"""Chequeo del entorno: `python -m farmared.verificar`.

Comprueba lo que necesitan las consultas, en particular las transacciones
de MongoDB y los scripts Lua de Redis que usan q14 y q15.
"""

import sys
import uuid

from farmared.conexiones import get_mongo, get_mongo_client, get_redis


def mongo_ping() -> str:
    get_mongo_client().admin.command("ping")
    return "responde"


def mongo_replica_set() -> str:
    estado = get_mongo_client().admin.command("replSetGetStatus")
    primarios = [m["name"] for m in estado["members"] if m["stateStr"] == "PRIMARY"]
    if not primarios:
        raise RuntimeError(f"replica set {estado['set']} sin primario")
    return f"{estado['set']}, primario {primarios[0]}"


def mongo_transaccion() -> str:
    coleccion = get_mongo()["_verificacion"]
    marca = str(uuid.uuid4())
    with get_mongo_client().start_session() as sesion:
        sesion.start_transaction()
        coleccion.insert_one({"marca": marca}, session=sesion)
        sesion.abort_transaction()
    if coleccion.find_one({"marca": marca}) is not None:
        raise RuntimeError("el insert abortado quedó persistido")
    coleccion.drop()
    return "abort deshace el insert"


def redis_ping() -> str:
    get_redis().ping()
    return "responde"


def redis_aof() -> str:
    valor = get_redis().config_get("appendonly")["appendonly"]
    if valor != "yes":
        raise RuntimeError(f"appendonly = {valor}")
    return "appendonly = yes"


def redis_lua() -> str:
    r = get_redis()
    clave = f"_verificacion:{uuid.uuid4()}"
    try:
        resultado = r.eval("return redis.call('INCRBY', KEYS[1], ARGV[1])", 1, clave, 5)
    finally:
        r.delete(clave)
    if resultado != 5:
        raise RuntimeError(f"el script devolvió {resultado}")
    return "EVAL ejecuta scripts"


CHEQUEOS = [
    ("MongoDB: conexión", mongo_ping),
    ("MongoDB: replica set", mongo_replica_set),
    ("MongoDB: transacciones", mongo_transaccion),
    ("Redis: conexión", redis_ping),
    ("Redis: persistencia AOF", redis_aof),
    ("Redis: scripts Lua", redis_lua),
]


def main() -> int:
    fallas = 0
    for nombre, chequeo in CHEQUEOS:
        try:
            print(f"✔ {nombre}: {chequeo()}")
        except Exception as error:
            fallas += 1
            print(f"✘ {nombre}: {error}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
