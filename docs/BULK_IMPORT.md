# Carga masiva de documentos (`scripts/bulk_import.py`)

Herramienta para ingestar una carpeta de PDFs de golpe y **reoptimizar el índice
vectorial al final**. Está pensada para ejecutarse **de forma repetida** (cada vez
que llega un lote nuevo): el índice HNSW se puede reconstruir tantas veces como
haga falta, no es una operación de una sola vez.

Qué hace cada ejecución:

1. Recorre `--source` buscando `*.pdf` e ingesta cada uno directamente (parsea,
   trocea, embebe e inserta), sin pasar por la API HTTP ni la cola arq.
2. **Deduplica por contenido (sha256)**: los ficheros ya indexados se saltan.
   Por eso re-ejecutar es idempotente y sirve de *resume* si algo se corta.
3. **Optimiza el índice** una vez al terminar (`--reindex`).

## Requisitos

- Ejecutarse en el servidor (o donde haya acceso a Postgres y al `data_dir`), con
  el entorno del proyecto (`.env` con `OPENAI_API_KEY`, `DATABASE_URL`, etc.).
- Los PDFs deben tener **capa de texto** (no escaneos-imagen); si no, ese fichero
  falla con "No extractable text".

## Uso básico

```bash
# 1. Copia los PDFs al servidor, p. ej. /data/import
# 2. Ejecuta la carga (sin downtime, reindex concurrente por defecto):
uv run python scripts/bulk_import.py --source /data/import
```

Con metadatos y más paralelismo:

```bash
uv run python scripts/bulk_import.py \
  --source /data/import \
  --metadata /data/import/metadata.csv \
  --concurrency 6 \
  --report /data/import/resultado.csv
```

## Metadatos (opcional)

Sin `--metadata`, el `name` de cada documento es el nombre del fichero sin
extensión y el resto de campos quedan vacíos. Con `--metadata` puedes aportar por
fichero: `name, author, publication_year, description, category, language`.

**CSV** (cabecera obligatoria; `filename` identifica el PDF):

```csv
filename,name,author,publication_year,category,language
informe-motor.pdf,Informe motor 2024,García,2024,informe,es
manual.pdf,Manual de taller,,2023,manual,es
```

**JSON** (objeto por nombre de fichero, o lista con clave `filename`):

```json
{ "informe-motor.pdf": { "name": "Informe motor 2024", "author": "García", "publication_year": 2024 } }
```

Si dos PDFs distintos resolverían el mismo `name`, se desambigua con sufijos
`-2`, `-3`… automáticamente.

## Optimización del índice (`--reindex`)

| Valor | Qué hace | Cuándo |
|---|---|---|
| `concurrent` (def.) | `REINDEX INDEX CONCURRENTLY` — sin bloquear búsquedas | Sistema en uso. Necesita ~2× el tamaño del índice en disco temporal. |
| `rebuild` | `DROP` + `CREATE INDEX` | Lote enorme y **ventana de mantenimiento** (búsquedas degradadas mientras dura). Menor tiempo total. |
| `none` | No toca el índice | Si prefieres reindexar aparte. |

Solo se reoptimiza si de verdad se ingestó algo nuevo. Ajusta la memoria de
construcción con `--maintenance-work-mem 4GB` (y en `rebuild`, opcionalmente
`--hnsw-m` / `--hnsw-ef-construction`).

## Recomendación por tamaño de lote

- **Lote pequeño/mediano, sistema en uso** → por defecto: `--reindex concurrent`.
- **Lote muy grande, puedes parar el servicio** → para API+worker, luego
  `--reindex rebuild --maintenance-work-mem 8GB`, y reabre tráfico al terminar.

## Resúmenes IA

Por defecto **no** se generan (para acelerar y abaratar la carga). Los documentos
quedan con `summary_generated=false` y puedes generarlos después bajo demanda con
`POST /documents/{name}/summary`. Usa `--summaries` para generarlos durante la carga.

## Si algún fichero falla

Se registran en el `--report` con su motivo y la carga continúa. Volver a
ejecutar el mismo comando **reintenta solo los que faltan** (el dedupe se salta
los ya cargados).
