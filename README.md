# Documind

Microservicio de recomendación de documentos con búsqueda semántica sobre embeddings almacenados en PostgreSQL (pgvector).

## Casos de uso

- Subir documentos PDF con metadatos opcionales (año de publicación, autor, descripción, categoría, idioma, imagen de portada).
- Cada documento se divide en chunks con trazabilidad exacta de página/línea de inicio y fin; cada chunk se convierte a embedding y se almacena en PostgreSQL.
- Se genera automáticamente un resumen del documento con IA y se registran los tokens consumidos al generar los embeddings.
- Descargar el documento original íntegro (verificable por SHA-256).
- Listar documentos con filtros ricos (nombre, páginas, chunks, tamaño, fecha de subida, resumen, metadatos, número de búsquedas con coincidencia).
- Búsqueda semántica en lenguaje natural: devuelve los 10 chunks más similares, los documentos a los que pertenecen (sin duplicados, en el mismo orden) y metadatos (tokens de la consulta, tiempo total de respuesta).
- Histórico auditable de búsquedas con sus respuestas, consultable por rango de fechas.

## Tecnologías

| Componente | Tecnología |
|---|---|
| API | FastAPI + Uvicorn (async) |
| Base de datos | PostgreSQL 16 + extensión pgvector (índice HNSW, distancia coseno) |
| Cola de tareas | Redis 7 + arq (ingesta asíncrona en un worker aparte) |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dimensiones) |
| Resúmenes IA | OpenAI (`gpt-4o-mini` por defecto, configurable) |
| Parsing PDF | pypdf |
| Gestor de paquetes | uv |
| Tests | pytest + pytest-asyncio |
| Linting | ruff |

## Arquitectura

```
app/
├── main.py               # FastAPI app, lifespan (pool de la cola), manejadores globales de errores
├── worker.py             # worker arq: ejecuta los jobs de ingesta (proceso aparte)
├── config.py             # Settings (pydantic-settings, variables de entorno)
├── core/                 # auth por API key, cola (arq), excepciones, notificaciones Telegram
├── db/                   # engine async, modelos SQLAlchemy (documents, chunks, api_keys, search_history)
├── routers/              # endpoints: documents, search, search/history
├── schemas/              # modelos Pydantic de entrada/salida
└── services/             # pdf_parser, chunking, embeddings, summarizer, storage, document_ingestion
scripts/                  # create_api_key.py (CLI)
sql/                      # init_database.sql + migraciones de referencia
tests/                    # tests unitarios (chunking, auth, storage, parser, notificaciones)
frontend/                 # SPA React + Vite + TypeScript (interfaz para clientes finales)
```

### Interfaz web (frontend)

`frontend/` es una SPA en React (Vite + TypeScript) para los clientes finales: subir, listar y eliminar documentos, búsqueda semántica e historial. La autenticación es por **API key**: el cliente introduce su `X-API-Key` (como un login), se guarda en `localStorage` del navegador y se envía en cada petición. En producción, un **nginx** sirve la SPA y hace de reverse-proxy de `/api` hacia el contenedor `api` por la red interna de Docker — así la API nunca se expone directamente y no hay CORS.

> ⚠️ La API key vive en el navegador (`localStorage`), visible para quien use esa sesión. Es apropiado cuando **cada cliente final es el titular de su propia API key**. Si los usuarios fueran anónimos/no confiables, habría que anteponer un backend propio (BFF) que guarde la clave del lado servidor.

Desarrollo del frontend:

```bash
cd frontend
npm install
npm run dev   # Vite en :5173, con proxy /api → http://localhost:8010 (backend local)
```

Decisiones de diseño:

- **Ingesta asíncrona**: `POST /documents` responde `202 Accepted` de inmediato (guarda el archivo y crea la fila con `status="processing"`); un worker arq consume el job desde Redis y hace el trabajo pesado (parseo, embeddings, resumen). Al terminar marca `status="ready"` (o `"failed"` + alerta Telegram si algo falla). El cliente consulta `GET /documents/{name}` hasta ver `ready`. Solo los documentos `ready` participan en la búsqueda semántica.
- **Almacenamiento de archivos**: los PDF originales y las portadas se guardan en el sistema de archivos (`DATA_DIR`), y la BD guarda la ruta, el hash SHA-256 y el tamaño. La descarga se sirve con `FileResponse` (streaming), garantizando integridad sin inflar la base de datos.
- **Eliminación lógica**: columna `deleted_at`; los documentos eliminados no aparecen en listados, búsquedas ni descargas. El nombre queda libre para reutilizarse (índice único parcial `WHERE deleted_at IS NULL`).
- **Chunking**: agrupa líneas consecutivas hasta `MAX_CHUNK_CHARS` sin partir líneas, de modo que página/línea de inicio y fin son exactas.
- **Búsqueda**: distancia coseno de pgvector sobre todos los chunks de documentos activos y `ready`, top 10, con índice HNSW. Cada búsqueda incrementa `search_hit_count` en los documentos con coincidencia y se archiva íntegra (consulta + respuesta) para auditoría.
- **Caché de embeddings de consulta (Redis)**: el vector de cada consulta de búsqueda se cachea en Redis con TTL (clave = hash de `modelo + consulta`). Una búsqueda repetida evita la llamada a OpenAI (0 tokens, respuesta en ms). Solo aplica a `embed_query`; los embeddings de chunks se generan una vez y viven en Postgres. Si Redis falla, la búsqueda cae con gracia a una llamada en vivo. Configurable con `EMBEDDING_CACHE_ENABLED` / `EMBEDDING_CACHE_TTL_SECONDS`.
- **Autenticación**: header `X-API-Key`. Las claves se almacenan hasheadas (SHA-256) en la tabla `api_keys`, con revocación (`is_active`) y registro de último uso.
- **Agente de respuesta (RAG)**: en cada búsqueda, un agente IA responde la consulta usando exclusivamente los 10 chunks recuperados; si la respuesta no está contenida en ellos devuelve `NOT_FOUND` (campo `answer: null`). La respuesta viaja en el endpoint y se persiste en el histórico.
- **Agente de alcance**: un prompt persistido en BD (`/settings/search-scope`, editable desde la UI) define qué consultas son válidas; un agente valida cada consulta antes de procesarla (`in_scope`), y el veredicto queda en el histórico (`passed_validation`). Alcance vacío = validación desactivada. Fail-open: si el agente falla, la búsqueda continúa.
- **Historial de subidas**: cada archivo subido registra su resultado en `upload_history` — `success`, `skipped_duplicate` (dedup por SHA-256) o `failed` con el traceback completo del error.
- **Subida múltiple**: `POST /documents` acepta varios PDF en un solo request y los registra en paralelo (sesiones de BD independientes); la ingesta pesada ya era paralela vía worker.

## Endpoints

Todos (excepto `/health`) requieren el header `X-API-Key`. **Referencia completa para integradores/frontends en [docs/API.md](docs/API.md)** (modelos, ejemplos de respuesta, flujos y manejo de errores); interactiva en `/api/docs` (Swagger); colección de Postman lista para importar en [docs/Launch-Intelligence.postman_collection.json](docs/Launch-Intelligence.postman_collection.json).

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/documents` | Subir uno o varios PDF (multipart, campo `files` repetible) → `202` con resultado por archivo (`processing` / `skipped_duplicate` / `failed`). Campos opcionales: `name` y `cover_image` (solo con 1 archivo), `publication_year`, `author`, `description`, `category`, `language` |
| `GET` | `/documents` | Listar con filtros: `name`, `status`, `min/max_pages`, `min/max_chunks`, `min/max_size_bytes`, `uploaded_from/to`, `summary`, `publication_year`, `author`, `description`, `category`, `language`, `has_cover_image`, `min/max_search_hits`, `limit`, `offset` |
| `GET` | `/documents/{name}` | Obtener metadatos de un documento por nombre |
| `GET` | `/documents/{name}/download` | Descargar el archivo original íntegro |
| `GET` | `/documents/{name}/cover` | Descargar la imagen de portada |
| `DELETE` | `/documents/{name}` | Eliminación lógica |
| `POST` | `/search` | Búsqueda semántica. Body: `{"query": "..."}`. Devuelve chunks, documentos, `answer` (agente RAG, `null` = NOT_FOUND) e `in_scope` (validación de alcance) |
| `GET` | `/uploads` | Historial de subidas: `outcome`, `from_date`, `to_date`, `limit`, `offset` |
| `GET` | `/settings/search-scope` | Leer el prompt que define el alcance de las búsquedas |
| `PUT` | `/settings/search-scope` | Actualizar el prompt de alcance (vacío = validación desactivada) |
| `GET` | `/search/history` | Historial de búsquedas: `from_date`, `to_date`, `limit`, `offset` |
| `GET` | `/health` | Health check (sin auth) |

Documentación interactiva (Swagger): `http://localhost:8000/docs`

## Variables de entorno

Copiar `.env.example` a `.env` y completar:

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | Conexión PostgreSQL (asyncpg) |
| `REDIS_URL` | Conexión Redis para la cola de ingesta y la caché de embeddings (dev: `redis://localhost:6380`) |
| `EMBEDDING_CACHE_ENABLED` / `EMBEDDING_CACHE_TTL_SECONDS` | Caché de embeddings de consulta en Redis (por defecto activada, TTL 24 h) |
| `OPENAI_API_KEY` | **Requerida.** Para embeddings y resúmenes con IA |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | Modelo de embeddings (por defecto `text-embedding-3-small`, 1536) |
| `SUMMARY_MODEL` | Modelo OpenAI para resúmenes (por defecto `gpt-4o-mini`) |
| `MAX_CHUNK_CHARS` | Tamaño máximo de chunk en caracteres (1200) |
| `SEARCH_TOP_K` | Chunks devueltos por búsqueda (10) |
| `DATA_DIR` | Carpeta local para archivos y portadas |
| `API_ALLOWED_HOSTS` | IPs/CIDRs (separados por coma) con acceso a la API; `*` = cualquier cliente (defecto). `/health` queda siempre accesible. Complementa a la API key, no la sustituye |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Opcional: notificación de errores críticos al dev |

## Cómo ejecutar

```bash
# 1. Levantar PostgreSQL (pgvector) y Redis
docker compose up -d

# 2. Instalar dependencias
uv sync

# 3. Configurar entorno
copy .env.example .env   # y completar las API keys

# 4. Crear una API key para un cliente
uv run python scripts/create_api_key.py --name "mi-cliente"

# 5. Iniciar el worker de ingesta (terminal aparte)
uv run arq app.worker.WorkerSettings

# 6. Iniciar la API
uv run uvicorn app.main:app --reload
```

Ejemplo de uso:

```bash
# Subir un documento
curl -X POST http://localhost:8000/documents \
  -H "X-API-Key: <tu-api-key>" \
  -F "file=@libro.pdf" \
  -F "author=Gabriel García Márquez" \
  -F "publication_year=1967" \
  -F "category=novela" \
  -F "language=es" \
  -F "cover_image=@portada.jpg"
# → 202 Accepted { "status": "processing", ... }

# Consultar el estado hasta que el worker termine ("ready" o "failed")
curl http://localhost:8000/documents/libro -H "X-API-Key: <tu-api-key>"
# → { "status": "ready", "chunk_count": 214, "summary": "...", ... }

# Búsqueda semántica
curl -X POST http://localhost:8000/search \
  -H "X-API-Key: <tu-api-key>" -H "Content-Type: application/json" \
  -d '{"query": "una historia sobre varias generaciones de una familia en un pueblo"}'
```

## Backup y migración de servidor

Los datos viven en dos sitios: PostgreSQL (documentos, chunks + embeddings, api keys, históricos, ajustes) y el volumen `documents` (PDFs y portadas). Los scripts exportan/importan ambos:

```bash
# En el servidor origen (stack corriendo):
./scripts/export_backup.sh                    # → backups/<fecha>/database.dump + documents.tar.gz

# En el servidor destino (tras clonar, crear .env y levantar el stack):
./scripts/import_backup.sh backups/<fecha>    # pg_restore --clean + restauración de archivos
```

El formato es `pg_dump -Fc` (comprimido, portable entre versiones de Postgres compatibles) + tar.gz del directorio de datos. Las API keys se conservan, así que los clientes no necesitan re-emitirse claves.

## Tests y linting

```bash
uv run pytest
uv run ruff check
```

## APIs externas / claves requeridas

- **OpenAI API**: única clave requerida. `/v1/embeddings` para embeddings (reporta `usage.total_tokens`, persistido por documento y por búsqueda) y `/v1/chat/completions` para el resumen del documento.
- **Telegram Bot API** (opcional): notificación al dev de errores críticos, documentos ingestados y búsquedas realizadas.

## Áreas de mejora

- Soporte de más formatos (TXT, Markdown, DOCX) con paginación sintética.
- Re-ranking de resultados y filtrado por umbral de similitud.
- Migraciones con Alembic en lugar de `create_all`.
- Rate limiting por API key.

---

Copyright © Osliani Figueiras Saucedo
