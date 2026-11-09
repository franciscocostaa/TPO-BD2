# TPO Bases de Datos II — FarmaRed

Sistema de gestión para una red de farmacias con persistencia políglota: **MongoDB** como sistema de registro y **Redis** para el stock por lote. Trabajo Práctico Obligatorio, Bases de Datos II (ITBA), 2.º cuatrimestre de 2026.

## Integrantes

| Nombre | Usuario de GitHub |
|---|---|
| | [@franciscocostaa](https://github.com/franciscocostaa) |
| | |
| | |
| | |

## Levantar el entorno

### GitHub Codespaces

1. En GitHub: **Code → Codespaces → Create codespace on main**.
2. Esperar a que termine de construir. Levanta tres contenedores: `app` (Python 3.12, donde se trabaja), `mongo` (MongoDB 8.0 como replica set `rs0`) y `redis` (Redis 7.4 con AOF), e instala las dependencias.
3. En la terminal del Codespace:

```bash
python -m farmared.verificar
```

Tienen que aparecer seis ✔: conexión, replica set y transacciones en MongoDB; conexión, persistencia AOF y scripts Lua en Redis.

### VS Code local

Con Docker y la extensión **Dev Containers**: abrir la carpeta del repo y elegir **Reopen in Container**. El entorno es el mismo que en Codespaces.

### Consolas

Desde la terminal del contenedor `app`:

```bash
mongosh "$MONGO_URI"      # MongoDB
redis-cli -h redis        # Redis
```

### Vaciar los datos

Los datos persisten en volúmenes de Docker entre reinicios. Para empezar de cero:

```bash
mongosh "$MONGO_URI" --quiet --eval 'db.getSiblingDB("farmared").dropDatabase()'
redis-cli -h redis FLUSHDB
```

## Estado

| Parte | Estado |
|---|---|
| Datasets provistos | Cargados en [`datos/provistos/`](datos/provistos/) |
| Elección de motores y justificación | Propuesta en [`docs/arquitectura.md`](docs/arquitectura.md) |
| División del trabajo | Propuesta en [`docs/division.md`](docs/division.md) |
| Entorno en Codespaces | Listo |
| Registros adicionales (≥ 10 por colección/tabla) | Pendiente |
| Scripts de carga | Pendiente |
| Consultas `q01`–`q15` | Pendiente |
| Informe PDF | Pendiente |

## Estructura

```
.devcontainer/      devcontainer de Codespaces (imagen de app con mongosh y redis-cli)
docker-compose.yml  servicios app, mongo y redis
requirements.txt    dependencias de Python
farmared/
  conexiones.py     get_mongo(), get_mongo_client() y get_redis()
  verificar.py      chequeo del entorno
  consultas/        q01–q15, un módulo por consulta
datos/
  provistos/        CSV entregados por la cátedra, sin modificar
docs/               arquitectura y división del trabajo
```

## Datos

Ver [`datos/README.md`](datos/README.md).
