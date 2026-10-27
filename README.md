# TestPulse

API inicial de TestPulse, construida con FastAPI. La configuración requiere PostgreSQL; las
credenciales se leen del entorno o de un archivo `.env` local, que no se versiona.

## Requisitos

- Python 3.9 o posterior
- Docker con Docker Compose

## Preparar el entorno local

Desde la raíz del repositorio, en PowerShell:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Edita `.env` y cambia `POSTGRES_PASSWORD` por una contraseña local. No uses credenciales reales
ni compartas este archivo. Instala las versiones fijadas de las dependencias y el paquete:

```powershell
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
docker compose up -d db
python -m alembic upgrade head
```

Arranca la API con:

```powershell
python -m uvicorn main:app --reload
```

La API estará disponible en <http://127.0.0.1:8000>; la comprobación de salud es
<http://127.0.0.1:8000/health> y la documentación interactiva está en <http://127.0.0.1:8000/docs>.
Para detener PostgreSQL, ejecuta `docker compose down`. Los datos locales persisten en el volumen
`postgres_data`; `docker compose down -v` también elimina ese volumen.

## API de proyectos

- `POST /projects`: crea un proyecto con `name` y `repository_url` opcional. Devuelve `201`; los
  nombres vacíos o URL inválidas devuelven `422` y los nombres duplicados `409`.
- `GET /projects`: lista los proyectos registrados.
- `GET /projects/{project_id}`: devuelve el proyecto o `404` si no existe.

## Ingesta e historial de ejecuciones

- `POST /api/v1/projects/{project_id}/runs`: recibe JUnit XML en el cuerpo y acepta `X-Commit-SHA`,
  `X-Branch` e `Idempotency-Key` como encabezados opcionales. Devuelve `201` al crear la ejecución,
  `200` al repetir una solicitud idéntica con la misma clave, `409` si se reutiliza la clave con
  contenido o metadatos diferentes, `404` si el proyecto no existe, `413` si el informe excede el
  límite configurado y `422` si el informe es inválido.
- `GET /api/v1/projects/{project_id}/runs`: devuelve una página ligera del historial, ordenada por
  fecha de ingesta descendente y, en caso de empate, por identificador descendente. Acepta `branch`
  como filtro opcional, `limit` (predeterminado `20`, de `1` a `100`) y `offset` (predeterminado
  `0`, no negativo). La respuesta incluye `items`, `limit`, `offset` y `total`; un proyecto
  inexistente devuelve `404` y parámetros fuera de rango devuelven `422`.
- `GET /api/v1/projects/{project_id}/runs/{run_id}`: devuelve los metadatos y los contadores
  `total`, `passed`, `failed`, `skipped` y `error`, calculados en base de datos. Devuelve `404` si
  el proyecto no existe o la ejecución no pertenece a él.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/results`: devuelve una página de pruebas
  individuales. Acepta `status` (`passed`, `failed`, `skipped` o `error`), `limit` (predeterminado
  `20`, máximo `100`) y `offset` (predeterminado `0`). Incluye el total correspondiente al filtro;
  estados no válidos devuelven `422` y proyectos o ejecuciones inexistentes devuelven `404`.

## Migraciones, tests y calidad

Las migraciones se ejecutan contra la URL definida por las variables `POSTGRES_*` o el archivo
`.env`. La suite de integración usa PostgreSQL y crea un esquema aislado nuevo para probar las
migraciones desde cero y comprobar las restricciones de integridad. Con PostgreSQL iniciado y el
entorno virtual activo, configura la URL de pruebas (usa la misma contraseña local de `.env`):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://testpulse:replace-with-a-local-password@127.0.0.1:5432/testpulse"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Si `TEST_DATABASE_URL` no está definido, pytest omite las pruebas de integración PostgreSQL. GitHub
Actions inicia un PostgreSQL limpio y ejecuta las migraciones, los tests y los controles de calidad
en cada pull request y en cada push a `main`. El último comando comprueba el formato sin modificar
archivos.
