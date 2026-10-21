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
