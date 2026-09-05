import psycopg2
import psycopg2.extras

conn = psycopg2.connect("postgresql://postgres:trafficdev@127.0.0.1:5432/traffic_trace")
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# The 4 timestamps Muhammad flagged (camera 05ed7642, "kept" but 0 violations),
# from api.log on 1 Sep. We look for sightings on that camera around those times.
target_camera = "05ed7642-ff08-461f-b28f-2db08148c611"

cur.execute("""
    SELECT id, camera_id, ts, vehicle_type, bbox, attrs, confidence,
           crop_path, crop_hash, violations
    FROM sightings
    WHERE camera_id = %s
    ORDER BY ts DESC
    LIMIT 50
""", (target_camera,))

rows = cur.fetchall()
print(f"Found {len(rows)} recent sightings on camera {target_camera}\n")

for r in rows:
    print(f"id={r['id']}")
    print(f"  ts={r['ts']}  vehicle={r['vehicle_type']}  violations={r['violations']}")
    print(f"  bbox={r['bbox']}  crop_path={r['crop_path']}")
    print(f"  attrs={r['attrs']}")
    print()

cur.close()
conn.close()
