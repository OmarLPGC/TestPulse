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

## English

# Analysis engine

The analysis engine lives in `testpulse.analysis` and operates on typed observations; it does not
depend on FastAPI or SQLAlchemy. Database queries select the history or run pair and convert their
rows into these observations. Deterministic functions then apply the rules.

## Reliability and flakiness

For each test, the engine considers the most recent valid observations from the requested branch.
The order is `ingested_at` descending, with run ID descending to break ties. `skipped` results are
excluded before selecting the window and do not increase the observation count. `passed` counts
as a success; `failed` and `error` count as failures.

The default window size is 20 (the endpoint accepts 1 to 100). At least 5 valid observations are
required to classify reliability:

- `insufficient_data`: fewer than 5 valid observations.
- `stable`: at least 5 observations, all `passed`.
- `persistently_failing`: at least 5 observations, all `failed` or `error`.
- `potentially_flaky`: at least 5 observations, with both `passed` and `failed`/`error`.

The failure rate is `(number of failed + number of error) / number of valid observations`,
rounded to four decimal places. The response keeps the `failed` and `errors` counters separate.
This rule identifies observed alternation; it does not infer a root cause or apply a probabilistic
model.

## Regressions

The comparison uses the chronologically previous run for the same branch and project, ordered by
`ingested_at` descending with ID as the tie-breaker. A test is reported as a regression only if it
appears in both runs, its previous result was `passed`, and its current result is `failed` or
`error`. Persistent failures, new tests, and tests that were previously skipped are not classified
as regressions. If there is no previous run on that branch (or no branch was provided), the result
is an empty list. The output is sorted by class, name, and ID for reproducibility.

## Endpoints

- `GET /api/v1/projects/{project_id}/analysis/reliability?branch=main&window_size=20` returns
  reliability analysis per test. The branch is optional; without it, histories from all project
  branches are considered.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/regressions` returns the branch, the previous
  run used for comparison, and the regressions (which may be an empty list).

Both endpoints return `404` for nonexistent projects; the regression endpoint also returns `404`
if the run does not exist in the specified project. A `window_size` outside the allowed range
returns `422`.
