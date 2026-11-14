# División del TPO FarmaRed

Arquitectura: MongoDB + Redis con Python (ver `informe.md`, sección 1).

El informe es un único archivo, [`informe.md`](informe.md), con la estructura que pide la consigna (§5.2). Cada uno escribe su parte en la sección que le corresponde.

## Criterio

Dividimos **por consultas**, no por motor. Si cada uno tomara un motor, a quien le tocara Redis le quedaría muy poco, porque Redis solo interviene en las consultas 8, 14 y 15. Además, la consigna evalúa consulta por consulta y pide commits de todos.

Cada uno se hace cargo de su parte completa: código, registros de prueba y sección del informe.

## Fase 0 — Juntos, antes de programar

Una reunión. Lo que salga queda escrito en `docs/` y nadie lo cambia sin avisar:

1. **Modelo de datos:**
   - MongoDB: colecciones, campos, tipos, índices y qué se embebe.
   - Redis: claves y tipos.
2. **Convenciones:**
   - Mantenemos los ids del CSV (`C001`, `V001`…) y los registros propios siguen la misma serie.
   - Fechas como `date` de Python.
   - "Hoy" sale de la fecha del sistema, con un parámetro opcional para que las pruebas den siempre el mismo resultado.
3. **Formato de cada consulta:** `qNN.py` con una función `ejecutar(...)` y un docstring con propósito, parámetros, retorno y motor (lo pide la consigna).
4. **Git:**
   - Una rama por persona.
   - Pull request a `main`, revisado por otro integrante.
   - Nada directo a `main`.

## Fase 1 — En paralelo

| | Integrante 1 | Integrante 2 | Integrante 3 | Integrante 4 |
|---|---|---|---|---|
| **Rol** | Infraestructura y carga | Lecturas | Agregaciones y fechas | Escritura y consistencia |
| **Código** | devcontainer, `docker-compose` (MongoDB como replica set de un nodo, Redis con AOF), conexiones compartidas, carga idempotente, **q13** (ABM de clientes) | **q01, q02, q03, q06, q08, q09** | **q04, q05, q07, q10, q11** (vista), **q12** | **q14, q15**, script Lua de stock, compensación, modelo de stock en Redis |
| **Registros propios** | Clientes, proveedores, sucursales, farmacéuticos | Productos; lotes con stock bajo, por vencer y vencidos | Ventas recientes, del mes actual y de hace más de un año; clientes sin compras | Recetas en cada estado; casos de rechazo |
| **Informe** | Entorno, estrategia de carga, README | Sus consultas, con ejemplos | Sus consultas, con ejemplos | Consistencia de 14 + 15, con estado antes y después y un rechazo |

**Registros adicionales:** la consigna pide ≥ 10 por colección, elegidos para ejercitar las consultas (fechas recientes, stock bajo, lotes vencidos, recetas vencidas, clientes sin compras, ventas pendientes). Cada uno agrega los casos borde que necesitan sus consultas, porque quien programa una consulta es quien mejor sabe qué casos la ponen a prueba. El integrante 1 se asegura de que la carga los tome.

## Dependencias

| Quién espera | A quién | Qué | Cómo no bloquearse |
|---|---|---|---|
| Todos | Integrante 1 | Entorno y carga | Primera entrega chica y temprana: compose levantado + carga de los CSV provistos. |
| Integrante 2 (q08) | Integrante 4 | Claves de stock en Redis | Se definen en la fase 0; el integrante 4 es el dueño y el 2 solo lee. |
| Integrante 4 (q14) | Integrante 1 (q13) | Modelo de clientes | q13 sale temprano. |

## Carga de cada parte

- **Integrante 4:** solo dos consultas, pero son las más difíciles y valen casi todo el 20 % de servicios. Además lleva la sección más larga del informe.
- **Integrante 1:** lleva el riesgo de que todo levante en Codespaces y el README con las instrucciones.
- **Integrantes 2 y 3:** seis consultas cada uno, de dificultad parecida.
  - El 2 tiene q08, la única de lectura que cruza motores.
  - El 3 tiene la vista y todas las que dependen de "hoy".

## Fase 2 — Juntos, cierre

- Probar todo desde cero en un Codespace limpio, siguiendo solo el README.
- Escribir entre todos la justificación de la arquitectura, las limitaciones y las conclusiones del informe.
- Cada uno revisa la sección del informe de otro.

## Asignación

| Integrante | Persona | Estado |
|---|---|---|
| 1 — Infraestructura y carga | Fran | Hecho: entorno, carga, q13 |
| 2 — Lecturas | Román | Hecho: q01, q02, q03, q06, q08, q09 |
| 3 — Agregaciones y fechas | Franco | Hecho: q04, q05, q07, q10, q11, q12 |
| 4 — Escritura y consistencia | Fran | Hecho: q14, q15 |

Con tres personas el rol 4 iba a repartirse entre todos, pero lo tomó Fran junto con el rol 1. Queda pendiente decidir si eso se compensa en el cierre de la fase 2.

## Para consultar con la cátedra

- La portada dice grupos de **4**, pero los entregables hablan de "los **tres** integrantes".
- **Consulta 12:** ¿una venta "Pendiente" o "Anulada" cuenta como "venta registrada"? Mientras no haya respuesta, q12 cuenta **todas** las ventas, en cualquier estado. Con los datos cargados la diferencia es visible: si las anuladas no contaran, aparecería también C015, cuya única venta del año está anulada.
- **Recetas:** el CSV no dice qué productos cubre cada una. q14 valida cliente, estado, dispensas disponibles y, para productos archivados, que la receta sea archivada.
- **Dispensas:** una venta con varios productos bajo receta, ¿cuenta como una dispensa o como varias? Tomamos una por venta, como los datos provistos.
