"""Business logic — the layer that actually decides things.

Planned modules:
    ingest.py     frame -> pipeline.process_frame -> sightings + incidents (Phase 5)
    evidence.py   save crops to disk, compute SHA-256                      (Phase 5)
    matching.py   space-time gate -> numpy cosine -> score_candidates      (Phase 11)
    journeys.py   confirmed matches -> build_journey                       (Phase 13)
    watchlist.py  check_watchlist on each new sighting                     (Phase 14)

Services own the workflow. They call app.db.queries for data and pipeline.*
for AI, and know nothing about HTTP requests or responses.
"""
