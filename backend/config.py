"""Central configuration for the Music Organizer backend."""

from pathlib import Path
import os

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR  # JSON mappings, DB, rollback logs live here
PROJECT_ROOT = BASE_DIR.parent

DEFAULT_MASTER_COLLECTION = os.getenv(
    "MASTER_COLLECTION",
    r"G:\__DJ-ING\_______MASTER_COLLECTION",
)
DEFAULT_STYLES_DIR = os.getenv(
    "STYLES_DIR",
    r"G:\__DJ-ING\_______MASTER_COLLECTION\_STYLES",
)
DEFAULT_NEW_RELEASES_DIR = os.getenv(
    "NEW_RELEASES_DIR",
    r"G:\__DJ-ING\__NEW_RELEASES",
)

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_PATH = DATA_DIR / "music_organizer.db"

# ── Mapping files ──────────────────────────────────────────────────────────────
FOLDER_MAPPING_PATH = DATA_DIR / "folder_mapping.json"
LABEL_MAPPING_PATH = DATA_DIR / "label_mapping.json"

# ── Audio ──────────────────────────────────────────────────────────────────────
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".aiff", ".aif", ".ogg", ".wma"}

# ── Scanner ────────────────────────────────────────────────────────────────────
SCANNER_WORKERS = os.cpu_count() or 4
SCANNER_CHUNKSIZE = 64

# ── Organizer ──────────────────────────────────────────────────────────────────
MOVER_WORKERS = 16
TARGET_FOLDER_COUNT = 50
UNCLASSIFIED_FOLDER = "__REVISAR"

# ── Duplicates ─────────────────────────────────────────────────────────────────
HASH_CHUNK_SIZE = 65536  # 64 KB

# ── AI: Embeddings ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── AI: Ollama (optional, for name cleaning) ───────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")

# ── FastAPI ────────────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
