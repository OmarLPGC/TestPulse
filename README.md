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

Para levantar API y worker en contenedores junto a PostgreSQL, usa el perfil self-hosted:

```powershell
docker compose --profile self-hosted up -d --build
```

La API se publica por defecto solo en `127.0.0.1`; coloca un proxy HTTPS delante en despliegues.
Consulta [docs/authentication-and-self-hosting.md](docs/authentication-and-self-hosting.md) para
configurar la GitHub App, las cookies, la clave de cifrado, el workspace legado y los secrets de CI.
El despliegue Compose de este alcance es backend-only; el empaquetado del dashboard se configura
por separado.

## Autenticación y workspaces

Las rutas de proyectos, ejecuciones, análisis y jobs requieren una sesión iniciada mediante la
GitHub App. La sesión usa una cookie opaca `HttpOnly`; `/api/v1/auth/me` devuelve el perfil y el
`X-CSRF-Token` que debe acompañar las operaciones de escritura. `GET /api/v1/workspaces` lista los
workspaces disponibles. Los members pueden consultar recursos; solo owners pueden crear proyectos,
gestionar miembros, conectar repositorios y administrar tokens CI.

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
  proyecto, visible solo en la respuesta de creación. Owners pueden revocarlo mediante `DELETE` y
  listar metadatos sin recuperar el secreto.

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
  observaciones de una rama opcional. Acepta `window_size` (predeterminado `20`, máximo `100`) y
  excluye `skipped`. Se necesitan al menos 5 observaciones válidas para clasificar; una mezcla de
  `passed` y `failed`/`error` se marca como `potentially_flaky`, mientras que fallos en todas las
  observaciones se clasifican como `persistently_failing`. También informa la tasa de fallo,
  calculada como `(failed + error) / observaciones válidas`.
- `GET /api/v1/projects/{project_id}/runs/{run_id}/regressions`: compara la ejecución con la
  ejecución cronológicamente anterior de la misma rama. Solo informa tests presentes en ambas que
  cambian de `passed` a `failed` o `error`; los tests nuevos y los fallos persistentes no son nuevas
  regresiones. Devuelve una lista vacía si no hay casos que cumplan las condiciones. Proyectos o
  ejecuciones inexistentes devuelven `404`.
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
minutos permite recuperar trabajos cuyo proceso se haya detenido mientras los ejecutaba.

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

El dashboard React/TypeScript permite explorar proyectos, filtrar el historial por rama, consultar
el resumen y los resultados de una ejecución, ver trazas de fallos como texto y revisar tests
potencialmente inestables o regresiones.

Las rutas de datos ahora requieren una sesión GitHub y las escrituras requieren `X-CSRF-Token`.
La integración de login y CSRF del dashboard queda fuera de este alcance backend-only; hasta que el
frontend la implemente, el dashboard existente no podrá consultar ni modificar estos datos.

Con la API y PostgreSQL iniciados, abre otra terminal desde la raíz del repositorio:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Necesitas Node.js 22.12 o posterior. Abre <http://127.0.0.1:5173>. Vite reenvía `/projects` y `/api` a
`http://127.0.0.1:8000`; cambia el destino con `TESTPULSE_API_TARGET` si la API escucha en otro
host. Para desplegar el frontend y la API en orígenes diferentes, configura un proxy inverso de
misma procedencia para esas rutas.

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
testpulse --url https://testpulse.example.com --project 42 --report test-results.xml `
  --commit $env:GITHUB_SHA --branch $env:GITHUB_REF_NAME
```

`--commit` y `--branch` son opcionales; el cliente los toma de `GITHUB_SHA` y `GITHUB_REF_NAME` o
de `CI_COMMIT_SHA` y `CI_COMMIT_REF_NAME`. Se puede proporcionar `--idempotency-key` para reintentos
manuales. En GitHub Actions se genera una clave estable por repositorio, ejecución, intento y
proyecto. En ejecuciones locales sin esos metadatos se genera un UUID por invocación.
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
        if: always()
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
variables del repositorio y el token, si el servidor lo requiere, como secreto. El comando termina
con código distinto de cero ante errores de red, autenticación, validación o servidor. `if: always()`
intenta subir el informe aunque fallen los tests.

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
