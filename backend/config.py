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
OTHER_FOLDER = "Other"
UNCLASSIFIED_FOLDER = "__REVISAR"

# ── Duplicates ─────────────────────────────────────────────────────────────────
HASH_CHUNK_SIZE = 65536  # 64 KB
DUPLICATES_QUICK_HASH_BYTES = int(os.getenv("DUPLICATES_QUICK_HASH_BYTES", str(2 * 1024 * 1024)))
DUPLICATES_HASH_WORKERS = int(os.getenv("DUPLICATES_HASH_WORKERS", "0"))  # 0 = auto
DUPLICATES_METADATA_WORKERS = int(os.getenv("DUPLICATES_METADATA_WORKERS", "0"))  # 0 = auto
DUPLICATES_MAX_WORKERS_CAP = int(os.getenv("DUPLICATES_MAX_WORKERS_CAP", "32"))
DUPLICATES_STORAGE_MODE = os.getenv("DUPLICATES_STORAGE_MODE", "auto").strip().lower()  # auto|ssd|hdd|network
DUPLICATES_METADATA_SIZE_TOLERANCE = float(os.getenv("DUPLICATES_METADATA_SIZE_TOLERANCE", "0.03"))

# ── AI: Embeddings ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── AI: OpenAI (optional, for intelligent folder proposal) ────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── AI: Ollama (optional, for name cleaning) ───────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")

# ── FastAPI ────────────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
