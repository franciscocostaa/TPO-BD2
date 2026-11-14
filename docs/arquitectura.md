# Propuesta de arquitectura — TPO FarmaRed

**Propuesta:** MongoDB como sistema de registro y Redis para el stock por lote, con Python como lenguaje.

Este documento explica por qué, qué alternativas evaluamos y cómo resolvemos el punto más delicado de la consigna: que las consultas 14 y 15 sean todo o nada. Las referencias citan las clases de la cátedra (ver [Fuentes](#fuentes)).

## 1. Qué nos piden

- Backoffice para una red de farmacias sobre **al menos dos motores NoSQL de paradigmas distintos**, con una justificación técnica para cada entidad o caso de uso (vale 25 % de la nota). (Consigna, pp. 1, 5)
- Entorno en GitHub Codespaces, carga idempotente desde los CSV más **≥ 10 registros propios por colección**, y las 15 consultas en módulos `q01`–`q15`. (Consigna, pp. 2, 5–7)
- **Consultas 14 + 15:** se registra una venta validando cliente, farmacéutico, productos y receta, y se descuenta el stock con FEFO sin usar lotes vencidos. Si algún ítem no alcanza, **no puede quedar nada modificado**: ni la venta, ni la receta, ni los lotes. El informe tiene que explicar la estrategia según las garantías de cada motor. (Consigna, p. 7)

La consigna adelanta las características de cada dato:

| Dato | Característica |
|---|---|
| Ventas y detalle | Jerárquico (cabecera con ítems variables); consultas por cliente, farmacéutico y fecha; muchas inserciones. |
| Stock por lote | Actualizaciones frecuentes y concurrentes; nunca negativo; prioridad por vencimiento. |
| Clientes, recetas, farmacéuticos | ABM con baja lógica; relaciones que se recorren en el historial. |
| Catálogo y proveedores | Pocos cambios, muchas lecturas. |
| Reportes | Totales, rankings, conteos por período. |

(Consigna, p. 5)

## 2. Criterio de elección

La cátedra plantea que la persistencia políglota consiste en usar la tecnología adecuada para cada necesidad. La elección tiene que pesar modelo, consistencia, durabilidad, escalabilidad, complejidad operativa y capacidades del equipo, y **cada motor agregado suma costo de integración, despliegue y mantenimiento**. (Clase I, pp. 4–6)

Por eso buscamos el **mínimo de motores (dos)** que cubra bien todos los casos, y que cada uno tenga un rol que no pueda cumplir el otro.

## 3. Evaluación de los motores vistos en la materia

| Motor | A favor para FarmaRed | En contra para FarmaRed |
|---|---|---|
| **MongoDB** | Embeber los ítems en la venta permite leerla y escribirla en una sola operación atómica (Clase 13, pp. 3–8). `$lookup` (Clase 13, pp. 21–24), pipelines de agregación y vistas (Clase 12, pp. 50–52). | La atomicidad vista en clase es por documento: venta y receta son dos documentos (Clase 13, p. 5). |
| **Redis** | Los scripts Lua se ejecutan de forma atómica y ningún otro cliente se atiende en el medio (Clase 17, p. 31). Los sorted sets ordenan por score (Clase 18, pp. 14–15): con el vencimiento como score, FEFO sale solo. Es muy rápido (Clase 18, pp. 34–35). | La clase lo desaconseja para relaciones y para transacciones de varias operaciones (Clase 17, pp. 6–7). `MULTI` no tiene rollback (Clase 17, p. 12; Clase 18, p. 7). Vive en memoria, así que hay que activar AOF (Clase 17, pp. 17–24). |
| **Neo4j** | ACID (Clase 16, pp. 15–16). Recorre relaciones sin joins (Clase 16, p. 39). `MERGE` + restricciones de unicidad (Anexo Neo4j, pp. 2–5). | Replica el grafo completo, sin fragmentarlo, lo que limita el tamaño (Clase 16, pp. 39–40). Mayor curva de modelado. |
| **Cassandra** | Escrituras masivas, una tabla por consulta (Clase 15, pp. 16–19). | Sin joins ni subconsultas (Clase 15, pp. 13, 19). La clase la desaconseja para sistemas que requieren ACID (Clase 15, p. 6). Pesada para Codespaces. |
| **DynamoDB** | Clave de partición y ordenamiento, más LSI y GSI para consultar por cliente y fecha (Clase 20, pp. 6, 17–19). | Según la clase, consistencia solo a nivel de ítem, sin operaciones atómicas entre ítems (Clase 20, p. 6). Sin agregaciones; modelado y capacidad complejos (Clase 20, pp. 32–33). |

**Descartadas:** Cassandra y DynamoDB, porque fallan justo en lo que más pesa: la consistencia de 14 + 15 y los reportes.

## 4. Arquitectura elegida: MongoDB + Redis

### Qué guarda cada motor

**MongoDB — sistema de registro**

| Colección | Modelo |
|---|---|
| `ventas` | Los ítems van **embebidos** en la venta: es una relación "contiene" y siempre se leen juntos (Clase 13, pp. 3–8). Índices por cliente, farmacéutico y fecha. |
| `recetas` | Documento propio con referencia al cliente: un cliente acumula recetas sin límite, y referenciar desde el hijo evita un arreglo que crece (Clase 13, pp. 16–20). |
| `productos`, `proveedores` | El producto referencia a su proveedor y se combinan con `$lookup` para la consulta 1. |
| `clientes`, `farmaceuticos`, `sucursales` | Documentos con baja lógica (`activo`). |

**Redis — stock por lote**

| Clave | Tipo | Uso |
|---|---|---|
| `lote:{id}` | Hash | Unidades, vencimiento, número de lote, producto, sucursal. |
| `stock:{sucursal}:{producto}` | Sorted set | Lotes con score = vencimiento → orden FEFO. |
| `lotes:unidades` | Sorted set | Lotes con score = unidades → consulta 8 (menos de 50). |

Persistencia **AOF con fsync cada segundo más snapshots RDB**: es la combinación que recomienda la clase, y con ella se pierde a lo sumo un segundo ante una caída (Clase 17, pp. 18–24).

### Por qué cada dato va donde va

- **Ventas → MongoDB.** Son jerárquicas, crecen mucho y se consultan y agregan por cliente, farmacéutico y fecha. Embeber los ítems da una lectura y una escritura atómica por venta (Clase 13, pp. 3–8). Los reportes (consultas 4, 5, 7 y 11) son pipelines de agregación, y la consulta 11 pide una vista, que MongoDB tiene (Clase 12, pp. 50–52).
- **Stock → Redis.** Es el dato con más escrituras concurrentes y una invariante dura: nunca negativo y FEFO. Un script Lua evalúa todos los ítems y descuenta solo si alcanzan todos, de forma atómica y sin otro cliente en el medio (Clase 17, p. 31). El sorted set por vencimiento resuelve FEFO sin ordenar en la aplicación (Clase 18, pp. 14–15).
- **Clientes, recetas, catálogo → MongoDB.** Las relaciones que se recorren en el historial (consultas 3 y 10) se resuelven con referencias y `$lookup` (Clase 13, pp. 21–24). El catálogo es poco volátil y de lectura frecuente.

Sobre la advertencia de la clase de que las bases clave-valor no convienen para transacciones de varias operaciones (Clase 17, pp. 6–7): a Redis no le pedimos una transacción entre entidades, sino **una única operación atómica sobre el stock**, que es lo que garantiza un script Lua.

### Cómo se reparten las consultas

| Motor | Consultas |
|---|---|
| Solo MongoDB | 1, 2, 3, 4, 5, 6, 7, 9, 10, 11 (vista), 12, 13 |
| Redis + MongoDB | 8 (lotes de Redis enriquecidos con producto, sucursal y proveedor de MongoDB), 14 + 15 |

## 5. Estrategia de consistencia para 14 + 15

No hay transacciones entre motores distintos, así que el todo o nada se garantiza **por el orden de las operaciones, con compensación como último recurso**:

1. **Validar** en MongoDB: cliente activo; farmacéutico activo y de una sucursal tipo Farmacia; productos activos; si hay productos bajo receta, receta vigente del mismo cliente.
2. **Abrir una transacción en MongoDB:** insertar la venta y actualizar la receta (dispensas, próxima dispensa, estado), **sin confirmar**.
3. **Descontar stock en Redis** con el script Lua: FEFO, sin lotes vencidos, todos los ítems o ninguno.
4. **Si Redis rechaza** (stock insuficiente) → abortar la transacción de MongoDB. No queda nada escrito y no hace falta compensar. Es el caso de rechazo que muestra el informe.
5. **Si Redis acepta** → confirmar la transacción de MongoDB.
6. **Si esa confirmación falla y la venta no quedó registrada** → compensar en Redis devolviendo las unidades descontadas.

El caso frecuente (falta de stock) se resuelve sin compensación. La compensación queda solo para una falla de MongoDB justo después de descontar.

> Complemento (no está en las clases): MongoDB soporta transacciones de varios documentos, pero solo si corre como *replica set*. En Docker alcanza con un replica set de un solo nodo. Ver [manual de transacciones](https://www.mongodb.com/docs/manual/core/transactions/).

**Limitación declarada:** si el proceso se cae entre el paso 3 y el 5, el stock puede quedar descontado sin venta. El detalle de la implementación, las decisiones y las limitaciones están en [`informe/q14-q15.md`](informe/q14-q15.md).

## 6. Alternativa evaluada: Neo4j como núcleo + MongoDB para el catálogo

Fue la segunda candidata y la más fuerte. Además, la cátedra cita como ejemplo un caso real de MongoDB + Neo4j (Clase I, p. 6).

- **Diseño:** Neo4j guarda clientes, recetas, farmacéuticos, sucursales, ventas y lotes como un grafo. MongoDB guarda productos y proveedores.
- **A favor:**
  - 14 + 15 serían **una sola transacción ACID** de Neo4j, sin compensación (Clase 16, pp. 15–16).
  - El historial (consultas 3 y 10) es un recorrido natural (Clase 16, p. 39).
- **En contra (por qué no la elegimos):**
  - Las ventas, que son jerárquicas y de alto volumen, quedan en el motor que menos escala para eso (Clase 16, pp. 39–40).
  - MongoDB quedaría solo con el catálogo, un rol difícil de justificar como necesario.
  - Neo4j no tiene vistas, que pide la consulta 11.
  - El producto quedaría duplicado entre los dos motores.
  - Es más pesado de levantar y el grupo tiene menos práctica.

**Tres motores** (el esquema del libro: sistema de registro + Neo4j + Redis; Seven Databases, pp. 289, 293): lo descartamos porque la consigna pide dos como mínimo y cada motor extra suma costo de integración (Clase I, p. 6).

## 7. Stack

- **Python**, que es el lenguaje que usa la cátedra en los ejemplos (`redis-py` con pipelines en Clase 18, pp. 18–19; `boto3` en Clase 20, pp. 26–27). Librerías: `pymongo` y `redis`.
- **docker-compose + devcontainer** con MongoDB (replica set de un nodo) y Redis (AOF activado).
- Las consultas que dependen de la fecha (5, 6, 11, 12 y la vigencia de los lotes) toman la fecha del sistema, como exige la consigna (p. 6).

## 8. Reparto de tareas

**Juntos, antes de dividirnos:** confirmar la arquitectura, cerrar el modelo de datos con sus diagramas y acordar convenciones (ids, fechas, manejo de "hoy").

| Integrante | Parte |
|---|---|
| 1 | Entorno (devcontainer y compose), script de carga idempotente, coordinación de los registros adicionales, README, **q13** (ABM de clientes) |
| 2 | **q01, q02, q03, q06, q08, q09** (lecturas; la q08 cruza Redis y MongoDB) |
| 3 | **q04, q05, q07, q10, q11, q12** (agregaciones, la vista y todo lo que depende de "hoy") |
| 4 | **q14 + q15** y la estrategia de consistencia |

Cada uno escribe la sección del informe de lo suyo, con código, ejemplo de resultado y, para 13–15, el estado antes y después. La justificación de la arquitectura y las conclusiones las escribimos entre todos.

## 9. Para consultar con la cátedra

- La portada dice grupos de **4**, pero los entregables hablan de "los **tres** integrantes".
- **Consulta 12:** ¿una venta "Pendiente" o "Anulada" cuenta como "venta registrada"?
- **Recetas:** el CSV no dice qué productos cubre cada una, así que solo podemos validar que sea del cliente y esté vigente.
- **Dispensas:** una venta con varios productos bajo receta, ¿cuenta como una dispensa o como varias? Los datos provistos cuentan una por venta.

## Fuentes

| Cita | Material de la cátedra |
|---|---|
| Consigna | TPO_FarmaRed.pdf |
| Clase I | BDD II - Clase I (persistencia políglota y Docker) |
| Clase 12 | BD2_Clase 12 - Introducción a NoSQL |
| Clase 13 | BD2_Clase 13 - NoSQL - Embebidos vs. normalizado |
| Clase 15 | BD2_Clase 15 - Introducción a Cassandra |
| Clase 16 | BD2_Clase 16 - Neo4j |
| Anexo Neo4j | Neo4j_anexo (MERGE, Causal Clustering y Raft) |
| Clase 17 | BD2_Clase 17 - Bases de clave-valor (generalidades) |
| Clase 18 | BD2_Clase 18 - Bases de clave-valor (hands-on) |
| Clase 20 | BD2_Clase 20 - Amazon DynamoDB |
| Seven Databases | Perkins, Redmond y Wilson, *Seven Databases in Seven Weeks*, 2.ª ed. |
