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

## Cargar los datos

```bash
python -m farmared.carga
```

Carga los CSV de `datos/provistos/` y `datos/adicionales/` en MongoDB y en Redis. Se puede correr cuantas veces se quiera: cada vez deja exactamente el estado de los CSV y descarta lo que hayan cambiado los servicios de escritura. Si los datos tienen un error, por ejemplo una referencia a un id inexistente, lo informa y no modifica ninguna base. Detalle en [`docs/informe/carga.md`](docs/informe/carga.md).

Los datos persisten en volúmenes de Docker entre reinicios. Para vaciar las bases por completo:

```bash
mongosh "$MONGO_URI" --quiet --eval 'db.getSiblingDB("farmared").dropDatabase()'
redis-cli -h redis FLUSHDB
```

## Ejecutar las consultas

Cada consulta es un módulo de `farmared/consultas/` y se ejecuta desde la terminal del contenedor `app`, después de la carga:

```bash
python -m farmared.consultas.qNN [argumentos]
```

`python -m farmared.consultas.qNN --help` muestra los argumentos de las consultas que los tienen.

| # | Consulta | Ejemplo |
|---|---|---|
| 13 | ABM de clientes | `python -m farmared.consultas.q13 alta --nombre Ana --apellido Paz --dni 40111222 --email ana.paz@example.com --telefono 1140001111 --ciudad "Buenos Aires" --provincia "Buenos Aires" --obra-social OSDE --nro-afiliado OS-500100` |
| | | `python -m farmared.consultas.q13 modificar C021 --telefono 1140002222 --obra-social "Sin cobertura" --nro-afiliado ""` |
| | | `python -m farmared.consultas.q13 baja C021` |

## Estado

| Parte | Estado |
|---|---|
| Datasets provistos | En [`datos/provistos/`](datos/provistos/) |
| Elección de motores y justificación | Propuesta en [`docs/arquitectura.md`](docs/arquitectura.md) |
| División del trabajo | Propuesta en [`docs/division.md`](docs/division.md) |
| Modelo de datos | Borrador en [`docs/modelo.md`](docs/modelo.md) |
| Entorno en Codespaces | Listo |
| Script de carga | Listo |
| Registros adicionales (≥ 10 por colección/tabla) | Clientes, sucursales, farmacéuticos y proveedores listos; faltan productos, lotes, recetas, ventas y detalle |
| Consultas | q13 lista; faltan q01–q12, q14 y q15 |
| Informe PDF | Secciones de entorno, carga y q13 en [`docs/informe/`](docs/informe/) |

## Estructura

```
.devcontainer/      devcontainer de Codespaces (imagen de app con mongosh y redis-cli)
docker-compose.yml  servicios app, mongo y redis
requirements.txt    dependencias de Python
farmared/
  conexiones.py     get_mongo(), get_mongo_client() y get_redis()
  verificar.py      chequeo del entorno
  carga.py          carga idempotente de los CSV
  stock.py          claves del stock en Redis
  errores.py        ErrorDeValidacion, para los servicios de escritura
  salida.py         impresión de resultados como JSON
  consultas/        q01–q15, un módulo por consulta
datos/
  provistos/        CSV entregados por la cátedra, sin modificar
  adicionales/      registros propios del equipo, mismo formato
docs/               arquitectura, división del trabajo y modelo de datos
  informe/          secciones del informe PDF
```

## Datos

Ver [`datos/README.md`](datos/README.md).
