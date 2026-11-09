# Entorno

El entorno se levanta completo en GitHub Codespaces a partir de `.devcontainer/` y `docker-compose.yml`, sin pasos manuales: al crear el Codespace quedan los motores corriendo, las dependencias instaladas y las consolas disponibles. El mismo devcontainer funciona en VS Code local con la extensión Dev Containers.

Cada motor corre en su propio contenedor, a partir de una imagen oficial con la versión fijada. Así el entorno es el mismo en cualquier máquina (Clase I, pp. 8–9).

## Servicios

| Servicio | Imagen | Configuración | Por qué |
|---|---|---|---|
| `app` | Python 3.12 (imagen de devcontainers) + `mongosh` + `redis-cli` | Monta el repositorio en `/workspaces/TPO-BD2`. Define `MONGO_URI`, `MONGO_DB`, `REDIS_URL` y `TZ=America/Argentina/Buenos_Aires`. Arranca cuando `mongo` y `redis` están sanos. | Es donde se trabaja y se ejecutan la carga y las consultas. La zona horaria hace que "hoy" sea el día argentino. |
| `mongo` | `mongo:8.0` | Replica set `rs0` de un nodo. | Las transacciones de varios documentos, que usan la carga y q14, requieren un replica set. |
| `redis` | `redis:7.4` | AOF con `appendfsync everysec`, más los snapshots RDB por defecto. | El stock vive solo en Redis: sin persistencia, un reinicio lo perdería. AOF + RDB es la combinación que aconseja la clase, y con fsync por segundo se pierde a lo sumo un segundo de escrituras (Clase 17, pp. 17–21). |

*Complemento (no está en las clases):*
- `docker-compose`, el devcontainer y los volúmenes con nombre.
- El replica set de un nodo. Ver el [manual de transacciones de MongoDB](https://www.mongodb.com/docs/manual/core/transactions/).

## Replica set sin pasos manuales

Un replica set nuevo hay que iniciarlo una vez con `rs.initiate`. Lo hace el healthcheck del servicio `mongo`:

1. Si `rs.status()` falla, el nodo todavía no es parte de un replica set, así que lo inicia.
2. El servicio recién queda sano cuando el nodo es primario y acepta escrituras.

`app` espera esa condición para arrancar. En los reinicios, el replica set ya existe y el paso 1 no hace nada.

## Persistencia

Los datos se guardan en tres volúmenes con nombre (`mongo-data`, `mongo-config`, `redis-data`), así que sobreviven a reinicios y a reconstrucciones del contenedor. No se publican puertos: `app` se conecta a `mongo` y `redis` por la red interna de compose.

## Verificación

`python -m farmared.verificar` comprueba lo que necesitan la carga y las consultas:

```text
✔ MongoDB: conexión: responde
✔ MongoDB: replica set: rs0, primario mongo:27017
✔ MongoDB: transacciones: abort deshace el insert
✔ Redis: conexión: responde
✔ Redis: persistencia AOF: appendonly = yes
✔ Redis: scripts Lua: EVAL ejecuta scripts
```

La prueba de transacciones inserta un documento dentro de una transacción, la aborta y comprueba que no quedó. La de Lua ejecuta un `EVAL` sobre una clave temporal.

## Limitaciones

- El replica set de un nodo habilita las transacciones, pero no da alta disponibilidad: si se cae el nodo, se cae la base.
- Con fsync por segundo, una caída de Redis puede perder hasta un segundo de descuentos de stock ya confirmados en MongoDB (Clase 17, p. 21). *Complemento (no está en las clases):* `appendfsync always` lo evitaría a costa de un fsync por cada escritura.
