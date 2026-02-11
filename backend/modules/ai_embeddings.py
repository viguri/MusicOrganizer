"""Semantic genre grouping using sentence-transformers embeddings."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from backend.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            _model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Embedding model loaded")
        except ImportError:
            logger.warning("sentence-transformers not installed, semantic grouping disabled")
            return None
    return _model


def compute_embeddings(texts: List[str]) -> Optional[np.ndarray]:
    """Compute embeddings for a list of genre strings."""
    model = _get_model()
    if model is None:
        return None
    return model.encode(texts, show_progress_bar=False, normalize_embeddings=True)


def group_genres_by_similarity(
    genre_counts: Dict[str, int],
    target_groups: int = 50,
    similarity_threshold: float = 0.65,
) -> Dict[str, List[str]]:
    """Group similar genres into clusters using embeddings.

    Args:
        genre_counts: Dict of genre_name → count
        target_groups: Target number of output groups
        similarity_threshold: Cosine similarity threshold for merging

    Returns:
        Dict of group_name → [list of genres in group]
    """
    genres = list(genre_counts.keys())
    if not genres:
        return {}

    embeddings = compute_embeddings(genres)

    # Fallback: no embeddings available, return each genre as its own group
    if embeddings is None:
        return {g: [g] for g in genres}

    # Compute cosine similarity matrix
    sim_matrix = np.dot(embeddings, embeddings.T)

    # Greedy agglomerative clustering
    assigned = [False] * len(genres)
    groups: Dict[str, List[str]] = {}

    # Sort genres by count (descending) — most popular become group leaders
    sorted_indices = sorted(range(len(genres)), key=lambda i: genre_counts[genres[i]], reverse=True)

    for idx in sorted_indices:
        if assigned[idx]:
            continue

        leader = genres[idx]
        group = [leader]
        assigned[idx] = True

        # Find similar unassigned genres
        for other_idx in range(len(genres)):
            if assigned[other_idx]:
                continue
            if sim_matrix[idx][other_idx] >= similarity_threshold:
                group.append(genres[other_idx])
                assigned[other_idx] = True

        groups[leader] = group

        # Stop if we've reached target group count and all remaining are low-count
        if len(groups) >= target_groups:
            # Assign remaining to closest group
            for rem_idx in range(len(genres)):
                if assigned[rem_idx]:
                    continue
                best_group = None
                best_sim = -1.0
                for group_leader_idx in sorted_indices:
                    if genres[group_leader_idx] in groups:
                        s = float(sim_matrix[rem_idx][group_leader_idx])
                        if s > best_sim:
                            best_sim = s
                            best_group = genres[group_leader_idx]
                if best_group:
                    groups[best_group].append(genres[rem_idx])
                else:
                    groups.setdefault("Other", []).append(genres[rem_idx])
                assigned[rem_idx] = True
            break

    # Assign any remaining unassigned
    for idx in range(len(genres)):
        if not assigned[idx]:
            groups.setdefault("Other", []).append(genres[idx])

    logger.info(f"Grouped {len(genres)} genres into {len(groups)} clusters")
    return groups
