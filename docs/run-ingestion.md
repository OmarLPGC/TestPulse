# Ingesta de ejecuciones

## Endpoint

`POST /api/v1/projects/{project_id}/runs` recibe un informe JUnit XML directamente en el cuerpo HTTP. El proyecto debe existir antes de procesar el informe.

Encabezados opcionales:

| Encabezado | Uso |
| --- | --- |
| `Content-Type` | Preferiblemente `application/xml` o `text/xml`. |
| `X-Commit-SHA` | Commit asociado, de hasta 40 caracteres. |
| `X-Branch` | Rama asociada, de hasta 255 caracteres. |
| `Idempotency-Key` | Clave de reintento, de 1 a 255 caracteres no blancos. |

Los metadatos de commit y rama forman parte de la identidad de la solicitud idempotente. La misma clave de idempotencia, proyecto, contenido XML y metadatos devuelve la ejecución previa con `200 OK`; reutilizar la clave con contenido o metadatos distintos devuelve `409 Conflict`. Sin clave, cada solicitud válida crea una nueva ejecución.

Una nueva ejecución se responde con `201 Created`. El cuerpo contiene el identificador y el estado de la ejecución, el hash SHA-256 del informe, los metadatos y los resultados persistidos. Cada resultado incluye la identidad de la prueba, el estado, la duración en milisegundos y los mensajes o trazas del XML, cuando existan.

Los estados globales se derivan de los resultados procesados, no de los contadores declarados en el XML:

- `empty`: el informe no contiene casos de prueba.
- `failed`: al menos un caso tiene estado `failed` o `error`.
- `completed`: los casos restantes son `passed` o `skipped`.

El parser valida el informe completo antes de abrir la operación de persistencia. La ejecución, sus casos de prueba nuevos y todos sus resultados se escriben en una transacción; un error durante el guardado revierte el conjunto completo. Los errores de validación devuelven `422`, un informe por encima del límite devuelve `413`, un proyecto inexistente devuelve `404` y los conflictos de idempotencia devuelven `409`.

## Límites

Por defecto, se aceptan informes de hasta **10 MiB** y **100.000 casos de prueba**. Los límites se pueden reducir mediante las variables de entorno `MAX_JUNIT_REPORT_BYTES` y `MAX_JUNIT_TEST_CASES`; el backend no permite configurarlos por encima de esos máximos de seguridad. Los límites deben revisarse con mediciones de rendimiento antes de aumentarlos.
