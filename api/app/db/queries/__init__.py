"""One module per table. Every SQL statement in the project lives in here.

Each function takes an open connection as its first argument, so callers control
transaction boundaries — a service can insert a sighting and open an incident in
one atomic unit.
"""
