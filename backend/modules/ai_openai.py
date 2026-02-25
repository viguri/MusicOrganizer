"""Optional OpenAI-assisted genre folder proposal."""

from __future__ import annotations

import json
import logging
from typing import Dict, List
from urllib import error, request

from backend.config import OPENAI_API_KEY, OPENAI_MODEL, OTHER_FOLDER
from backend.modules.genre_parser import sanitize_folder_name

logger = logging.getLogger(__name__)


def is_openai_available() -> bool:
    return bool(OPENAI_API_KEY.strip())


def propose_folder_mapping_with_openai(genre_counts: Dict[str, int], target_folders: int = 50) -> Dict[str, List[str]]:
    """Ask OpenAI to generate a logical folder mapping.

    Returns a dict: folder_name -> [genres].
    Raises RuntimeError on API/response issues.
    """
    if not is_openai_available():
        raise RuntimeError("OPENAI_API_KEY is missing")

    genres_payload = [
        {"genre": genre, "count": count}
        for genre, count in sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    prompt = (
        "You are a music librarian specializing in DJ collections. "
        "Given a list of normalized genres with track counts, produce a logical folder structure. "
        "Return ONLY JSON object with this shape: {\"folder_mapping\": {\"Folder\": [\"GenreA\", \"GenreB\"]}}. "
        "Rules: "
        "1) Use at most the requested target_folders. "
        "2) You may use nested folders via '/' when helpful (e.g. 'Techno/Peak Time'). "
        "3) Every input genre must appear exactly once in output lists. "
        "4) Avoid tiny singleton folders unless musically meaningful. "
        "5) Put uncertain/noisy genres into 'Other'."
    )

    payload = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You output strict JSON only."},
            {
                "role": "user",
                "content": (
                    f"target_folders={target_folders}\n"
                    f"genres={json.dumps(genres_payload, ensure_ascii=False)}\n"
                    f"instructions={prompt}"
                ),
            },
        ],
        "temperature": 0.2,
    }

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI HTTP {e.code}: {body[:300]}") from e
    except Exception as e:
        raise RuntimeError(f"OpenAI request failed: {e}") from e

    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        raw_mapping = parsed.get("folder_mapping", {})
        if not isinstance(raw_mapping, dict):
            raise ValueError("folder_mapping missing or invalid")
    except Exception as e:
        raise RuntimeError(f"Invalid OpenAI response format: {e}") from e

    # Normalize + sanitize
    safe_mapping: Dict[str, List[str]] = {}
    seen_genres = set()
    for folder, genres in raw_mapping.items():
        safe_folder = sanitize_folder_name(str(folder), fallback=OTHER_FOLDER)
        if not isinstance(genres, list):
            continue
        bucket = safe_mapping.setdefault(safe_folder, [])
        for g in genres:
            genre = str(g).strip()
            if not genre or genre in seen_genres:
                continue
            seen_genres.add(genre)
            bucket.append(genre)

    # Ensure all genres are covered exactly once
    missing = [g for g in genre_counts.keys() if g not in seen_genres]
    if missing:
        safe_mapping.setdefault(OTHER_FOLDER, []).extend(missing)

    for folder, genres in list(safe_mapping.items()):
        safe_mapping[folder] = sorted(set(genres))

    logger.info("OpenAI proposed %d folders for %d genres", len(safe_mapping), len(genre_counts))
    return safe_mapping
