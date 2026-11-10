# Estrategia de carga

```bash
python -m farmared.carga
```

El script (`farmared/carga.py`) parte de los CSV de la cátedra (`datos/provistos/`) y de los registros propios del equipo (`datos/adicionales/`). Los adicionales tienen los mismos nombres de archivo y encabezados, así que la carga solo concatena las filas de ambos orígenes y procesa todo igual.

## Pasos

1. **Lectura y conversión.** Según las convenciones de la consigna:
   - Campo vacío → `null`.
   - `True`/`False` → booleano.
   - Fechas `AAAA-MM-DD` → `Date` a las 00:00 UTC.
   - Importes, unidades y dispensas → enteros.
   - El resto queda como texto, incluidos DNI y teléfonos, para no perder ceros a la izquierda.
2. **Validación** de los datos combinados, antes de escribir (ver [Integridad referencial](#integridad-referencial)). Si hay errores, los lista todos y termina sin tocar ninguna base.
3. **Transformación** al modelo de `docs/modelo.md`:
   - El id de cada CSV pasa a ser el `_id`.
   - Las filas de `detalle_ventas` se agrupan como `items` embebidos en su venta.
   - Cada venta recibe `id_sucursal`, la sucursal de su farmacéutico.
   - `stock_lotes` va a Redis.
4. **MongoDB.** Crea los índices (únicos en `clientes.dni` y `farmaceuticos.matricula`, y los que usan las consultas). Después, en **una sola transacción**, vacía cada colección con `delete_many` y la vuelve a llenar con `insert_many`.
5. **Redis.** En **un solo `MULTI`**, borra las claves de stock anteriores (`lote:*`, `stock:*`, `lotes:unidades`) y escribe cada lote en sus tres claves (`farmared/stock.py`).

Salida con los datos actuales:

```text
✔ clientes: 8 provistos + 12 adicionales → MongoDB clientes
✔ sucursales: 5 provistos + 10 adicionales → MongoDB sucursales
✔ farmaceuticos: 7 provistos + 11 adicionales → MongoDB farmaceuticos
✔ proveedores: 5 provistos + 10 adicionales → MongoDB proveedores
✔ productos: 13 provistos + 12 adicionales → MongoDB productos
✔ recetas: 9 provistos + 0 adicionales → MongoDB recetas
✔ ventas: 16 provistos + 0 adicionales → MongoDB ventas
✔ detalle_ventas: 22 provistos + 0 adicionales → MongoDB ventas.items
✔ stock_lotes: 18 provistos + 16 adicionales → Redis
```

## Reproducible e idempotente

Cada ejecución deja exactamente el estado de los CSV, sin importar el estado anterior. Descarta las modificaciones de los servicios de escritura y también los documentos que agregaron, por ejemplo un cliente dado de alta con q13. Por eso no se usa un upsert por documento, que dejaría esos documentos agregados.

- En MongoDB, la transacción hace que el reemplazo sea todo o nada: si algo falla a mitad de camino, las colecciones quedan como estaban. Las vistas (q11) no se tocan.
- En Redis, `MULTI` aplica el borrado y la escritura juntos, sin que otro cliente vea el stock vacío en el medio.

Lo comprobamos calculando un hash de todo el contenido de ambas bases después de dos cargas seguidas, con altas, modificaciones y bajas de q13 entre medio: el hash es idéntico.

## Integridad referencial

MongoDB y Redis no garantizan integridad referencial, así que la resolvemos en la aplicación en dos momentos:

- **En la carga**, para los datos de los CSV. Antes de escribir, el script valida los datos combinados de ambos orígenes:
  - Solo pueden estar vacíos `nro_afiliado`, `proxima_dispensa` e `id_receta`, que la consigna permite vacíos.
  - No hay ids repetidos, tampoco entre provistos y adicionales.
  - No hay DNI ni matrículas repetidos.
  - Cada referencia de la consigna (§2.10) apunta a un id existente: sucursal del farmacéutico, proveedor del producto, producto y sucursal del lote, cliente de la receta, cliente, farmacéutico y receta de la venta, y venta y producto de cada ítem.
  - Cada venta tiene al menos un ítem y su total es la suma de cantidad × precio de sus ítems.
  - La receta de una venta, si tiene, es del mismo cliente.
  - Ningún lote tiene unidades negativas.
- **En los servicios de escritura** (q13, q14 y q15), para los datos nuevos: cada servicio valida que existan las entidades que referencia antes de escribir.

Además:
- Los índices únicos de MongoDB garantizan DNI y matrícula únicos aun ante escrituras concurrentes.
- El modelado embebido elimina la referencia venta–ítem: un ítem no puede existir sin su venta.

Las validaciones corren por etapas: formato de cada fila, después vacíos y unicidad, después referencias y por último ventas y lotes. Cada etapa supone que la anterior pasó, así que si una falla se informan sus errores y no se sigue. Ejemplos reales de cargas rechazadas, con filas agregadas a propósito en `adicionales/`:

```text
✘ Carga abortada; no se modificó ninguna base:
  - adicionales/clientes.csv, línea 15: activo: booleano inválido 'Si'
```

```text
✘ Carga abortada; no se modificó ninguna base:
  - clientes: id_cliente C020 repetido
  - clientes: dni 31245678 repetido
```

```text
✘ Carga abortada; no se modificó ninguna base:
  - farmaceuticos F019: id_sucursal S099 no existe en sucursales
```

La carga no valida las reglas de negocio de alta de q14 sobre los datos históricos. Los CSV provistos incluyen, por ejemplo, una venta de un farmacéutico hoy inactivo (V001) y una de un producto hoy discontinuado (V014), que eran válidas cuando se registraron.

## Registros adicionales

La consigna pide al menos 10 registros propios por colección, elegidos para ejercitar las consultas. Cada integrante agregó los casos que ponen a prueba sus consultas.

### Clientes (C009–C020, 12 registros)

| Caso | Registros | Ejercita |
|---|---|---|
| Sin ninguna venta | Todos, salvo los que usen las ventas adicionales | q12 (clientes sin ventas en el último año), q10 |
| Dados de baja | C016, C020 | q13 (baja ya hecha), q14 (rechazo por cliente inactivo) |
| Sin cobertura, sin número de afiliado | C012, C015 | q13 (regla de cobertura) |
| DNI de 7 dígitos | C011 | q13 (el DNI se guarda como texto) |
| Todas las obras sociales y las tres provincias de la red | Todos | q03, q04, q06 (datos del cliente) |

### Sucursales (S006–S015, 10 registros)

| Caso | Registros | Ejercita |
|---|---|---|
| Farmacias nuevas en Buenos Aires, Santa Fe y Córdoba | S006–S013, S015 | q10 con una sucursal sin ventas (resultado vacío) |
| Farmacia dada de baja | S014 | q14 (venta en una sucursal cerrada) |

No agregamos droguerías: la consigna describe una única droguería propia (S005), y el rechazo de una venta en droguería ya se puede probar con su farmacéutico F007.

### Farmacéuticos (F008–F018, 11 registros)

| Caso | Registros | Ejercita |
|---|---|---|
| Director técnico de cada farmacia nueva | F008–F015, F018 | q05 (activos con cero ventas en los últimos 60 días) |
| Segundo farmacéutico de una sucursal existente | F017 (S003) | q05, q10 |
| Dado de baja, en una sucursal cerrada | F016 (S014) | q05 (no aparece), q14 (rechazo por farmacéutico inactivo) |

### Proveedores (PRV006–PRV015, 10 registros)

| Caso | Registros | Ejercita |
|---|---|---|
| Laboratorios y droguerías de distintas provincias, con CUIT de dígito verificador válido | Todos | q01, q08 |
| Dados de baja | PRV013, PRV015 | q01 y q08 con un proveedor inactivo, cuando un producto adicional lo referencia |

### Productos (PRD014–PRD025, 12 registros)

| Caso | Registros | Ejercita |
|---|---|---|
| Las tres condiciones de venta: libre, bajo receta y bajo receta archivada | Todos | q01, q14 (exigir receta o no) |
| Activo con proveedor dado de baja | PRD023 (PRV013) | q01 (aparece, con `proveedor.activo: false`), q08 |
| Discontinuados | PRD024 (de PRV015, también dado de baja), PRD025 | q01 (no aparecen), q14 (rechazo por producto inactivo) |
| Productos de los proveedores adicionales | PRD014–PRD023 | q01, q08 (proveedor de cada lote) |

### Lotes (L019–L034, 16 registros)

Las fechas "por vencer" y "vencido" se eligieron respecto de noviembre de 2026.

| Caso | Registros | Ejercita |
|---|---|---|
| **FEFO con un lote vencido en el medio:** PRD001 en S001 tiene L019 (vencido, 2026-08-31), L020 (2026-12-20) y L001 (2027-08-31) | L019, L020 | q15: tiene que saltear L019 y descontar primero de L020 |
| **FEFO con tres lotes vigentes:** PRD003 en S001 tiene L033 (2026-11-20), L005 (2026-11-30) y L015 (2027-06-30) | L033 | q15: una venta grande consume L033, después L005 y después L015 |
| **Solo stock vencido:** PRD017 en S001 tiene únicamente L022, vencido | L022 | q15: rechazo por falta de stock vigente, aunque haya unidades |
| Lote agotado, que no se borra | L021 (0 unidades) | q08 (aparece con 0), q15 (se saltea) |
| Stock bajo y por vencer | L026 (10 u., 2026-11-25), L028 (8 u., 2026-12-05) | q08 |
| Bordes del umbral de q08 | L030 (49 u., entra), L031 (50 u., no entra) | q08 (`< 50` estricto) |
| Vencido de un producto discontinuado | L034 | q08 (`vencido: true`) |
| Stock central en la droguería | L032 (1800 u.) | q15 (la droguería no vende: sus lotes no se tocan) |
| Lotes en farmacias adicionales | L027 (S006), L028 (S008), L029 (S007), L030 (S012), L031 (S010) | q08 |

### Recetas y ventas

*Pendiente: las agregan los integrantes 3 y 4 (ver `docs/division.md`).*
