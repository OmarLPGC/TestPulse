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

Guarda el token como `TESTPULSE_TOKEN` en los secrets del repositorio y pásalo al CLI como
`TESTPULSE_API_TOKEN` en el entorno del paso. El CLI envía metadata neutral de GitHub Actions
(fuente, run, intento, evento y PR) y una clave idempotente estable; esa metadata no concede
permisos ni se considera una prueba de identidad. No incluyas el valor en YAML, argumentos
versionados o logs. Rota y revoca el token inmediatamente si se expone.

En Actions, ejecuta la subida con `if: always()` para conservar el informe cuando pytest falla. Esto
no cubre cancelaciones del workflow. GitHub no entrega secrets a workflows de `pull_request`
procedentes de forks: omite la subida para esos eventos o usa otra canalización confiable. No uses
`pull_request_target` para ejecutar código de PR no confiable con acceso al token.

## Compose backend

Parte de `.env.example`, copia el archivo a `.env` y sustituye los placeholders. Para el modo
self-hosted del backend:

```powershell
docker compose --profile self-hosted up -d --build
```

Compose mantiene PostgreSQL en una red privada y publica la API solo en `127.0.0.1`. El contenedor
de API aplica migraciones y después inicia Uvicorn; el worker espera a que la API esté saludable.
Coloca un proxy HTTPS delante de la API. El dashboard frontend y su empaquetado no forman parte de
este despliegue backend; configúralos aparte para compartir el mismo origen.

Antes de una actualización, respalda PostgreSQL y comprueba la migración en una copia de los datos.
No uses `docker compose down -v` salvo que quieras eliminar deliberadamente el volumen persistente.
