# Music Organizer

Web-based tool to automate music collection organization with AI-assisted genre classification, file renaming, duplicate detection, and future Rekordbox 7 integration.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + TailwindCSS v4 + shadcn/ui + Lucide |
| Backend | FastAPI + WebSockets + BackgroundTasks |
| State | React Query (server) + Zustand (client) |
| AI | sentence-transformers (genre grouping) + Ollama (name cleaning, optional) |
| Build | Vite (frontend) + uvicorn (backend) |

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
cd ..
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Features

- **Dashboard** — Collection stats, genre distribution
- **Scan & Classify** — Scan directories, analyze genres, propose ~50 folder structure
- **Organize** — Dry-run planning, execute moves, rollback support
- **Name Cleaner** — Remove URL spam, numeric prefixes from filenames
- **Duplicates** — SHA-256 hash + metadata duplicate detection
- **Settings** — Configure paths, edit folder/label mappings

## Hierarchization Modes (Analyze Genres)

In **Scan & Classify → Analyze Genres**, you can choose:

- **Backend**: local embeddings + heuristics (default)
- **OpenAI**: cloud logical reorganization
- **Ollama**: local model logical reorganization

Set these environment variables before starting backend (only needed for corresponding mode):

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
```

Notes:
- OpenAI mode is optional and may add latency/cost.
- Ollama mode is optional and requires a local Ollama server/model.
- If selected mode is unavailable/fails, backend falls back automatically to local embeddings/heuristics.

## Architecture

```
music_organizer/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration
│   ├── api/
│   │   ├── websocket.py     # Real-time progress
│   │   ├── routes_scan.py   # Scan & genre analysis
│   │   ├── routes_organize.py # Organize, clean, duplicates
│   │   └── routes_settings.py # Config & mappings
│   └── modules/
│       ├── scanner.py       # Multiprocessing ID3 reader
│       ├── genre_parser.py  # Genre string normalization
│       ├── genre_analyzer.py # Frequency analysis → folder proposal
│       ├── genre_mapper.py  # Classification cascade
│       ├── ai_embeddings.py # Semantic genre grouping
│       ├── organizer.py     # File moves with rollback
│       ├── name_cleaner.py  # Filename cleaning (regex)
│       ├── duplicates.py    # Hash + metadata dedup
│       └── database.py      # SQLite inventory
├── frontend/
│   └── src/
│       ├── pages/           # Dashboard, ScanClassify, Organize, etc.
│       ├── components/      # UI components + shadcn/ui
│       ├── hooks/           # useWebSocket
│       ├── stores/          # Zustand task store
│       └── lib/             # API client, utils
└── docs/
    └── PLAN.md              # Full project plan
```

## License

MIT
