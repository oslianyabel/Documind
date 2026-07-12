# Launch-Intelligence — Referencia de la API

Guía para construir un cliente/frontend contra la API. Complemento interactivo: Swagger en `/{base}/docs` (p. ej. `https://tu-dominio.com/api/docs`).

## Base URL

| Entorno | Base URL |
|---|---|
| Producción, túnel Cloudflare **dedicado a la API** (TLS, sin prefijo) | `https://<tunel-api>.trycloudflare.com` |
| Producción, vía proxy del frontend (TLS, con prefijo) | `https://<dominio-frontend>/api` |
| Producción, puerto directo de la API (HTTP plano; para LAN/VPN o si pones TLS delante) | `http://<host-vps>:8000` |
| Desarrollo (API directa) | `http://localhost:8010` |

Todas las rutas de este documento son relativas a esa base. ⚠️ Por el túnel dedicado y el puerto directo las rutas van **sin** el prefijo `/api` (`https://<tunel-api>…/documents`); ese prefijo solo existe en la vía del proxy del frontend. El Swagger interactivo solo renderiza bien por la ruta con proxy (`…/api/docs`).

## Autenticación

Todos los endpoints exigen el header — **excepto** `GET /health`, `GET /documents/{name}/download` y `GET /documents/{name}/cover`, que son públicos:

```
X-API-Key: <clave>
```

- Las claves las emite el operador del sistema (`scripts/create_api_key.py`); no hay registro self-service.
- Clave ausente o inválida → **`401 {"detail": "..."}`**. Ante un 401 el cliente debe descartar la clave guardada y pedirla de nuevo.
- ⚠️ Si el cliente es una SPA/app pública, la clave es visible para el usuario final. Cada cliente final debe usar **su propia** clave (tratarla como credencial de login), nunca incrustar una compartida en el bundle.

## Formato de errores

Siempre JSON: `{"detail": "mensaje"}`.

| Código | Cuándo |
|---|---|
| 400 | Petición inválida (p. ej. archivo no soportado en endpoints antiguos) |
| 401 | API key ausente/incorrecta |
| 404 | Documento inexistente (o sin portada en `/cover`) |
| 422 | Validación de parámetros (formato de query params/body) |
| 500 | Error interno (se notifica al operador automáticamente) |

---

## Documentos

### Modelo `Document`

```jsonc
{
  "id": "uuid",
  "name": "informe-2024",              // identificador legible y único entre documentos activos
  "original_filename": "informe.pdf",
  "mime_type": "application/pdf",
  "sha256": "…",                        // hash del contenido (integridad / dedupe)
  "size_bytes": 123456,
  "status": "processing | ready | failed",
  "page_count": 19,                     // 0 mientras status = processing
  "chunk_count": 32,                    // 0 mientras status = processing
  "summary": "Resumen generado por IA…" , // null mientras procesa o si su generación falló
  "summary_generated": true,            // false = el resumen falló/está pendiente; regenerable vía POST /documents/{name}/summary
  "embedding_tokens_used": 10945,
  "publication_year": 2024,             // opcionales: null si no se aportaron
  "author": "…",
  "description": "…",
  "category": "…",
  "language": "es",
  "has_cover_image": true,
  "search_hit_count": 4,                // nº de búsquedas en las que ha aparecido
  "created_at": "2026-07-10T12:00:00Z",
  "download_url": "/documents/informe-2024/download"  // relativa a la base; pública (sin X-API-Key)
}
```

**Ciclo de vida (`status`)**: la subida devuelve `processing`; un worker en segundo plano parsea, genera embeddings y resumen, y lo pasa a `ready` (o `failed`). **Solo los documentos `ready` participan en la búsqueda.** Patrón recomendado: tras subir, hacer *polling* de `GET /documents/{name}` cada ~3 s hasta que `status != "processing"`.

### `POST /documents` — subir uno o varios PDF

`multipart/form-data`. Devuelve **`202 Accepted`** con el resultado por archivo (la ingesta continúa en segundo plano).

| Campo | Tipo | Notas |
|---|---|---|
| `files` | file (repetible) | **Requerido.** Uno o más PDF. Repetir el campo por cada archivo. |
| `name` | string | Solo aplica con **1** archivo; si se omite se usa el nombre del archivo sin extensión. |
| `cover_image` | file | Imagen de portada; solo aplica con **1** archivo. |
| `publication_year` | int | Compartidos: aplican a todos los archivos del lote. |
| `author`, `description`, `category`, `language` | string | Compartidos. |

Respuesta:

```jsonc
{
  "items": [
    {
      "filename": "a.pdf",
      "outcome": "processing",          // aceptado; ingesta en curso
      "detail": null,
      "document": { …Document… }        // con status = processing
    },
    {
      "filename": "b.pdf",
      "outcome": "skipped_duplicate",   // mismo contenido (sha256) ya indexado: NO se reprocesa
      "detail": "El contenido ya existe como 'informe-2024'",
      "document": { …Document existente… }
    },
    {
      "filename": "c.txt",
      "outcome": "failed",              // p. ej. no es PDF, o nombre en conflicto
      "detail": "Solo se admiten documentos PDF",
      "document": null
    }
  ]
}
```

`outcome` ∈ `processing | skipped_duplicate | failed`. Los duplicados se detectan por **hash del contenido**, aunque el archivo tenga otro nombre. El resultado final de cada subida (`success`/`failed`) queda en `GET /uploads`.

### `GET /documents` — listar con filtros

Query params (todos opcionales salvo paginación):

```
name (subcadena) · status (processing|ready|failed) · min_pages/max_pages ·
min_chunks/max_chunks · min_size_bytes/max_size_bytes ·
uploaded_from/uploaded_to (ISO 8601) · summary (subcadena) ·
publication_year · author (subcadena) · description (subcadena) ·
category · language · has_cover_image (bool) ·
min_search_hits/max_search_hits · limit (1-100, def. 20) · offset (def. 0)
```

Respuesta: `{ "items": [Document…], "total": n, "limit": n, "offset": n }`

### `GET /documents/{name}` — detalle

Devuelve el `Document`. Úsalo para el polling del estado tras subir.

### `GET /documents/{name}/download` — descargar el PDF original

Respuesta binaria (`application/pdf`, `Content-Disposition` con el nombre original). **Público (sin `X-API-Key`)**: un `<a href="{base}{download_url}">` directo funciona, y la URL es compartible. El campo `download_url` de cada documento ya trae la ruta lista para concatenar a la base.

### `GET /documents/{name}/cover` — portada

Imagen binaria. `404` si el documento no tiene portada (comprobar antes `has_cover_image`). También **pública**: puede usarse directamente como `src` de un `<img>`.

### `POST /documents/{name}/summary` — verificar/generar el resumen IA

Si el resumen ya existe lo devuelve tal cual; si no (falló durante la ingesta), lo **genera y persiste** en el momento.

```jsonc
{ "document_name": "informe-2024", "summary": "…", "generated_now": false }
// generated_now: true = se generó en esta petición; false = ya existía
```

Errores propios: `409` si el documento aún está `processing` (el resumen llegará al terminar la ingesta) · `502` si el proveedor de IA falla al generarlo.

### `DELETE /documents/{name}`

`204 No Content`. Eliminación lógica: desaparece de listados, búsquedas y descargas; el nombre queda libre para reutilizarse.

---

## Búsqueda semántica

### `POST /search`

```json
{ "query": "¿qué fallo reporta el sensor de oxígeno?" }
```

(`query`: 1–2000 caracteres, lenguaje natural.)

Respuesta:

```jsonc
{
  "in_scope": true,          // false = consulta rechazada por el agente de alcance (ver abajo)
  "answer": "El sensor reporta el fallo P0135 en el banco 1 [informe-2024]",
  //          ↑ respuesta del agente IA basada SOLO en los documentos.
  //          null = la respuesta no está contenida en los documentos (NOT_FOUND)
  //                 o la consulta estaba fuera de alcance.
  "chunks": [                 // 10 fragmentos más similares (SEARCH_TOP_K), orden desc. por similitud
    {
      "document_name": "informe-2024",
      "start_page": 1, "start_line": 37,
      "end_page": 2,   "end_line": 28,
      "text": "…contenido del fragmento…",
      "similarity": 0.531     // 1 - distancia coseno; mayor = más similar
    }
  ],
  "documents": [ …Document… ], // documentos de los chunks, sin duplicados,
                               // en el mismo orden de aparición (traen download_url)
  "metadata": {
    "embedding_tokens": 15,    // 0 si el vector vino de caché
    "total_time_ms": 1830.5
  }
}
```

**Validación de alcance:** el operador puede definir un prompt (`/settings/search-scope`) que delimita qué consultas son válidas. Si un agente IA determina que la consulta está fuera de ese alcance, la búsqueda **no se ejecuta** y la respuesta llega con `in_scope: false`, `chunks: []`, `documents: []`, `answer: null`. El frontend debe mostrar un aviso claro en ese caso.

**UI sugerida para `answer`:** si `answer != null`, mostrarla destacada como "respuesta basada en los documentos"; si es `null` con chunks presentes, indicar que la respuesta no está contenida en los documentos (los fragmentos siguen siendo útiles).

### `GET /search/history` — histórico de búsquedas

Query params: `from_date`, `to_date` (ISO 8601, inclusive), `limit` (1-200, def. 50), `offset`.

```jsonc
{
  "items": [
    {
      "id": "uuid",
      "query_text": "…",
      "response": { …SearchResponse íntegra, incluida answer… },
      "embedding_tokens": 15,
      "duration_ms": 1830.5,
      "passed_validation": true,   // false = rechazada por el agente de alcance
      "created_at": "2026-07-10T12:00:00Z"
    }
  ],
  "total": n, "limit": n, "offset": n
}
```

---

## Historial de subidas

### `GET /uploads`

Query params: `outcome` (`processing|success|skipped_duplicate|failed`), `from_date`, `to_date`, `limit` (1-200, def. 50), `offset`.

```jsonc
{
  "items": [
    {
      "id": "uuid",
      "original_filename": "a.pdf",
      "document_name": "informe-2024",   // null si falló antes de registrarse
      "sha256": "…",
      "outcome": "success",              // processing → success | failed; o skipped_duplicate
      "error_traceback": null,           // traceback completo cuando outcome = failed
      "document_id": "uuid | null",
      "created_at": "…",
      "finished_at": "… | null"          // null mientras el worker procesa
    }
  ],
  "total": n, "limit": n, "offset": n
}
```

---

## Ajustes

### `GET /settings/search-scope`

`{ "prompt": "texto del alcance" | null }` — `null`/vacío significa validación desactivada (se permite cualquier consulta).

### `PUT /settings/search-scope`

Body: `{ "prompt": "Solo se permiten consultas sobre…" }` (máx. 8000 caracteres; cadena vacía desactiva la validación). Respuesta: el mismo shape que el GET.

---

## Salud

### `GET /health` (sin auth)

`{ "status": "ok" }` — útil para readiness checks del frontend.

---

## Recetario rápido (flujos típicos)

**Subir y esperar a que esté listo**
1. `POST /documents` (multipart) → por cada item con `outcome: "processing"`, tomar `document.name`.
2. Polling `GET /documents/{name}` cada ~3 s hasta `status != "processing"`.
3. `status = "ready"` → listo para buscar; `"failed"` → consultar el motivo en `GET /uploads` (`error_traceback`).

**Buscar y descargar un resultado**
1. `POST /search` → renderizar `answer` + `chunks` (ordenados por similitud).
2. Para descargar un documento del resultado basta un enlace directo: `<a href="{base}{doc.download_url}">` (la descarga es pública, no requiere header).

**Manejo del 401**
Cualquier 401 ⇒ borrar la clave almacenada y volver a la pantalla de introducción de clave.
