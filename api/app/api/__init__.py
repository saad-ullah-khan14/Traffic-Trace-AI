"""HTTP layer.

    router.py   mounts every route module under /api
    routes/     URL -> function. Thin: validate, call a service, return
    deps.py     shared dependencies (auth guards) — Express middleware

Routes must not contain business logic and must not write SQL.
"""
