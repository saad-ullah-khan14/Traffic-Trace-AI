"""Data access layer — the ONLY place SQL is written.

    session.py   connection handling
    queries/     one module per table (cameras, sightings, incidents, ...)
    migrations/  schema.sql and any later migration files

Services call these functions; routes never call them directly.
"""
