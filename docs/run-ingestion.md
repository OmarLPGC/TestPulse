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
