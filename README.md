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

Carga los CSV de `datos/provistos/` y `datos/adicionales/` en MongoDB y en Redis. Se puede correr cuantas veces se quiera: cada vez deja exactamente el estado de los CSV y descarta lo que hayan cambiado los servicios de escritura. Si los datos tienen un error, por ejemplo una referencia a un id inexistente, lo informa y no modifica ninguna base. Detalle en la sección 4 de [`docs/informe.md`](docs/informe.md).

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
| 1 | Productos activos con su proveedor | `python -m farmared.consultas.q01` |
| 2 | Ventas pendientes con su farmacéutico | `python -m farmared.consultas.q02` |
| 3 | Historial de un cliente: ventas y recetas por fecha | `python -m farmared.consultas.q03 C001` |
| 4 | Clientes con más de una receta, con la cantidad | `python -m farmared.consultas.q04` (opcional: `--minimo 3`) |
| 5 | Farmacéuticos activos y sus ventas de los últimos 60 días, con los ceros | `python -m farmared.consultas.q05` (opcional: `--hoy 2026-11-14 --dias 30`) |
| 6 | Recetas prolongadas vigentes con la próxima dispensa vencida | `python -m farmared.consultas.q06` (opcional: `--hoy 2026-10-13`) |
| 7 | Top 5 de productos más vendidos en unidades | `python -m farmared.consultas.q07` (opcional: `--limite 10`) |
| 8 | Lotes con menos de 50 unidades, con producto, sucursal y proveedor | `python -m farmared.consultas.q08` (opcional: `--umbral 20 --hoy 2026-10-13`) |
| 9 | Ventas libres de menos de $5.000, sin anuladas | `python -m farmared.consultas.q09` |
| 10 | Clientes atendidos en una sucursal, vía el farmacéutico | `python -m farmared.consultas.q10 S001` |
| 11 | Vista de ingresos por farmacéutico en el mes actual | `python -m farmared.consultas.q11` (opcional: `--hoy 2026-11-14`, `--recrear`) |
| 12 | Clientes sin ventas registradas en el último año | `python -m farmared.consultas.q12` (opcional: `--hoy 2026-11-14 --dias 365`) |
| 13 | ABM de clientes | `python -m farmared.consultas.q13 alta --nombre Ana --apellido Paz --dni 40111222 --email ana.paz@example.com --telefono 1140001111 --ciudad "Buenos Aires" --provincia "Buenos Aires" --obra-social OSDE --nro-afiliado OS-500100` |
| | | `python -m farmared.consultas.q13 modificar C021 --telefono 1140002222 --obra-social "Sin cobertura" --nro-afiliado ""` |
| | | `python -m farmared.consultas.q13 baja C021` |
| 14 | Registro de una venta "Completada" (descuenta stock con q15) | `python -m farmared.consultas.q14 --cliente C011 --farmaceutico F001 --item PRD003:20 --item PRD001:35 --medio-pago "Obra social" --receta RC012` |
| 15 | Descuento de stock FEFO de una venta registrada | `python -m farmared.consultas.q15 V030` (opcional: `--hoy 2026-11-14`) |

## Estado

| Parte | Estado |
|---|---|
| Datasets provistos | En [`datos/provistos/`](datos/provistos/) |
| Elección de motores y justificación | Sección 1 de [`docs/informe.md`](docs/informe.md) |
| División del trabajo | Propuesta en [`docs/division.md`](docs/division.md) |
| Modelo de datos | Sección 2 de [`docs/informe.md`](docs/informe.md), con diagramas |
| Entorno en Codespaces | Listo |
| Script de carga | Listo |
| Registros adicionales (≥ 10 por colección/tabla) | Listos: clientes, sucursales, farmacéuticos, proveedores, productos, lotes, recetas, ventas y detalle |
| Consultas | Las 15 listas |
| Informe | [`docs/informe.md`](docs/informe.md): faltan la carátula y las conclusiones |

## Estructura

```
.devcontainer/      devcontainer de Codespaces (imagen de app con mongosh y redis-cli)
docker-compose.yml  servicios app, mongo y redis
requirements.txt    dependencias de Python
farmared/
  conexiones.py     get_mongo(), get_mongo_client() y get_redis()
  verificar.py      chequeo del entorno
  carga.py          carga idempotente de los CSV
  stock.py          claves del stock en Redis y scripts Lua de descuento y reposición
  errores.py        ErrorDeValidacion, para los servicios de escritura
  salida.py         impresión de resultados como JSON
  fechas.py         "hoy" y conversión a fecha de MongoDB
  consultas/        q01–q15, un módulo por consulta
datos/
  provistos/        CSV entregados por la cátedra, sin modificar
  adicionales/      registros propios del equipo, mismo formato
docs/
  informe.md        informe del TPO (arquitectura, modelo, carga, consultas, consistencia)
  division.md       división del trabajo y dudas para la cátedra
```

## Datos

Ver [`datos/README.md`](datos/README.md).
