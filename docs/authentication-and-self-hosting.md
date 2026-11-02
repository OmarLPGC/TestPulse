# Autenticación y operación self-hosted

TestPulse conserva runs, resultados, jobs e histórico en PostgreSQL. GitHub se utiliza para
identidad, descubrimiento de repositorios y metadata CI; no se transfieren resultados fuera de la
instalación.

## Configuración de GitHub App

Cada instalación configura su propia GitHub App. Define su homepage como el origen público de
TestPulse y el callback exactamente como:

```text
https://testpulse.example.com/api/v1/auth/github/callback
```

Concede únicamente permiso de repositorio **Metadata: read-only** y permite su instalación solo en
las cuentas y organizaciones que deban aparecer en el selector. No se requiere permiso de escritura
ni una clave privada de App. El usuario autoriza la App para iniciar sesión; el listado solo puede
mostrar repositorios accesibles al token de usuario y a la instalación de la App. Las organizaciones
pueden exigir que un administrador apruebe o instale la App.

Configura en el entorno:

- `GITHUB_APP_CLIENT_ID` y `GITHUB_APP_CLIENT_SECRET`.
- `GITHUB_APP_CALLBACK_URL` y `PUBLIC_BASE_URL` del origen HTTPS público.
- `GITHUB_TOKEN_ENCRYPTION_KEY`, una clave URL-safe base64 de 32 bytes, generada con:

  ```powershell
  python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  ```

- `APP_ENV=production` para emitir cookies `Secure`.

Los cinco valores GitHub deben configurarse juntos. En producción, la aplicación se niega a iniciar
sin ellos y sin un origen HTTPS. Conserva la clave de cifrado en un gestor de secretos y respáldala
con control de acceso: perderla requiere que los usuarios autoricen GitHub de nuevo. No la cambies
sin una estrategia de re-encriptado. Los access/refresh tokens GitHub se cifran con AES-GCM antes de
persistirse; los tokens de sesión se generan aleatoriamente y solo se conserva su hash.

El login es `GET /api/v1/auth/github/login`; el callback consume un `state` aleatorio de un solo uso,
ligado a una cookie temporal `HttpOnly`. La identidad actual es `GET /api/v1/auth/me` y el cierre de
sesión es `POST /api/v1/auth/logout`. Las sesiones son revocables y caducan según
`SESSION_TTL_SECONDS` (por defecto 14 días, máximo 90 días). Las cookies usan `HttpOnly`,
`SameSite=Lax` y `Secure` en producción. Para las operaciones de sesión que modifican datos, el
cliente debe enviar en `X-CSRF-Token` el valor recibido en `/me`; no guardes tokens GitHub ni de
sesión en `localStorage`.

Sirve el dashboard y la API bajo el mismo origen, usando un proxy inverso para `/api` y `/projects`.
No habilites CORS permisivo. Termina TLS en el proxy y evita publicar directamente el puerto de la
API o PostgreSQL en interfaces públicas.

## Workspace legado

La migración `0005` mueve todos los proyectos existentes a un workspace legado sin miembros. No
asigna esos datos al primer usuario que inicia sesión. Para reclamarlo, configura
`TESTPULSE_BOOTSTRAP_GITHUB_USER_ID` con el ID numérico GitHub del único responsable autorizado y,
tras iniciar sesión con esa cuenta, llama a `POST /api/v1/workspaces/legacy/claim`. Sin el valor, la
operación falla explícitamente; una cuenta distinta recibe `403`. El valor debe provisionarse por
canal administrativo seguro, no desde una petición de usuario.

Cada usuario nuevo recibe un workspace personal. Los roles son `owner` y `member`: los miembros
pueden consultar proyectos, ejecuciones, resultados y análisis; solo owners pueden crear proyectos,
administrar miembros, conectar repositorios o gestionar tokens CI. Los recursos fuera de los
workspaces del usuario responden como inexistentes para evitar filtraciones por enumeración de IDs.

## Repositorios GitHub

`GET /api/v1/github/repositories` devuelve páginas de hasta 100 repositorios accesibles al usuario.
No se importan repositorios en lote. Un owner conecta o desconecta un repositorio seleccionado desde
`/api/v1/projects/{project_id}/repository`; antes de guardar se verifica contra GitHub el ID, nombre
y permiso de lectura. El ID GitHub estable y el nombre completo se guardan junto al proyecto. Si se
revoca el acceso o la instalación deja de exponer el repositorio, vuelve a autorizar la App o instala
la App en la organización correspondiente.

## Ingesta desde CI

Un owner crea un token de proyecto con `POST /api/v1/projects/{project_id}/ingestion-tokens`. El
valor secreto se muestra solo en la respuesta de creación; la base de datos conserva únicamente su
hash. Se limita a subir JUnit para un solo proyecto: no autoriza lecturas, análisis ni otros
proyectos. Los owners pueden listar metadatos de tokens y revocarlos mediante
`DELETE /api/v1/projects/{project_id}/ingestion-tokens/{token_id}`.

Guarda el token como un secret del repositorio. El workflow generado desde el dashboard lo consume
como `TESTPULSE_TOKEN`; el CLI lo lee como `TESTPULSE_API_TOKEN`, por lo que, si reutilizas el
secret `TESTPULSE_TOKEN` con el CLI, asígnalo a `TESTPULSE_API_TOKEN` en el entorno del paso. El CLI
envía metadata neutral de GitHub Actions (fuente, run, intento, evento y PR) y una clave
idempotente estable; esa metadata no concede permisos ni se considera una prueba de identidad. No
incluyas el valor en YAML, argumentos versionados o logs. Rota y revoca el token inmediatamente si
se expone.

En Actions, ejecuta la subida con `if: always()` para conservar el informe cuando pytest falla. Esto
no cubre cancelaciones del workflow. GitHub no entrega secrets a workflows de `pull_request`
procedentes de forks: omite la subida para esos eventos o usa otra canalización confiable. No uses
`pull_request_target` para ejecutar código de PR no confiable con acceso al token.

## Compose self-hosted

Parte de `.env.example`, copia el archivo a `.env` y sustituye los placeholders. Para iniciar el
dashboard, la API, el worker y PostgreSQL:

```powershell
docker compose --profile self-hosted up -d --build
```

Compose mantiene los servicios en una red privada. Publica el dashboard, la API y PostgreSQL solo
en `127.0.0.1`; el dashboard Nginx sirve la aplicación y reenvía `/api` y `/projects` a la API. El
contenedor de API aplica migraciones y después inicia Uvicorn; el worker espera a que la API esté
saludable. En despliegues públicos, coloca un proxy HTTPS delante del dashboard y configura
`PUBLIC_BASE_URL` y el callback GitHub para ese origen.

Antes de una actualización, respalda PostgreSQL y comprueba la migración en una copia de los datos.
No uses `docker compose down -v` salvo que quieras eliminar deliberadamente el volumen persistente.

## English

# Authentication and self-hosting

TestPulse stores runs, results, jobs, and history in PostgreSQL. GitHub is used for identity,
repository discovery, and CI metadata; results are not transferred outside the installation.

## GitHub App configuration

Each installation configures its own GitHub App. Set its homepage to the public TestPulse origin
and its callback URL exactly as follows:

```text
https://testpulse.example.com/api/v1/auth/github/callback
```

Grant only the **Metadata: read-only** repository permission, and allow the App to be installed
only on the accounts and organizations that should appear in the selector. No write permission or
App private key is required. The user authorizes the App to sign in; the repository list can show
only repositories accessible to the user's token and the App installation. Organizations may
require an administrator to approve or install the App.

Configure these environment variables:

- `GITHUB_APP_CLIENT_ID` and `GITHUB_APP_CLIENT_SECRET`.
- `GITHUB_APP_CALLBACK_URL` and `PUBLIC_BASE_URL` for the public HTTPS origin.
- `GITHUB_TOKEN_ENCRYPTION_KEY`, a URL-safe base64-encoded 32-byte key generated with:

  ```powershell
  python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  ```

- `APP_ENV=production` to issue `Secure` cookies.

All five GitHub values must be configured together. In production, the application refuses to
start without them and an HTTPS origin. Keep the encryption key in a secrets manager and back it
up with access controls: losing it requires users to authorize GitHub again. Do not change it
without a re-encryption strategy. GitHub access and refresh tokens are encrypted with AES-GCM
before persistence; session tokens are generated randomly, and only their hashes are stored.

Sign-in starts at `GET /api/v1/auth/github/login`; the callback consumes a random, single-use
`state` value bound to a temporary `HttpOnly` cookie. The current identity is available at
`GET /api/v1/auth/me`, and sign-out is `POST /api/v1/auth/logout`. Sessions can be revoked and
expire according to `SESSION_TTL_SECONDS` (14 days by default, up to 90 days). Cookies use
`HttpOnly`, `SameSite=Lax`, and `Secure` in production. For session operations that modify data,
the client must send the value received from `/me` in `X-CSRF-Token`; do not store GitHub or
session tokens in `localStorage`.

Serve the dashboard and API under the same origin, using a reverse proxy for `/api` and `/projects`.
Do not enable permissive CORS. Terminate TLS at the proxy and do not expose the API or PostgreSQL
ports directly on public interfaces.

## Legacy workspace

Migration `0005` moves all existing projects into a legacy workspace with no members. It does not
assign that data to the first user who signs in. To claim it, configure
`TESTPULSE_BOOTSTRAP_GITHUB_USER_ID` with the numeric GitHub ID of the sole authorized owner and,
after signing in with that account, call `POST /api/v1/workspaces/legacy/claim`. Without the
setting, the operation fails explicitly; a different account receives `403`. Provision this
setting through a secure administrative channel, not through a user request.

Each new user receives a personal workspace. The roles are `owner` and `member`: members can view
projects, runs, results, and analyses; only owners can create projects, manage members, connect
repositories, or manage CI tokens. Resources outside a user's workspaces respond as not found to
prevent ID enumeration.

## GitHub repositories

`GET /api/v1/github/repositories` returns pages of up to 100 repositories accessible to the user.
Repositories are not imported in bulk. An owner connects or disconnects a selected repository
using `/api/v1/projects/{project_id}/repository`; before saving, TestPulse verifies the ID, name,
and read permission with GitHub. The stable GitHub ID and full name are stored with the project. If
access is revoked or the installation no longer exposes the repository, authorize the App again or
install it in the relevant organization.

## Ingestion from CI

An owner creates a project-scoped token with `POST /api/v1/projects/{project_id}/ingestion-tokens`.
The secret is shown only in the creation response; the database stores only its hash. The token can
upload JUnit results for one project and does not authorize reads, analyses, or access to other
projects. Owners can list token metadata and revoke tokens using
`DELETE /api/v1/projects/{project_id}/ingestion-tokens/{token_id}`.

Store the token as a repository secret. A workflow generated from the dashboard consumes it as
`TESTPULSE_TOKEN`; the CLI reads `TESTPULSE_API_TOKEN`, so if you reuse the `TESTPULSE_TOKEN`
secret with the CLI, map it to `TESTPULSE_API_TOKEN` in the step's environment. The CLI sends
neutral GitHub Actions metadata (source, run, attempt, event, and PR) and a stable idempotency key;
this metadata does not grant permissions or prove identity. Do not include the secret value in YAML,
versioned arguments, or logs. Rotate and revoke the token immediately if it is exposed.

In Actions, run the upload with `if: always()` to preserve the report when pytest fails. This does
not cover workflow cancellations. GitHub does not provide secrets to `pull_request` workflows
originating from forks: skip the upload for those events or use another trusted pipeline. Do not
use `pull_request_target` to run untrusted PR code with access to the token.

## Self-hosted Compose

Start from `.env.example`, copy it to `.env`, and replace the placeholders. To start the dashboard,
API, worker, and PostgreSQL:

```powershell
docker compose --profile self-hosted up -d --build
```

Compose keeps the services on a private network. It publishes the dashboard, API, and PostgreSQL
only on `127.0.0.1`; dashboard Nginx serves the application and forwards `/api` and `/projects` to
the API. The API container applies migrations and then starts Uvicorn; the worker waits for the
API to become healthy. For public deployments, put an HTTPS proxy in front of the dashboard and
configure `PUBLIC_BASE_URL` and the GitHub callback for that origin.

Before upgrading, back up PostgreSQL and test the migration on a copy of the data. Do not use
`docker compose down -v` unless you intend to delete the persistent volume.
