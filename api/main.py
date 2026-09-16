"""
api/main.py

Phase 6: small API serving MedSense's topics and insights.

Reads from data/processed/public_data.json (built by
src/build_public_dataset.py) - a small, pre-vetted, privacy-safe file.
This API never touches the raw or full de-identified dataset directly,
by design.

The data contract (response shapes below) is dataset-agnostic: nothing
here assumes WebMD specifically. Pointing the pipeline at a different
dataset and rebuilding public_data.json would work with this same API
unchanged, per the project's ground rules.

Run locally:
    uvicorn api.main:app --reload

Deployment: see DEPLOYMENT.md
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MedSense API", version="1.0")

# Allow the frontend (deployed separately) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your actual frontend URL once deployed
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATA_PATH = Path(__file__).parent.parent / "data" / "processed" / "public_data.json"

_cache: dict | None = None


def load_data() -> dict:
    global _cache
    if _cache is None:
        if not DATA_PATH.exists():
            raise RuntimeError(
                f"{DATA_PATH} not found. Run 'python src/build_public_dataset.py' first."
            )
        with open(DATA_PATH) as f:
            _cache = json.load(f)
    return _cache


@app.get("/")
def root():
    return {"service": "MedSense API", "status": "ok"}


@app.get("/api/topics")
def list_topics(condition: str | None = None, min_reviews: int = 0, sort: str = "n_reviews"):
    """
    Overview endpoint: list all topics, optionally filtered by condition
    or minimum review count, sorted by n_reviews or avg_sentiment.
    """
    data = load_data()
    topics = data["topics"]

    if condition:
        topics = [t for t in topics if t["top_condition"] == condition]
    if min_reviews:
        topics = [t for t in topics if t["n_reviews"] >= min_reviews]

    if sort == "avg_sentiment":
        topics = sorted(topics, key=lambda t: t["avg_sentiment"])
    else:
        topics = sorted(topics, key=lambda t: t["n_reviews"], reverse=True)

    return {"count": len(topics), "topics": topics}


@app.get("/api/topics/{topic_id}")
def get_topic(topic_id: int):
    """Drill-down endpoint: full detail for a single topic."""
    data = load_data()
    for t in data["topics"]:
        if t["topic_id"] == topic_id:
            return t
    raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")


@app.get("/api/insights")
def list_insights():
    """The curated, privacy-checked Phase 5 insights."""
    data = load_data()
    return {"count": len(data["insights"]), "insights": list(data["insights"].values())}


@app.get("/api/insights/{name}")
def get_insight(name: str):
    data = load_data()
    if name not in data["insights"]:
        raise HTTPException(status_code=404, detail=f"Insight '{name}' not found")
    return data["insights"][name]


@app.get("/api/meta")
def get_meta():
    data = load_data()
    return data["meta"]
