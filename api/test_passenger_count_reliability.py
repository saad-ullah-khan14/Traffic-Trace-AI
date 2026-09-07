"""
Re-test passenger_count reliability after today's rider-bbox extension fix
in pipeline/detector.py. Muhammad measured this ~11% unreliable before that
fix (a 2-rider bike recorded as passenger_count=1). If the fix improved
rider detection generally, this number might be trustworthy now — worth
checking with real fresh data before re-enabling PASSENGER_FILTER_ENABLED.

Run from api/ with venv active:
    python test_passenger_count_reliability.py
"""
from app.db.session import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, crop_path, attrs->>'passenger_count' AS passenger_count, ts "
            "FROM sightings ORDER BY ts DESC"
        )
        rows = cur.fetchall()

print(f"{len(rows)} sightings:\n")
for r in rows:
    print(f"  passenger_count={r['passenger_count']}  crop={r['crop_path']}  ts={r['ts']}")

print("\nOpen each crop_path under evidence/ and count riders by eye.")
print("Compare against the passenger_count printed above for that row.")
