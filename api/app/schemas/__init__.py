"""Pydantic models — the shape of what goes in and out over HTTP.

The Express equivalent of Joi/Zod schemas, except FastAPI also generates the
OpenAPI docs from them, so /docs stays correct for free.

Keep these separate from database rows: a response model is what the dashboard
is promised, not whatever columns happen to exist.
"""
