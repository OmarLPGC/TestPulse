# Ingesta de ejecuciones

## Endpoint

`POST /api/v1/projects/{project_id}/runs` recibe un informe JUnit XML directamente en el cuerpo HTTP. El proyecto debe existir antes de procesar el informe.

La operación requiere `Authorization: Bearer <project-ingestion-token>`. El token debe estar activo,
no expirado y asociado al proyecto de la ruta. Se valida antes de leer el cuerpo. Los tokens CI no
autorizan consultas ni proyectos distintos; la autenticación de usuarios usa sesiones separadas.

Encabezados opcionales:

| Encabezado | Uso |
| --- | --- |
| `Content-Type` | Preferiblemente `application/xml` o `text/xml`. |
| `X-Commit-SHA` | Commit asociado, de hasta 40 caracteres. |
| `X-Branch` | Rama asociada, de hasta 255 caracteres. |
| `Idempotency-Key` | Clave de reintento, de 1 a 255 caracteres no blancos. |
| `X-CI-Source` | Fuente CI, hasta 100 caracteres. |
| `X-CI-Run-ID` | Identificador externo de ejecución, hasta 255 caracteres. |
| `X-CI-Run-Attempt` | Intento externo, hasta 64 caracteres. |
| `X-CI-Event` | Evento externo, hasta 100 caracteres. |
| `X-CI-Pull-Request` | Pull request externo opcional, hasta 64 caracteres. |

Los metadatos de commit, rama y CI forman parte de la identidad de la solicitud idempotente. La
misma clave, proyecto, contenido XML y metadata devuelve la ejecución previa con `200 OK`;
reutilizarla con contenido o metadata distintos devuelve `409 Conflict`. Los encabezados CI son
descriptivos y no prueban identidad ni autorizan la petición. Sin clave, cada solicitud válida crea
una nueva ejecución.

Una nueva ejecución se responde con `201 Created`. El cuerpo contiene el identificador y el estado de la ejecución, el hash SHA-256 del informe, los metadatos y los resultados persistidos. Cada resultado incluye la identidad de la prueba, el estado, la duración en milisegundos y los mensajes o trazas del XML, cuando existan.

Los estados globales se derivan de los resultados procesados, no de los contadores declarados en el XML:

- `empty`: el informe no contiene casos de prueba.
- `failed`: al menos un caso tiene estado `failed` o `error`.
- `completed`: los casos restantes son `passed` o `skipped`.

El parser valida el informe completo antes de abrir la operación de persistencia. La ejecución, sus
casos de prueba nuevos, resultados y job se escriben en una transacción; un error durante el guardado
revierte el conjunto completo. Un token ausente, inválido, expirado o revocado devuelve `401`; los
errores de validación devuelven `422`, un informe por encima del límite devuelve `413` y los
conflictos de idempotencia devuelven `409`.

## Límites

Por defecto, se aceptan informes de hasta **10 MiB** y **100.000 casos de prueba**. Los límites se pueden reducir mediante las variables de entorno `MAX_JUNIT_REPORT_BYTES` y `MAX_JUNIT_TEST_CASES`; el backend no permite configurarlos por encima de esos máximos de seguridad. Los límites deben revisarse con mediciones de rendimiento antes de aumentarlos.

## English

# Run ingestion

## Endpoint

`POST /api/v1/projects/{project_id}/runs` accepts a JUnit XML report directly in the HTTP request
body. The project must exist before the report is processed.

The operation requires `Authorization: Bearer <token>`. The token must be active, not expired, and
associated with the project in the route. It is validated before the request body is read. CI tokens
do not authorize queries or access to other projects; user authentication uses separate sessions.

Optional headers:

| Header | Purpose |
| --- | --- |
| `Content-Type` | Preferably `application/xml` or `text/xml`. |
| `X-Commit-SHA` | Associated commit, up to 40 characters. |
| `X-Branch` | Associated branch, up to 255 characters. |
| `Idempotency-Key` | Retry key, 1 to 255 non-whitespace characters. |
| `X-CI-Source` | CI source, up to 100 characters. |
| `X-CI-Run-ID` | External run identifier, up to 255 characters. |
| `X-CI-Run-Attempt` | External attempt, up to 64 characters. |
| `X-CI-Event` | External event, up to 100 characters. |
| `X-CI-Pull-Request` | Optional external pull request, up to 64 characters. |

Commit, branch, and CI metadata are part of the idempotent request identity. The same key, project,
XML content, and metadata return the previous run with `200 OK`; reusing the key with different
content or metadata returns `409 Conflict`. CI headers are descriptive and do not prove identity
or authorize the request. Without a key, each valid request creates a new run.

A new run returns `201 Created`. The response body contains the run identifier and status, the
report's SHA-256 hash, metadata, and persisted results. Each result includes the test identity,
status, duration in milliseconds, and any messages or traces from the XML.

Overall statuses are derived from the processed results, not from the counts declared in the XML:

- `empty`: the report contains no test cases.
- `failed`: at least one case has the `failed` or `error` status.
- `completed`: the remaining cases are `passed` or `skipped`.

The parser validates the complete report before opening the persistence operation. The run, its
new test cases, results, and job are written in one transaction; an error during persistence rolls
back the entire operation. A missing, invalid, expired, or revoked token returns `401`; validation
errors return `422`, a report over the configured limit returns `413`, and idempotency conflicts
return `409`.

## Limits

By default, reports of up to **10 MiB** and **100,000 test cases** are accepted. The limits can be
lowered using the `MAX_JUNIT_REPORT_BYTES` and `MAX_JUNIT_TEST_CASES` environment variables; the
backend does not allow values above these safety maximums. Measure performance before increasing
the limits.
