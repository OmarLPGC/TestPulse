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

Las reglas de ventana, clasificación de fiabilidad y comparación de regresiones se describen con
detalle en [docs/analysis-engine.md](docs/analysis-engine.md).

## Dashboard web

El dashboard React/TypeScript permite explorar proyectos, filtrar el historial por rama, consultar
el resumen y los resultados de una ejecución, ver trazas de fallos como texto y revisar tests
potencialmente inestables o regresiones.

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
