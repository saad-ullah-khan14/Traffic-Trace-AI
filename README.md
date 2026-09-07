# Traffic_Trace — No-Plate Vehicle Tracking System

Traffic_Trace is an AI-powered traffic-violation tracking system built for vehicles whose number plates cannot be read — the exact case where traditional e-challan systems fail.

## How It Works

1. **Detection** — Phone cameras (standing in for fixed traffic cameras) detect every vehicle with YOLOv8, and attach any riders to their motorcycle.

2. **Helmet Violation** — A fine-tuned YOLO model checks whether a motorcycle rider is wearing a helmet.

3. **Visual Fingerprinting** — Every vehicle gets a CLIP-based visual "fingerprint" (colour, shape, rider details) whether or not its plate is readable.

4. **Smart Matching** — When a plate is unreadable, the system matches that vehicle's past and future sightings across other cameras by visual similarity, gated by physically plausible travel time.

5. **Officer Review** — The system never auto-confirms a match. Every candidate is shown to a human officer, who decides "Same vehicle" or "Not the same."

6. **Journey Mapping** — Confirmed matches build a visual route showing everywhere the vehicle was seen.

7. **Find Me (Search)** — An officer can upload any photo and search the entire camera network for that vehicle or person.

## Tech Stack

- Backend: Python, FastAPI
- AI: YOLOv8 (detection), CLIP (visual embeddings)
- Database: PostgreSQL
- Frontend: Next.js / React, real-time WebSocket updates

## Privacy-First Design

Sightings not linked to any incident are automatically deleted after 48 hours.

## Real-World Tested

The system has been tested with real phone cameras on live street footage, across three separate camera positions, with genuine helmet-violation detection and verified cross-camera matching.
