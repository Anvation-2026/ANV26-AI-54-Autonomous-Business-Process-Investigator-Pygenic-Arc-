"""Local retrieval-augmented memory for historical investigations.

The retriever is intentionally local and deterministic. Historical cases are
converted to searchable documents, represented with TF-IDF vectors, and ranked
with cosine similarity against the current investigation query.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _tokens(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", " ", value.lower()).strip()


def _document(case: dict[str, Any]) -> str:
    evidence = " ".join(str(item) for item in case.get("evidence", []))
    return " ".join([
        str(case.get("problem", "")),
        evidence,
        str(case.get("root_cause", "")),
        str(case.get("solution", "")),
        str(case.get("result", "")),
    ])


def retrieve_cases(path: str | Path, query: str, limit: int = 3) -> dict[str, Any]:
    """Retrieve cases and return both results and an auditable retrieval trace."""
    if not query or not query.strip():
        return {"matches": [], "retrieval": {"status": "empty_query", "documents": 0}}
    source = Path(path)
    if not source.exists():
        return {"matches": [], "retrieval": {"status": "memory_source_missing", "source": str(source), "documents": 0}}
    try:
        cases = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Historical memory could not be loaded: {error}") from error
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("Historical memory must contain an array of case objects")
    if not cases:
        return {"matches": [], "retrieval": {"status": "empty_memory", "source": str(source), "documents": 0}}

    documents = [_tokens(_document(case)) for case in cases]
    query_text = _tokens(query)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    matrix = vectorizer.fit_transform(documents)
    query_vector = vectorizer.transform([query_text])
    scores = cosine_similarity(query_vector, matrix)[0]
    ranked_indexes = sorted(range(len(cases)), key=lambda index: float(scores[index]), reverse=True)
    matches = []
    for rank, index in enumerate(ranked_indexes[:max(0, limit)], 1):
        score = round(float(scores[index]), 4)
        if score < 0.08:
            continue
        matches.append({
            **cases[index],
            "retrieval_score": score,
            "retrieval_rank": rank,
            "retrieval_source": str(source),
        })
    return {
        "matches": matches,
        "retrieval": {
            "status": "ok",
            "method": "tfidf_cosine_similarity",
            "source": str(source),
            "documents": len(cases),
            "returned": len(matches),
            "query_terms": sorted(set(query_text.split())),
        },
    }
