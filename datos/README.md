# Datos

`provistos/` contiene los CSV de la cátedra tal como fueron entregados. No se editan: los registros propios del equipo van en archivos aparte, y la carga combina ambos orígenes.

| Archivo | Registros | Contenido |
|---|---|---|
| `clientes.csv` | 8 | Clientes y cobertura de salud |
| `sucursales.csv` | 5 | Farmacias y la droguería central |
| `farmaceuticos.csv` | 7 | Profesionales y su sucursal |
| `proveedores.csv` | 5 | Laboratorios y droguerías |
| `productos.csv` | 13 | Catálogo con condición de venta y precio de lista |
| `stock_lotes.csv` | 18 | Existencias por lote, sucursal y vencimiento |
| `recetas.csv` | 9 | Recetas y estado de dispensas |
| `ventas.csv` | 16 | Cabecera de ventas |
| `detalle_ventas.csv` | 22 | Ítems de cada venta |

## Convenciones

- UTF-8, separador coma.
- Campo vacío = nulo.
- Booleanos `True`/`False`.
- Fechas ISO `AAAA-MM-DD`.
- Importes en ARS, enteros.
- Fecha de referencia de los datos: 13/10/2026. Las consultas usan la fecha del sistema.
