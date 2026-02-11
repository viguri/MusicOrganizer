# Plan: Music Organizer — Automatizar organización de música + Rekordbox 7

Proyecto nuevo con **Web UI (React + FastAPI)** y **AI local (Ollama)** que automatiza: escanear música → auto-generar estructura de carpetas por los ~50 géneros más frecuentes → clasificar con AI cuando faltan tags → limpiar nombres → mover a carpetas de estilo → sincronizar directamente con Rekordbox 7 vía `pyrekordbox`.

---

## Decisiones confirmadas por el usuario

1. **`library.xml`** en `_STYLES/` es antiguo (RB 6.8.5) → **descartado**. No usaremos XML.
2. **Modo Export** con controladora XDJ-XZ → la integración debe ser compatible con Export mode.
3. **Regenerar estructura de carpetas**: escanear todos los archivos, extraer géneros, agrupar en los **~50 géneros más frecuentes** y crear carpetas nuevas basadas en datos reales.
4. **Limpiar nombres** de archivos (quitar `www.djsoundtop.com`, `electronicfresh.com`, prefijos numéricos, etc.).
5. **Proyecto nuevo** en `D:\____DEVELOPMENT\_GITHUB\___SMALL_APPS\music_organizer\`.
6. **`pyrekordbox`** para acceso directo a la DB de Rekordbox 7 (requiere `sqlcipher3`). Soporta: leer/escribir tracks, playlists, géneros, artistas, albums, labels.
7. **Web UI** con React + TailwindCSS + shadcn/ui (frontend) y FastAPI (backend Python).
8. **AI local (limitada)**: sentence-transformers para agrupación semántica de géneros + Ollama solo para limpieza de nombres. **No** para clasificación de género (poco fiable en electrónica de nicho).

---

## Cambio clave: pyrekordbox en vez de XML

`pyrekordbox` (v0.3+, testado en RB 7.0.9) accede directamente a la DB cifrada `master.db` de Rekordbox 7 vía SQLCipher. Esto permite:

| Capacidad | XML (antiguo plan) | pyrekordbox (nuevo plan) |
|-----------|-------------------|--------------------------|
| Leer colección RB | ✅ (export manual) | ✅ (directo) |
| Escribir tracks en RB | ❌ (solo import) | ✅ (directo) |
| Crear playlists en RB | ❌ | ✅ (directo) |
| Modificar géneros en RB | ❌ | ✅ (directo) |
| Detectar duplicados en RB | ❌ | ✅ (query DB) |
| Sincronización bidireccional | ❌ | ✅ |
| Requiere acción manual en RB | Sí (import) | **No** |

**Requisito**: instalar `sqlcipher3` (el usuario ya lo tiene resuelto).

Scripts existentes del usuario que ya usan pyrekordbox:
- `rekordbox_db_access.py` — lectura básica de contenido y playlists
- `generate_playlist.py` — generación de playlists M3U desde RB con Camelot wheel
- `remove_duplicates.py` — eliminación de duplicados en la DB de RB

---

## Flujo automatizado propuesto

```
1. Descargas packs → __NEW_RELEASES\*.zip                         [MANUAL]
2. Descomprimes en temp*                                           [MANUAL]
3. TOOL: clean-names temp* → limpia nombres de archivos            [AUTO]
4. TOOL: scan temp* → lee géneros ID3 → detecta duplicados         [AUTO]
5. TOOL: classify → asigna carpeta estilo → muestra resumen        [AUTO]
6. Revisas resumen, ajustas si quieres                             [MANUAL - rápido]
7. TOOL: move → mueve archivos a _STYLES\_{ESTILO}                [AUTO]
8. TOOL: sync-rb → añade tracks a RB + crea playlists por estilo  [AUTO - pyrekordbox]
```

**De 6 pasos manuales a 2** (descargar + revisar resumen). Ya no hace falta importar nada en Rekordbox manualmente.

---

## Migración completa (Opción A): reubicar TODA la colección

La herramienta reubicará **todos los archivos existentes** en `_STYLES/` además de los nuevos en `__NEW_RELEASES/`. Dado el volumen (~15K+ tracks, muchos GB), el rendimiento es crítico.

### Paso 1: Generar estructura de carpetas (~50 géneros)

1. **Escanea toda la colección** (`_STYLES/` + `__NEW_RELEASES/`) → extrae todos los géneros ID3
2. **Cuenta frecuencia** de cada género
3. **Agrupa** géneros similares (fuzzy matching + reglas manuales) → top ~50 grupos
4. **Genera `folder_mapping.json`** con las carpetas propuestas y los géneros que van en cada una
5. **Tú revisas y ajustas** el JSON una vez
6. **Crea las carpetas nuevas** en `_STYLES/`

### Paso 2: Reubicar archivos existentes

7. **Escanea archivos existentes** en las carpetas actuales de `_STYLES/`
8. **Clasifica cada archivo** según el nuevo `folder_mapping.json`
9. **Dry-run**: muestra resumen completo (X archivos se mueven, Y ya están bien, Z sin clasificar)
10. **Execute**: mueve archivos a la nueva estructura
11. **Limpia carpetas vacías** tras la migración

Los géneros raros van a `__REVISAR/`.

---

## Estrategia de rendimiento (15K+ archivos, muchos GB)

### Escaneo ID3 → `multiprocessing.Pool` (CPU-bound)

Leer tags ID3 de miles de archivos es CPU-bound (decodificar headers). Usaremos `multiprocessing.Pool` con `os.cpu_count()` workers para paralelizar el escaneo. Cada worker recibe un lote de rutas y devuelve una lista de metadatos. Esto escala linealmente con los cores disponibles.

```python
# Pseudocódigo
with multiprocessing.Pool(os.cpu_count()) as pool:
    results = pool.map(scan_file_metadata, file_paths, chunksize=64)
```

### Mover/copiar archivos → `concurrent.futures.ThreadPoolExecutor` (I/O-bound)

Mover archivos en el mismo disco (G:) es I/O-bound. Usaremos `ThreadPoolExecutor` con ~8-16 threads. Si el origen y destino están en el mismo volumen, `os.rename()` es instantáneo (solo cambia el puntero del filesystem, no copia datos).

```python
# os.rename() en mismo volumen = O(1), no copia bytes
with ThreadPoolExecutor(max_workers=16) as executor:
    futures = [executor.submit(os.rename, src, dst) for src, dst in moves]
```

### Hash SHA-256 (duplicados) → `multiprocessing.Pool` (CPU+I/O)

Calcular hashes es intensivo. Usaremos multiprocessing + lectura en chunks de 64KB. Para la primera pasada, comparamos solo por **tamaño de archivo** (instantáneo) y solo calculamos hash de los archivos con tamaño idéntico.

### Pipeline general

```
1. Descubrir archivos (os.walk)           → single thread, rápido
2. Escanear ID3 tags                      → multiprocessing.Pool (CPU)
3. Calcular hashes (solo si hay dupes)    → multiprocessing.Pool (CPU+I/O)
4. Clasificar por género                  → single thread (lookup en dict)
5. Mover archivos                         → ThreadPoolExecutor (I/O) o os.rename
6. Actualizar DB SQLite                   → single thread (batch INSERT)
```

### Progreso

`tqdm` con barra de progreso para cada fase. Estimación de tiempo restante.

### Resiliencia

- **Checkpoint**: si el proceso se interrumpe, la DB SQLite registra qué archivos ya se procesaron. Al reiniciar, continúa desde donde quedó.
- **Rollback log**: antes de mover, se escribe un log JSON con `{src: dst}` para cada archivo. Si algo falla, se puede revertir.
- **Validación post-move**: verificar que el archivo existe en destino y tiene el mismo tamaño antes de eliminar el origen.

---

## UI: React + FastAPI

### ¿Por qué Web UI?

- **Dashboards** con estadísticas de la colección (géneros, BPM, keys)
- **Tablas interactivas** para revisar clasificación antes de mover (sort, filter, editar género)
- **Progreso en tiempo real** vía WebSockets (barras de progreso de escaneo/movimiento)
- **Preparada para AI** (chat, sugerencias inline, clasificación asistida)
- Se abre en el navegador, no necesita instalar nada extra

### Stack

| Capa | Tecnología |
|------|------------|
| Frontend | React 18 + TypeScript + TailwindCSS + shadcn/ui + Lucide icons |
| Backend | FastAPI (Python) + WebSockets (progreso) + BackgroundTasks |
| State | React Query (server state) + Zustand (client state) |
| Build | Vite (frontend) + uvicorn (backend) |

### Pantallas principales

1. **Dashboard** — estadísticas de la colección, géneros más frecuentes, tracks sin género
2. **Scan & Classify** — escanear carpeta, ver tabla de tracks con género asignado, editar, confirmar
3. **Organize** — dry-run visual, confirmar movimiento, progreso en tiempo real
4. **Rekordbox Sync** — estado de sincronización, playlists, duplicados en RB
5. **Settings** — rutas, configuración de Ollama, folder_mapping.json editor

---

## AI y clasificación inteligente

### Por qué NO usar Ollama para clasificar géneros de electrónica

Un LLM genérico (Llama 3, Mistral) **no analiza audio** y **no conoce** el nicho de electrónica:
- No sabe que "Reinier Zonneveld" = Hard Techno o "Kerri Chandler" = Deep House
- Los títulos de tracks electrónicos son abstractos ("Nebula", "Signal Path") — no dan pistas
- Las labels sí son indicativas (Drumcode = Techno) pero un LLM genérico puede no conocerlas

### Estrategia de clasificación para tracks sin género ID3

| Prioridad | Método | Descripción |
|-----------|--------|-------------|
| 1 | **Género ID3** | Si el tag existe, usarlo directamente |
| 2 | **Carpeta de origen** | Si el track ya estaba en `_HOUSE/`, asignar "House" |
| 3 | **Label → género** | Mapeo `label_mapping.json` (Drumcode→Techno, Defected→House, etc.) que se enriquece con el tiempo |
| 4 | **`__REVISAR/`** | Clasificación manual rápida en la UI (tabla interactiva con filtros) |

### Dónde SÍ aporta AI

| Funcionalidad | Tecnología | Descripción |
|---|---|---|
| **Agrupación semántica de géneros** | sentence-transformers (local, 80MB) | Agrupar "Melodic House & Techno" con "Melodic Techno" usando embeddings. Funciona bien porque opera sobre texto de géneros, no audio |
| **Limpieza de nombres de archivos** | Ollama (opcional) | Extraer artista/título de `"01.www.djsoundtop.com_Artist - Track (Mix).mp3"`. Fallback: regex si Ollama no está disponible |

### Arquitectura AI

```
FastAPI → ai_embeddings.py → sentence-transformers (in-process, sin servidor)
       → ai_name_cleaner.py → Ollama (localhost:11434) [opcional, fallback a regex]
```

- **sentence-transformers** (`all-MiniLM-L6-v2`, 80MB) corre in-process. Sin GPU necesaria.
- **Ollama** es **opcional**. Si no está instalado, `name_cleaner.py` usa regex (cubre el 90% de los casos).
- **`label_mapping.json`**: mapeo label→género que se genera automáticamente a partir de la colección existente y se refina manualmente.

---

## Arquitectura

```
D:\____DEVELOPMENT\_GITHUB\___SMALL_APPS\music_organizer\
├── backend/
│   ├── main.py                 # FastAPI app + CLI (click/typer)
│   ├── config.py               # Rutas, constantes, configuración
│   ├── api/
│   │   ├── routes_scan.py      # Endpoints: scan, analyze-genres
│   │   ├── routes_organize.py  # Endpoints: classify, move, dry-run
│   │   ├── routes_rekordbox.py # Endpoints: sync-rb, playlists
│   │   ├── routes_settings.py  # Endpoints: config, folder_mapping
│   │   └── websocket.py        # WebSocket: progreso en tiempo real
│   ├── modules/
│   │   ├── scanner.py          # Lectura ID3 unificada (mutagen)
│   │   ├── genre_parser.py     # Parsing géneros compuestos + normalización
│   │   ├── genre_analyzer.py   # Escaneo masivo → frecuencias → ~50 carpetas
│   │   ├── genre_mapper.py     # Mapeo género → carpeta estilo
│   │   ├── name_cleaner.py     # Limpieza nombres de archivos
│   │   ├── organizer.py        # Mover archivos (dry-run + execute)
│   │   ├── database.py         # SQLite: inventario local
│   │   ├── duplicates.py       # Detección duplicados (hash + título)
│   │   ├── rekordbox_sync.py   # pyrekordbox: DB de RB7
│   │   ├── ai_embeddings.py   # sentence-transformers: agrupación semántica
│   │   ├── ai_agent.py        # Agente conversacional (Ollama + cloud fallback)
│   │   └── playlist.py         # Generar M3U
│   ├── folder_mapping.json     # Mapeo carpeta → géneros (generado + refinado)
│   ├── label_mapping.json      # Mapeo label → género (generado + refinado)
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── ScanClassify.tsx
│   │   │   ├── Organize.tsx
│   │   │   ├── RekordboxSync.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/         # Tablas, barras de progreso, cards
│   │   └── hooks/              # useWebSocket, useApi
│   └── tailwind.config.js
└── README.md
```

---

## Fases de implementación

### Fase 1: Backend Core + AI + UI básica

1. **`scanner.py`**: lectura ID3 unificada con `mutagen` (MP3/FLAC/WAV/M4A/AIFF) — `multiprocessing.Pool`
2. **`genre_parser.py`**: parsing de géneros compuestos (separadores `;,/&`, CamelCase, normalización)
3. **`genre_analyzer.py`**: escaneo masivo → frecuencia → propuesta ~50 carpetas → `folder_mapping.json`
4. **`ai_embeddings.py`**: agrupación semántica de géneros con sentence-transformers (mejora paso 3)
5. **`genre_mapper.py`**: mapeo género → carpeta destino (folder_mapping.json + fuzzy fallback + carpeta origen + label)
6. **`name_cleaner.py`**: limpieza de nombres (regex + Ollama opcional para casos difíciles)
   - Quitar: `www.djsoundtop.com`, `electronicfresh.com`, etc.
   - Quitar prefijos numéricos: `01.`, `02.`, `60.`, etc.
   - Normalizar espacios, guiones, caracteres especiales
   - Actualizar tag ID3 Title si coincide con el nombre limpio
8. **`organizer.py`**: scan → resumen → dry-run → execute — `ThreadPoolExecutor` + `os.rename`
9. **`database.py`**: SQLite local (path, hash, género raw, género normalizado, carpeta, fecha, estado)
10. **`duplicates.py`**: detección antes de mover (tamaño → hash + título+artista)
11. **FastAPI backend** + WebSocket para progreso
12. **React frontend**: Dashboard + Scan & Classify + Organize (UI básica funcional)

### Fase 2: Integración Rekordbox 7 (pyrekordbox)

13. **`rekordbox_sync.py`**:
    - Leer DB de RB7: colección, playlists, géneros
    - Añadir tracks nuevos a RB
    - Crear/actualizar playlists por estilo
    - Sincronizar géneros (RB ↔ archivos locales)
    - Detectar duplicados en RB
    - Backup automático de DB antes de escritura
14. **`playlist.py`**: generar M3U como backup/export
15. **UI: RekordboxSync page**

### Fase 3: Herramientas auxiliares + Agente conversacional + UI completa

16. Detección de duplicados cross-folder (hash + waveform opcional con `librosa`)
17. Comparación de carpetas
18. Renombrado de tags (capitalización, limpieza Spotify, etc.)
19. **UI: Settings page** (editor de folder_mapping.json, config de Ollama, rutas)
20. **UI: Dashboard** con estadísticas completas
21. **Agente conversacional híbrido** (Ollama local + cloud fallback):
    - Chat integrado en la UI para ejecutar acciones con lenguaje natural
    - Queries sobre la colección: "Cuántos tracks sin género tengo?", "Mueve los tracks de Drumcode a _TECHNO"
    - Creación de playlists: "Crea playlist de Afro House > 122 BPM en key 5A"
    - Function calling / tool use sobre la DB SQLite y los módulos existentes
    - **Ollama local** por defecto (gratis, privado), **cloud** (GPT-4o-mini / Claude) como fallback

### Fase 4: Automatización

22. **Watch mode**: monitorear `__NEW_RELEASES` y auto-procesar
23. Reportes exportables (HTML/PDF)
24. CLI alternativa (para uso sin UI)

---

## Prioridad

| # | Qué | Impacto | Fase |
|---|-----|---------|------|
| 1 | `scanner.py` + `genre_parser.py` (lectura + parsing, multiprocessing) | **Crítico** | 1 |
| 2 | `genre_analyzer.py` + `ai_embeddings.py` (top 50 géneros con embeddings) | **Crítico** | 1 |
| 3 | `name_cleaner.py` (limpieza nombres, regex + Ollama opcional) | **Alto** | 1 |
| 4 | `genre_mapper.py` (clasificación: ID3 → carpeta origen → label → __REVISAR) | **Crítico** | 1 |
| 5 | `organizer.py` con dry-run (ThreadPoolExecutor) | **Crítico** | 1 |
| 7 | `duplicates.py` + `database.py` | Alto | 1 |
| 8 | FastAPI backend + WebSocket | **Alto** | 1 |
| 9 | React frontend (Scan & Classify + Organize) | **Alto** | 1 |
| 10 | `rekordbox_sync.py` (pyrekordbox → RB7) | **Alto** | 2 |
| 11 | UI completa (Dashboard, Settings, RB Sync) | Medio | 3 |
| 12 | Agente conversacional híbrido (Ollama + cloud fallback) | Medio | 3 |

---

## Decisiones de diseño

- **Proyecto nuevo** en `D:\____DEVELOPMENT\_GITHUB\___SMALL_APPS\music_organizer\`
- **Web UI** (React + FastAPI) — se abre en navegador, no necesita instalar nada extra
- **AI limitada y realista** — sentence-transformers para agrupación semántica, Ollama solo para limpieza de nombres (opcional). No AI para clasificación de género (poco fiable en electrónica)
- **Clasificación en cascada** — género ID3 → carpeta origen → label → `__REVISAR/`
- **Migración completa** (Opción A) — reubicar todos los archivos existentes a la nueva estructura
- **Mover** archivos (no copiar) — `os.rename()` en mismo volumen = instantáneo
- **Regenerar carpetas** basándose en los ~50 géneros más frecuentes + agrupación semántica con embeddings
- **`folder_mapping.json`** como fuente de verdad — generado con embeddings, refinado manualmente una vez
- **`label_mapping.json`** — mapeo label→género generado de la colección, refinado manualmente
- **Siempre dry-run primero** — nunca mover/modificar sin confirmación visual en la UI
- **pyrekordbox + SQLCipher** para integración directa con RB7 (no XML)
- **Backup automático** de la DB de Rekordbox antes de cualquier escritura
- **`__REVISAR/`** como destino para tracks sin clasificar
- **Compatible con Export mode** (XDJ-XZ)
- **Paralelismo**: multiprocessing (escaneo ID3, hashes) + ThreadPoolExecutor (mover archivos) + WebSocket (progreso UI)

## Dependencias principales

### Backend (Python)
```
fastapi          # Backend web + WebSockets
uvicorn          # Servidor ASGI
mutagen          # Lectura/escritura ID3 tags
pyrekordbox      # Acceso directo a DB de Rekordbox 7
sqlcipher3       # Descifrado de master.db
tqdm             # Barras de progreso (CLI fallback)
thefuzz          # Fuzzy matching de géneros
sentence-transformers  # Embeddings locales para agrupación semántica
ollama           # Cliente Python para Ollama (limpieza de nombres + agente chat)
openai           # Cliente para cloud fallback (GPT-4o-mini) — OPCIONAL
python-multipart # Upload de archivos en FastAPI
```

### Frontend (Node/React)
```
react + react-dom
typescript
tailwindcss
@shadcn/ui
lucide-react
@tanstack/react-query
zustand
```

### Requisitos del sistema
```
Ollama instalado (ollama.com) con modelo llama3:8b o mistral
Python 3.10+
Node.js 18+
```
