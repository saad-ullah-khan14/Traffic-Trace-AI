# Traffic-Trace-Frontend

The officer's dashboard and the phone camera page for **Traffic_Trace** — a system
that tracks vehicles which have no readable number plate.

Backend lives in a separate repository: **Traffic-Trace-Backend**.

## Clone them side by side

The two repositories are separate, but the folders must sit like this on disk —
the backend writes offline map tiles into `../dashboard/public/tiles`:

```
Traffic_Trace/            <- Traffic-Trace-Backend
└── dashboard/            <- Traffic-Trace-Frontend (this repo)
```

```powershell
git clone https://github.com/UniDev143/Traffic-Trace-Backend.git Traffic_Trace
cd Traffic_Trace
git clone https://github.com/UniDev143/Traffic-Trace-Frontend.git dashboard
```

## Run

```powershell
npm install
npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

> Use the **production build** whenever a phone is involved. `npm run dev` ships
> ~4 MB of JavaScript versus 563 KB; over a phone hotspot it often never finishes
> hydrating, so the page renders but every button silently does nothing.
> `npm run dev` is fine for laptop-only work.

The API address is derived from the browser's own hostname (`window.location`),
so a phone loading this from the laptop's hotspot reaches the right backend with
no configuration. Override with `NEXT_PUBLIC_API_URL` if ever needed.

## Pages

| Route | What it is |
|---|---|
| `/` | Live event monitor |
| `/incidents` | Violation feed, updates over WebSocket |
| `/incidents/[id]` | Review screen — candidates, score bars, confirm/reject |
| `/incidents/[id]/report` | Court-style case file, print to PDF |
| `/journeys` | The confirmed route, animated across the map |
| `/map` | Live map on cached offline tiles |
| `/camera` | The phone page — claim by secret, GPS, capture loop |

## Requirements

Node 22 · a running backend on port 8000 · offline tiles in `public/tiles/`
(generate with the backend's `scripts/download_tiles.py` **while online**).

Full project history, decisions and architecture: `PROGRESS.md` in the backend repo.
