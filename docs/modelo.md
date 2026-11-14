# Modelo de datos — borrador para la reunión

Propuesta del integrante 1 para cerrar en la fase 0. Arquitectura: MongoDB como sistema de registro y Redis para el stock (ver `arquitectura.md`).

## Convenciones

| Tema | Decisión |
|---|---|
| Identificadores | `_id` = id del CSV (`"C001"`, `"V001"`…). Las referencias usan los nombres de campo del CSV (`id_cliente`, `id_producto`…). Los registros propios siguen la misma serie (`C009`, `V017`…). |
| Nombres de campo | Los del CSV, sin cambios. |
| Booleanos | `True`/`False` del CSV → `bool`. |
| Fechas | `AAAA-MM-DD` → `Date` de MongoDB a las 00:00 UTC de ese día. Solo importa el día: para comparar con "hoy", se convierte la fecha de hoy de la misma forma. |
| Importes | Enteros en ARS. |
| Vacíos | `null` explícito: todos los documentos de una colección tienen los mismos campos. |
| "Hoy" | Fecha del sistema en hora argentina (el contenedor corre con `TZ=America/Argentina/Buenos_Aires`). Cada consulta que la usa acepta un parámetro opcional `hoy` para pruebas. |
| Lote vencido | `vencimiento < hoy`. Un lote se puede dispensar hasta el día de su vencimiento inclusive (supuesto, va al informe). |
| Bajas | Lógicas: `activo: false`. Nunca se borra un documento ni un lote. |

## MongoDB (base `farmared`)

Siete colecciones de datos más `contadores`. No hay colección de lotes: el stock vive solo en Redis.

### `clientes`

```js
{ _id: "C001", nombre: "Lucía", apellido: "Fernández", dni: "31245678",
  email: "lucia.f@gmail.com", telefono: "1145112233",
  ciudad: "Buenos Aires", provincia: "Buenos Aires",
  obra_social: "OSDE", nro_afiliado: "OS-310045", activo: true }
```

- Índice **único** en `dni` (q13 valida DNI único).
- Consultas: 3, 4, 6, 10, 12, 13, 14.

### `sucursales`

```js
{ _id: "S001", nombre: "Farmacia Palermo", tipo: "Farmacia",
  direccion: "Av. Santa Fe 3350", ciudad: "Buenos Aires", provincia: "Buenos Aires",
  telefono: "1148001001", activo: true }
```

- Consultas: 2, 8, 10, 14.

### `farmaceuticos`

```js
{ _id: "F001", nombre: "Mariana", apellido: "Quiroga", matricula: "MN-18041",
  cargo: "Director Técnico", id_sucursal: "S001", activo: true }
```

- Colección propia con referencia a la sucursal. Se consulta por sí sola (q05, q11), así que no conviene embeberla en la sucursal.
- Índice **único** en `matricula`; índice en `id_sucursal` (q10).
- Consultas: 2, 5, 10, 11, 14, 15.

### `proveedores`

```js
{ _id: "PRV001", razon_social: "Laboratorios Andinos S.A.", cuit: "30-71234567-1",
  tipo: "Laboratorio", ciudad: "Buenos Aires", provincia: "Buenos Aires",
  telefono: "1143001100", activo: true }
```

- Consultas: 1, 8.

### `productos`

```js
{ _id: "PRD001", nombre: "Paracetamol 500mg x30", principio_activo: "Paracetamol",
  categoria: "Analgésico", presentacion: "Comprimidos x30",
  condicion_venta: "Venta libre", precio_unit: 2800,
  id_proveedor: "PRV001", activo: true }
```

- Referencia al proveedor; la q01 lo une con `$lookup`. Un proveedor tiene muchos productos y así no se repiten sus datos (Clase 13, editor–libros).
- Consultas: 1, 7, 8, 14.

### `recetas`

```js
{ _id: "RC002", id_cliente: "C003", medico: "Dra. Silvia Montenegro",
  matricula_medico: "MP-39877", fecha_emision: ISODate("2026-07-15"),
  tipo: "Tratamiento prolongado", dispensas_autorizadas: 3, dispensas_realizadas: 2,
  proxima_dispensa: ISODate("2026-09-15"), estado: "Vigente" }
```

- Colección propia que referencia al cliente (un cliente acumula recetas sin límite).
- Índices: `id_cliente`; `{ tipo, estado, proxima_dispensa }` para q06.
- Consultas: 3, 4, 6, 14.

### `ventas`

```js
{ _id: "V006", id_cliente: "C006", id_farmaceutico: "F002", id_sucursal: "S001",
  id_receta: "RC003", fecha: ISODate("2026-08-01"), tipo: "Con receta",
  medio_pago: "Obra social", total: 22100, estado: "Completada",
  items: [
    { id_detalle: "D007", id_producto: "PRD005", cantidad: 3, precio_unit: 5400 },
    { id_detalle: "D008", id_producto: "PRD009", cantidad: 1, precio_unit: 5900 } ] }
```

- `items` embebidos: es una relación "contiene" y siempre se leen y escriben con la venta. Insertar una venta con sus ítems es una sola operación atómica (Clase 13).
- `precio_unit` del ítem es el precio al momento de la venta (puede diferir del de lista).
- `id_sucursal` es la sucursal donde ocurrió la venta, copiada del farmacéutico al registrarla. q15 la usa para saber de qué lotes descontar. La q10 sigue pasando por el farmacéutico, como pide la consigna.
- Índices: `{ id_cliente, fecha }`, `{ id_farmaceutico, fecha }`, `{ fecha }`, `{ estado }` y **único** en `items.id_detalle`.
- Consultas: 2, 3, 5, 7, 9, 10, 11, 12, 14, 15.

### `contadores`

```js
{ _id: "ventas", ultimo: 16 }
{ _id: "detalle_ventas", ultimo: 22 }
```

- Último número usado de cada serie de ids. La carga lo calcula de los CSV; q14 lo incrementa con un `$inc` atómico fuera de su transacción, así que dos ventas simultáneas no compiten por el mismo id (ver `informe/q14-q15.md`).

### Vista

- `ingresos_farmaceutico_mes` (q11): pipeline sobre `ventas` que filtra "Completada" del mes actual y suma `total` por farmacéutico. *Complemento (no está en las clases): la vista calcula el mes actual con `$$NOW`, que se evalúa en cada consulta.* El diseño final lo define el integrante 3.

## Redis (base 0)

| Clave | Tipo | Contenido |
|---|---|---|
| `lote:{id_lote}` | Hash | `id_producto`, `id_sucursal`, `nro_lote`, `unidades`, `vencimiento` (ISO) |
| `stock:{id_sucursal}:{id_producto}` | Sorted set | miembro `id_lote`, score = vencimiento como `AAAAMMDD` |
| `lotes:unidades` | Sorted set | miembro `id_lote`, score = unidades |
| `ventas:descontadas` | Set | ventas cuyo stock ya se descontó (la carga agrega las "Completada" de los CSV) |
| `descuento:{id_venta}` | Hash | `id_lote` → unidades descontadas de ese lote para la venta |

```text
HSET lote:L005 id_producto PRD003 id_sucursal S001 nro_lote L-2506A unidades 40 vencimiento 2026-11-30
ZADD stock:S001:PRD003 20261130 L005 20270630 L015
ZADD lotes:unidades 40 L005

# Lotes dispensables de PRD003 en S001, del que vence antes (hoy = 2026-11-09):
ZRANGEBYSCORE stock:S001:PRD003 20261109 +inf

# q08: lotes con menos de 50 unidades
ZRANGEBYSCORE lotes:unidades -inf (50
```

**Invariantes:**
- Las unidades solo cambian en los scripts Lua `descontar` y `reponer` (`farmared/stock.py`), que actualizan el hash y `lotes:unidades` en la misma operación atómica. La carga escribe todo en un `MULTI`.
- Los lotes con 0 unidades no se borran (baja lógica): quedan en los sorted sets y el script los saltea.
- Las unidades nunca quedan negativas: `descontar` solo escribe si alcanzan todos los productos.
- Una venta se descuenta una sola vez: `descontar` la agrega a `ventas:descontadas` y guarda `descuento:{id_venta}` en la misma operación.

## Consultas por colección y clave

| # | MongoDB | Redis |
|---|---|---|
| 1 | productos, proveedores | |
| 2 | ventas, farmaceuticos, sucursales | |
| 3 | ventas, recetas | |
| 4 | recetas, clientes | |
| 5 | farmaceuticos, ventas | |
| 6 | recetas, clientes | |
| 7 | ventas, productos | |
| 8 | productos, proveedores, sucursales | `lotes:unidades`, `lote:*` |
| 9 | ventas | |
| 10 | ventas, farmaceuticos, clientes | |
| 11 | vista `ingresos_farmaceutico_mes` | |
| 12 | clientes, ventas | |
| 13 | clientes | |
| 14 | clientes, farmaceuticos, sucursales, productos, recetas, ventas, contadores | (vía q15) y `descuento:*` para compensar |
| 15 | ventas | `stock:*`, `lote:*`, `lotes:unidades`, `ventas:descontadas`, `descuento:*` |

## Carga

- **Fuentes:** `datos/provistos/*.csv` y `datos/adicionales/*.csv`, con el mismo formato y los mismos nombres de archivo. Cada integrante agrega sus registros en `adicionales/`.
- **Transformación:**
  - `detalle_ventas` se agrupa en `ventas.items` por `id_venta`.
  - `ventas.id_sucursal` se completa con la sucursal del farmacéutico.
  - `stock_lotes` va a Redis, y las ventas "Completada" se marcan en `ventas:descontadas` porque los lotes ya reflejan su stock.
  - `contadores` toma el último id de ventas y de ítems.
- **Idempotencia:**
  - MongoDB: se crean los índices y, en una única transacción, cada colección se vacía (`delete_many`) y se vuelve a llenar (`insert_many`). Las vistas no se tocan.
  - Redis: en un único `MULTI`, se borran `lote:*`, `stock:*`, `lotes:unidades`, `ventas:descontadas` y `descuento:*` y se escriben de nuevo.
  - Volver a cargar deja exactamente el estado inicial de los CSV y descarta los cambios hechos por las consultas de escritura, incluidos los documentos que agregaron.
- **Integridad referencial:** antes de escribir, la carga valida los datos combinados y, si encuentra errores, los informa todos y no modifica ninguna base:
  - Solo pueden estar vacíos `nro_afiliado`, `proxima_dispensa` e `id_receta`.
  - Los ids, los DNI y las matrículas son únicos.
  - Cada referencia de la consigna (§2.10) apunta a un id existente.
  - Cada venta tiene ítems y su total es la suma de ellos. Su receta, si tiene, es del mismo cliente.
  - Ningún lote tiene unidades negativas.

  No valida las reglas de alta de q14: los datos históricos incluyen, por ejemplo, ventas de un farmacéutico hoy inactivo (V001) o de un producto hoy discontinuado (V014).

## Para decidir en la reunión

1. Aprobar o ajustar este modelo.
2. **Consulta 12:** ¿una venta "Pendiente" o "Anulada" cuenta como "venta registrada"? (también para preguntar a la cátedra).
3. Quién toma cada parte (integrantes 2, 3 y 4).

Las dudas sobre dispensas y recetas quedaron resueltas en `informe/q14-q15.md` (una venta es una dispensa; la receta no indica productos, así que se valida cliente, estado y tipo).
