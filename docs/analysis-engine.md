# Motor de análisis

El motor de análisis vive en `testpulse.analysis` y opera sobre observaciones tipadas; no depende
de FastAPI ni de SQLAlchemy. Las consultas de base de datos seleccionan el historial o la pareja de
ejecuciones y convierten sus filas en esas observaciones. Las reglas se aplican después mediante
funciones deterministas.

## Fiabilidad e inestabilidad

Para cada prueba se consideran las observaciones válidas más recientes de la rama solicitada. El
orden es `ingested_at` descendente y, en caso de empate, identificador de ejecución descendente.
Los resultados `skipped` se excluyen antes de seleccionar la ventana y no aumentan el número de
observaciones. `passed` cuenta como éxito; `failed` y `error` cuentan como fallos.

El tamaño de ventana predeterminado es 20 (el endpoint permite de 1 a 100). Se necesitan al menos
5 observaciones válidas para clasificar la fiabilidad:

- `insufficient_data`: menos de 5 observaciones válidas.
- `stable`: hay al menos 5 observaciones y todas son `passed`.
- `persistently_failing`: hay al menos 5 y todas son `failed` o `error`.
- `potentially_flaky`: hay al menos 5 y aparecen tanto `passed` como `failed`/`error`.

La tasa de fallo es `(cantidad de failed + cantidad de error) / cantidad de observaciones válidas`,
redondeada a cuatro decimales. Los contadores `failed` y `errors` de la respuesta se mantienen
separados. Esta regla identifica alternancia observada; no infiere una causa raíz ni aplica un
modelo probabilístico.

## Regresiones

La comparación usa la ejecución cronológicamente anterior de la misma rama y proyecto, ordenada por
`ingested_at` descendente con el ID como desempate. Una prueba se informa como regresión solo si
está en ambas ejecuciones, su resultado anterior es `passed` y el actual es `failed` o `error`.
Fallos persistentes, pruebas nuevas y pruebas que estaban omitidas anteriormente no se clasifican
como regresiones. Si no hay ejecución anterior en esa rama (o no se proporcionó rama), el resultado
es una lista vacía. La salida se ordena por clase, nombre e ID para que sea reproducible.

## Endpoints

- `GET /api/v1/projects/{project_id}/analysis/reliability?branch=main&window_size=20` devuelve el
  análisis de fiabilidad por prueba. La rama es opcional; sin ella se consideran los historiales de
  todas las ramas del proyecto.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/regressions` devuelve la rama, la ejecución
  previa comparada y las regresiones (posiblemente una lista vacía).

Ambos endpoints devuelven `404` para proyectos inexistentes; el endpoint de regresiones también
devuelve `404` si la ejecución no existe en el proyecto indicado. Un `window_size` fuera del rango
admitido devuelve `422`.
