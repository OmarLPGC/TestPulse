# TestPulse

TestPulse es una aplicación self-hosted para recopilar y analizar resultados de pruebas
automatizadas de proyectos Python. Recibe informes JUnit XML (por ejemplo, generados por pytest),
conserva su historial y ayuda a detectar pruebas potencialmente inestables y regresiones. No es un
ejecutor de pruebas ni un framework para escribirlas: la suite se ejecuta en tu CI y TestPulse
analiza sus resultados con reglas deterministas.

El proyecto contiene una API FastAPI, un dashboard React/TypeScript, un cliente CLI y un worker de
análisis asíncrono. PostgreSQL almacena los proyectos, ejecuciones, resultados y trabajos. Las
credenciales se leen del entorno o de un archivo `.env` local, que no se versiona.

## Requisitos

- Python 3.9 o posterior
- Docker con Docker Compose
- Node.js 22.12 o posterior, solo para ejecutar o compilar el dashboard fuera de Docker

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

Para levantar el dashboard, la API, el worker y PostgreSQL en contenedores, usa el perfil
self-hosted:

```powershell
docker compose --profile self-hosted up -d --build
```

Por defecto, el dashboard se publica en <http://127.0.0.1:8080>, la API en
<http://127.0.0.1:8000> y PostgreSQL en `127.0.0.1:5432`. La API y PostgreSQL solo se publican en
la interfaz local. En despliegues, coloca un proxy HTTPS delante del dashboard; este reenvía `/api`
y la ruta API exacta `/projects` a la API.
Consulta [docs/authentication-and-self-hosting.md](docs/authentication-and-self-hosting.md) para
configurar la GitHub App, las cookies, la clave de cifrado, el workspace legado y los secrets de CI.
Compose ejecuta `alembic upgrade head` antes de iniciar la API. Para detener todos los servicios,
ejecuta `docker compose --profile self-hosted down`; el volumen `postgres_data` se conserva. Añadir
`-v` elimina también los datos persistidos.

## Autenticación y workspaces

El login del dashboard usa una GitHub App configurada por la instalación. La sesión se mantiene en
una cookie opaca `HttpOnly`; `/api/v1/auth/me` devuelve el perfil y el `X-CSRF-Token` que acompaña
las operaciones de escritura. El dashboard gestiona esta sesión automáticamente. Las rutas privadas
de proyectos, ejecuciones, análisis y workspaces requieren sesión. `GET /api/v1/workspaces` lista
los workspaces disponibles. Los members pueden consultar proyectos, ejecuciones, resultados y
análisis de su workspace; solo owners pueden crear proyectos, gestionar miembros, conectar
repositorios y administrar tokens CI.

Para habilitar login y descubrimiento de repositorios, configura juntos los cinco valores de GitHub
App indicados en [docs/authentication-and-self-hosting.md](docs/authentication-and-self-hosting.md).
`PUBLIC_BASE_URL` debe ser el origen desde el que abres el dashboard y el callback debe usar ese
mismo origen. Sin esa configuración, los endpoints de autenticación GitHub responden que el servicio
no está configurado.

Cada proyecto pertenece a un workspace. Los proyectos preexistentes se migran a un workspace
legado sin miembros, que solo puede reclamar la cuenta GitHub configurada en
`TESTPULSE_BOOTSTRAP_GITHUB_USER_ID` a través de `POST /api/v1/workspaces/legacy/claim`.

## API de proyectos

- `POST /projects`: crea un proyecto con `name` y `repository_url` opcional en el workspace personal
  o en el `workspace_id` indicado. Requiere rol owner. Devuelve `201`; nombres vacíos o URL inválidas
  devuelven `422` y nombres duplicados en el mismo workspace `409`.
- `GET /projects`: lista los proyectos de los workspaces accesibles a la sesión.
- `GET /projects/{project_id}`: devuelve un proyecto accesible o `404`.
- `POST /api/v1/workspaces`: crea un workspace con el usuario actual como owner.
- `GET /api/v1/workspaces/{workspace_id}/members` y las operaciones `POST`/`DELETE` sobre esa ruta
  permiten consultar y administrar miembros; solo owners pueden modificar membresías.
- `GET /api/v1/github/repositories`: enumera repositorios GitHub accesibles de forma paginada.
  Owners conectan o desconectan el repositorio seleccionado desde
  `/api/v1/projects/{project_id}/repository`; no se importan repositorios en lote.
- `POST /api/v1/projects/{project_id}/ingestion-tokens`: crea un token de ingesta limitado a un
  proyecto, visible solo en la respuesta de creación. Acepta un `name` de hasta 100 caracteres.
  Owners pueden revocarlo mediante `DELETE` y listar metadatos (incluido el nombre) sin recuperar
  el secreto.

## Ingesta e historial de ejecuciones

- `POST /api/v1/projects/{project_id}/runs`: requiere `Authorization: Bearer <project-token>` y
  recibe JUnit XML en el cuerpo. Acepta `X-Commit-SHA`, `X-Branch`, `Idempotency-Key` y metadata
  opcional `X-CI-*`. El token solo autoriza ingesta del proyecto asociado. Devuelve `201` al crear
  la ejecución, `200` al repetir una solicitud idéntica con la misma clave, `409` si se reutiliza
  con contenido o metadata diferente, `401` si falta o no es válido el token, `413` si el informe
  excede el límite configurado y `422` si el informe es inválido.
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
- `GET /api/v1/projects/{project_id}/analysis/reliability`: analiza por test las últimas
  observaciones de una rama opcional; si no se indica, analiza el historial de todas las ramas.
  Acepta `window_size` (predeterminado `20`, máximo `100`) y
  excluye `skipped`. Se necesitan al menos 5 observaciones válidas para clasificar; todas aprobadas
  se clasifican como `stable`, una mezcla de `passed` y `failed`/`error` como `potentially_flaky`, y
  fallos en todas las observaciones como `persistently_failing`. Con menos de 5, el resultado es
  `insufficient_data`. También informa la tasa de fallo, `(failed + error) / observaciones válidas`,
  redondeada a cuatro decimales.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/regressions`: compara la ejecución con la
  ejecución cronológicamente anterior de la misma rama. Solo informa tests presentes en ambas que
  cambian de `passed` a `failed` o `error`; los tests nuevos y los fallos persistentes no son nuevas
  regresiones. Si la ejecución no tiene rama previa comparable, devuelve una lista vacía. Proyectos
  o ejecuciones inexistentes devuelven `404`.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/analysis-job`: devuelve el trabajo duradero
  asociado a la ejecución, incluyendo estado, intentos, último error y, al completarse, el snapshot
  de fiabilidad y regresiones. Devuelve `404` si el proyecto o el trabajo no existen.

Las reglas de ventana, clasificación de fiabilidad y comparación de regresiones se describen con
detalle en [docs/analysis-engine.md](docs/analysis-engine.md).

## Procesamiento asíncrono

Cada informe válido crea un trabajo de análisis en la misma transacción que la ejecución y sus
resultados. Repetir una ingesta idempotente devuelve la ejecución existente y conserva su único
trabajo. Los estados posibles son `pending`, `processing`, `completed` y `failed`; se permiten tres
intentos. Los errores se registran en el trabajo y en los logs del worker. Una concesión de cinco
minutos por defecto (ajustable con `--lease-seconds`) permite recuperar trabajos cuyo proceso se
haya detenido mientras los ejecutaba.

La cola está respaldada por PostgreSQL y no necesita un broker externo: si no hay ningún worker
activo, las tareas permanecen pendientes; al iniciar uno, las reclama desde la base de datos. El
worker usa bloqueos de fila en PostgreSQL para coordinar varios procesos, y el análisis persistido
es idempotente por ejecución. Las consultas básicas de proyectos, historial y resultados no
requieren que haya workers activos.

Inicia un worker en una terminal independiente, después de aplicar las migraciones:

```powershell
testpulse-worker
```

Para procesar como máximo un trabajo y salir, utiliza `testpulse-worker --once`. `--poll-interval`
ajusta la espera entre consultas cuando la cola está vacía y `--lease-seconds` la duración de la
concesión antes de recuperar un trabajo abandonado. Consulta el estado y el resultado con el
endpoint `analysis-job` de la ejecución. Los endpoints de fiabilidad y regresiones existentes
siguen disponibles y calculan sus respuestas directamente para conservar su comportamiento.

## Dashboard web

El dashboard incluye login de GitHub, selector de workspace, conexión de repositorios y
configuración de CI con tokens de ingesta que se muestran una sola vez. La vista del proyecto
permite explorar ejecuciones, filtrar por rama, inspeccionar resultados, consultar fiabilidad y
revisar regresiones.

Con la API y PostgreSQL iniciados, abre otra terminal desde la raíz del repositorio:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Necesitas Node.js 22.12 o posterior. Abre <http://127.0.0.1:5173>. Vite reenvía `/api` y la ruta
exacta `/projects` a `http://127.0.0.1:8000`; las rutas de interfaz como `/projects/new` siguen
sirviéndose como páginas del dashboard. Cambia el destino de la API con `TESTPULSE_API_TARGET`.
Para desplegar el frontend y la API en orígenes diferentes, configura un proxy inverso de misma
procedencia para `/api` y `/projects`.

Las pruebas del dashboard se ejecutan con `npm run test:run`; `npm run typecheck` valida TypeScript
y `npm run build` genera la versión estática en `frontend/dist`.

## Cliente CLI e integración con GitHub Actions

Instala el paquete TestPulse para disponer del comando `testpulse`. Desde el repositorio:

```powershell
python -m pip install .
```

Genera el informe de pytest y envíalo indicando el endpoint y el ID del proyecto:

```powershell
python -m pytest --junitxml=test-results.xml
testpulse --url https://testpulse.example.com --project 42 --report test-results.xml
```

`--commit` y `--branch` son opcionales. Por defecto, el cliente usa `GITHUB_SHA` o `CI_COMMIT_SHA`
para el commit y `GITHUB_HEAD_REF`, `GITHUB_REF_NAME` o `CI_COMMIT_REF_NAME` para la rama. Se puede
proporcionar `--idempotency-key` para reintentos manuales. En GitHub Actions se genera una clave
estable por repositorio, ejecución, intento y proyecto. En ejecuciones locales sin clave se genera
un UUID por invocación.

El endpoint de ingesta siempre requiere un token válido; el CLI termina con un error de uso si no
se configura.

Define `TESTPULSE_API_TOKEN` en el entorno antes de ejecutar el comando. La variable está omitida en
el ejemplo para no incluir el secreto en el README.
`TESTPULSE_API_TOKEN` (o `--token`) se envía como `Authorization: Bearer ...`; no escribas el token
directamente en los argumentos ni en el repositorio.

Ejemplo de workflow para el proyecto que produce las pruebas:

```yaml
name: Tests and TestPulse

on:
  push:
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
      - run: python -m pip install pytest
      - name: Install TestPulse CLI
        run: python -m pip install "git+https://github.com/OmarLPGC/TestPulse.git"
      - name: Run tests and generate JUnit XML
        run: python -m pytest --junitxml=test-results.xml
      - name: Upload results to TestPulse
        if: >-
          always() &&
          (github.event_name != 'pull_request' ||
          github.event.pull_request.head.repo.full_name == github.repository)
        env:
          TESTPULSE_URL: ${{ vars.TESTPULSE_URL }}
          TESTPULSE_PROJECT_ID: ${{ vars.TESTPULSE_PROJECT_ID }}
          TESTPULSE_API_TOKEN: ${{ secrets.TESTPULSE_API_TOKEN }}
          TESTPULSE_BRANCH: ${{ github.head_ref || github.ref_name }}
        run: >-
          testpulse --url "$TESTPULSE_URL"
          --project "$TESTPULSE_PROJECT_ID"
          --report test-results.xml
          --commit "$GITHUB_SHA"
          --branch "$TESTPULSE_BRANCH"
```

El ejemplo instala el CLI desde este repositorio; si se distribuye como paquete o artefacto, usa
esa fuente en el paso de instalación. Configura `TESTPULSE_URL` y `TESTPULSE_PROJECT_ID` como
variables del repositorio y `TESTPULSE_API_TOKEN` como secreto. La subida se omite para pull
requests desde forks, que no reciben secrets de GitHub. `if: always()` permite intentar la subida
aunque pytest falle, siempre que el informe exista; un error de subida hace fallar ese paso.

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

Si `TEST_DATABASE_URL` no está definido, pytest omite las pruebas de integración PostgreSQL. El
usuario de la base de datos de pruebas debe poder crear y eliminar esquemas: las pruebas de
integración migran cada una en un esquema PostgreSQL aislado. GitHub Actions inicia un PostgreSQL
limpio y ejecuta migraciones, tests, lint, formato, typecheck y build del frontend en cada pull
request y en cada push a `main`. El último comando comprueba el formato sin modificar archivos.
Si la contraseña contiene caracteres reservados en una URL, codifícalos antes de usarla en
`TEST_DATABASE_URL`.

---

# TestPulse (English)

TestPulse is a self-hosted application for collecting and analyzing automated test results from
Python projects. It accepts JUnit XML reports (for example, generated by pytest), keeps their
history, and helps identify potentially flaky tests and regressions. It is not a test runner or a
framework for writing tests: your CI runs the suite and TestPulse analyzes its results with
deterministic rules.

The project includes a FastAPI API, a React/TypeScript dashboard, a CLI client, and an asynchronous
analysis worker. PostgreSQL stores projects, test runs, results, and analysis jobs. Credentials are
read from the environment or a local `.env` file, which is not committed.

## Requirements

- Python 3.9 or later
- Docker with Docker Compose
- Node.js 22.12 or later, only if running or building the dashboard outside Docker

## Local setup

From the repository root, in PowerShell:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Edit `.env` and replace `POSTGRES_PASSWORD` with a local password. Do not use real credentials or
share this file. Install the pinned dependencies and the package:

```powershell
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
docker compose up -d db
python -m alembic upgrade head
```

Start the API:

```powershell
python -m uvicorn main:app --reload
```

The API is available at <http://127.0.0.1:8000>; its health check is
<http://127.0.0.1:8000/health>, and interactive API documentation is at
<http://127.0.0.1:8000/docs>. To stop PostgreSQL, run `docker compose down`. Local data persists in
the `postgres_data` volume; `docker compose down -v` also deletes that volume.

To run the dashboard, API, worker, and PostgreSQL in containers, use the self-hosted profile:

```powershell
docker compose --profile self-hosted up -d --build
```

By default, the dashboard is published at <http://127.0.0.1:8080>, the API at
<http://127.0.0.1:8000>, and PostgreSQL at `127.0.0.1:5432`. The API and PostgreSQL ports are
bound only to the local interface. For a deployment, put an HTTPS reverse proxy in front of the
dashboard; it forwards `/api` and the exact API route `/projects` to the API. See
[docs/authentication-and-self-hosting.md](docs/authentication-and-self-hosting.md) for GitHub App,
cookie, encryption key, legacy workspace, and CI secret configuration.

Compose runs `alembic upgrade head` before starting the API. Stop all services with
`docker compose --profile self-hosted down`; the `postgres_data` volume is preserved. Adding `-v`
also deletes the persisted data.

## Authentication and workspaces

Dashboard sign-in uses a GitHub App configured for the installation. The session is maintained in
an opaque `HttpOnly` cookie; `/api/v1/auth/me` returns the profile and the `X-CSRF-Token` required
for write operations. The dashboard manages this session automatically. Private project, run,
analysis, and workspace routes require a session. `GET /api/v1/workspaces` lists available
workspaces. Members can read projects, runs, results, and analysis in their workspace; only owners
can create projects, manage members, connect repositories, and manage CI tokens.

Each project belongs to a workspace. Existing projects are migrated into a legacy workspace with no
members. Only the GitHub account configured in `TESTPULSE_BOOTSTRAP_GITHUB_USER_ID` can claim it
through `POST /api/v1/workspaces/legacy/claim`.

## Projects API

- `POST /projects`: creates a project with `name` and optional `repository_url` in the personal
  workspace or the specified `workspace_id`. Requires the owner role. Returns `201`; empty names
  or invalid URLs return `422`, and duplicate names within a workspace return `409`.
- `GET /projects`: lists projects in workspaces accessible to the signed-in user.
- `GET /projects/{project_id}`: returns an accessible project or `404`.
- `POST /api/v1/workspaces`: creates a workspace with the current user as its owner.
- `GET /api/v1/workspaces/{workspace_id}/members`, and `POST`/`DELETE` on that route, allow
  listing and managing members; only owners can change membership.
- `GET /api/v1/github/repositories`: paginates through GitHub repositories accessible to the user.
  Owners connect or disconnect a selected repository through
  `/api/v1/projects/{project_id}/repository`; repositories are not imported in bulk.
- `POST /api/v1/projects/{project_id}/ingestion-tokens`: creates a project-scoped ingestion token.
  Its secret is returned only once. The request accepts a `name` of up to 100 characters. Owners
  can revoke tokens with `DELETE` and list metadata, including names, without retrieving secrets.

## Test ingestion and run history

- `POST /api/v1/projects/{project_id}/runs`: requires a project ingestion token in
  `Authorization: Bearer <token>` and accepts JUnit XML in the request body. Supports
  `X-Commit-SHA`, `X-Branch`, `Idempotency-Key`, and optional `X-CI-*` metadata. The token only
  authorizes ingestion for its project. Returns `201` for a new run, `200` when the same key is
  repeated with identical content and metadata, `409` if the key is reused with different content
  or metadata, `401` if the token is missing or invalid, `413` if the report exceeds the configured
  size limit, and `422` for an invalid report.
- `GET /api/v1/projects/{project_id}/runs`: returns a lightweight history page, ordered by
  ingestion time descending and then by run ID descending. Accepts optional `branch`, `limit`
  (default `20`, range `1` to `100`), and `offset` (default `0`, non-negative). The response
  includes `items`, `limit`, `offset`, and `total`; inaccessible or nonexistent projects return
  `404`, and out-of-range parameters return `422`.
- `GET /api/v1/projects/{project_id}/runs/{run_id}`: returns run metadata and database-calculated
  `total`, `passed`, `failed`, `skipped`, and `error` counts. Returns `404` if the project is
  inaccessible or the run does not belong to it.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/results`: returns a page of individual test
  results. Accepts `status` (`passed`, `failed`, `skipped`, or `error`), `limit` (default `20`,
  maximum `100`), and `offset` (default `0`). Includes the total for the selected filter; invalid
  statuses return `422`, and inaccessible or nonexistent projects and runs return `404`.
- `GET /api/v1/projects/{project_id}/analysis/reliability`: analyzes each test's latest
  observations, optionally filtered by branch; without a branch filter it includes all branches.
  Accepts `window_size` (default `20`, maximum `100`)
  and excludes `skipped`. At least 5 valid observations are needed for classification: all passes
  are `stable`, a mix of `passed` and `failed`/`error` is `potentially_flaky`, and all failures are
  `persistently_failing`. Fewer than 5 observations yields `insufficient_data`. The failure rate is
  `(failed + error) / valid observations`, rounded to four decimal places.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/regressions`: compares the run with the
  chronologically previous run on the same branch. It reports only tests present in both runs that
  changed from `passed` to `failed` or `error`; new tests and persistent failures are not new
  regressions. If the run has no comparable previous run, it returns an empty list. Inaccessible or
  nonexistent projects and runs return `404`.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/analysis-job`: returns the durable job for the
  run, including status, attempts, last error, and, when completed, a reliability and regression
  snapshot. Returns `404` if the project or job is unavailable.

The rules for observation windows, reliability classification, and regression comparisons are
documented in [docs/analysis-engine.md](docs/analysis-engine.md).

## Asynchronous processing

Each valid report creates an analysis job in the same transaction as the run and its results.
Repeating an idempotent ingestion returns the existing run and retains its single job. Job states
are `pending`, `processing`, `completed`, and `failed`, with up to three attempts. Errors are stored
on the job and in worker logs. A five-minute lease by default (configurable with `--lease-seconds`)
allows recovery of jobs whose worker stopped while processing them.

The queue is backed by PostgreSQL and needs no external broker. If no worker is active, jobs remain
pending; a worker claims them from the database when it starts. PostgreSQL row locks coordinate
multiple workers, and persisted analysis is idempotent per run. Basic project, history, and result
queries do not require a worker.

Start a worker in a separate terminal after applying migrations:

```powershell
testpulse-worker
```

Use `testpulse-worker --once` to process at most one job and exit. `--poll-interval` sets the delay
between checks when the queue is empty, and `--lease-seconds` controls the lease duration before an
abandoned job can be recovered. Check a run's status and result with its `analysis-job` endpoint.
The reliability and regression endpoints remain available and calculate their responses directly.

## Web dashboard

The dashboard includes GitHub sign-in, a workspace selector, repository connection, and CI setup
with ingestion tokens that are shown only once. Project views let users browse runs, filter by
branch, inspect results, and review reliability and regressions.

With the API and PostgreSQL running, open a separate terminal from the repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Node.js 22.12 or later is required. Open <http://127.0.0.1:5173>. Vite proxies `/api` and the exact
`/projects` API route to `http://127.0.0.1:8000`; UI routes such as `/projects/new` continue to be
served by the dashboard. Set `TESTPULSE_API_TARGET` to change the API target. When serving the
frontend and API on different origins, configure a same-origin reverse proxy for `/api` and
`/projects`.

Run dashboard tests with `npm run test:run`; `npm run typecheck` checks TypeScript, and
`npm run build` creates the static production build in `frontend/dist`.

## CLI client and GitHub Actions

Install the TestPulse package from the repository to get the `testpulse` command:

```powershell
python -m pip install .
```

Generate a pytest report and upload it with the API URL and project ID:

```powershell
python -m pytest --junitxml=test-results.xml
testpulse --url https://testpulse.example.com --project 42 --report test-results.xml
```

`--commit` and `--branch` are optional. By default, the client uses `GITHUB_SHA` or
`CI_COMMIT_SHA` for the commit and `GITHUB_HEAD_REF`, `GITHUB_REF_NAME`, or `CI_COMMIT_REF_NAME` for
the branch. `--idempotency-key` can be provided for manual retries. In GitHub Actions, a stable key
is derived from the repository, run, attempt, and project. Local runs without a key generate a UUID
for each invocation. The ingestion endpoint always requires a valid token: set
`TESTPULSE_API_TOKEN` or provide `--token`. The client sends it as `Authorization: Bearer <token>`.

Set `TESTPULSE_API_TOKEN` in the environment before running the command; it is omitted from the
example so the secret is not included in the README. Avoid passing secrets as command-line
arguments or storing them in the repository.

Example workflow for the project that runs the tests:

```yaml
name: Tests and TestPulse

on:
  push:
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
      - run: python -m pip install pytest
      - name: Install TestPulse CLI
        run: python -m pip install "git+https://github.com/OmarLPGC/TestPulse.git"
      - name: Run tests and generate JUnit XML
        run: python -m pytest --junitxml=test-results.xml
      - name: Upload results to TestPulse
        if: >-
          always() &&
          (github.event_name != 'pull_request' ||
          github.event.pull_request.head.repo.full_name == github.repository)
        env:
          TESTPULSE_URL: ${{ vars.TESTPULSE_URL }}
          TESTPULSE_PROJECT_ID: ${{ vars.TESTPULSE_PROJECT_ID }}
          TESTPULSE_API_TOKEN: ${{ secrets.TESTPULSE_API_TOKEN }}
          TESTPULSE_BRANCH: ${{ github.head_ref || github.ref_name }}
        run: >-
          testpulse --url "$TESTPULSE_URL"
          --project "$TESTPULSE_PROJECT_ID"
          --report test-results.xml
          --commit "$GITHUB_SHA"
          --branch "$TESTPULSE_BRANCH"
```

The example installs the CLI from this repository; use the corresponding package or artifact
source if you distribute it separately. Configure `TESTPULSE_URL` and `TESTPULSE_PROJECT_ID` as
repository variables and `TESTPULSE_API_TOKEN` as a repository secret. Uploads are skipped for
pull requests from forks, which do not receive GitHub secrets. `if: always()` attempts the upload
even when pytest fails, provided the report exists; an upload error fails that step.

## Migrations, tests, and quality checks

Migrations use the database URL from the `POSTGRES_*` environment variables or `.env`. The
integration suite uses PostgreSQL and creates an isolated schema to test migrations from scratch
and check database constraints. With PostgreSQL running and the virtual environment activated, set
the test URL using the same local password as in `.env`:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://testpulse:<POSTGRES_PASSWORD>@127.0.0.1:5432/testpulse"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Replace `<POSTGRES_PASSWORD>` with the local password; if it contains URL-reserved characters,
percent-encode it in the connection URL. If `TEST_DATABASE_URL` is unset, pytest skips PostgreSQL
integration tests. The database user must be allowed to create and drop schemas because each
integration-test run uses an isolated PostgreSQL schema. GitHub Actions starts a clean PostgreSQL
service and runs migrations, tests, lint, formatting, frontend typecheck, and frontend build on
every pull request and every push to `main`. The last command checks formatting without changing
files.
