"""Conexiones compartidas a MongoDB y Redis.

La configuración sale de variables de entorno; los valores por defecto
coinciden con los servicios de docker-compose.yml.
"""

import os
from functools import cache

import redis
from pymongo import MongoClient
from pymongo.database import Database

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017/?replicaSet=rs0")
MONGO_DB = os.environ.get("MONGO_DB", "farmared")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


@cache
def get_mongo_client() -> MongoClient:
    """Cliente de MongoDB, necesario para abrir sesiones y transacciones."""
    return MongoClient(MONGO_URI)


def get_mongo() -> Database:
    """Base de datos de FarmaRed en MongoDB."""
    return get_mongo_client()[MONGO_DB]


@cache
def get_redis() -> redis.Redis:
    """Cliente de Redis con respuestas decodificadas como str."""
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)
