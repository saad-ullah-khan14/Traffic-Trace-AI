# Traffic_Trace — Pitch Deck

> **What this file is.** The *content* of an 8-slide deck, ready to paste into slides.
> One `##` heading = one slide. Under each slide: what goes **on** the slide (keep it
> short — judges read a slide in three seconds) and what the speaker **says** (that is
> where the detail lives).
>
> **Numbers.** Every figure on slide 5 is copied from `docs/STATS.md`, which records what
> was actually measured on this laptop and when. **Never type a number into a slide that is
> not in that file.** If a re-run disagrees with what is written here, `STATS.md` wins and
> this slide gets updated — a blank row is survivable, a number a judge can disprove is not.
>
> **Running order:** slides 1–3 before the demo (~1.5 min), slide 3 hands off to
> `docs/DEMO_SCRIPT.md` (7 min), slides 4–8 after it (~2.5 min). Slide 4 explains the
> mechanism *after* the audience has seen it work; the demo script deliberately says the
> short version of the same thing at segment 6, so if you are running late, cut slide 4's
> gate walkthrough rather than repeating it word for word.

---

## Slide 1 — Enforcement stops at the number plate

**On the slide**

> Every automated traffic system in Pakistan asks the same first question:
> **"what is the plate?"**
>
> If it cannot read one, the case ends there.

Four photographs in a row, captioned:

| Photo | Caption |
|---|---|
| A motorcycle with no plate at all | **Missing** |
| A plate bent flat, or wrapped in cloth | **Obscured** |
| A decorative / calligraphy / wrong-format plate | **Not machine-readable** |
| A plate washed out by headlight glare at night | **Unreadable** |

Then one line, bold, under the photos:

> The camera saw the violation perfectly. It just cannot say **who**.

**What the speaker says**

"E-challan works like this. A camera catches a violation, an OCR system reads the number
plate, that plate is looked up in the vehicle registry, and a challan goes to the address
on file. Every step after the first one depends entirely on the first one.

Now take the most common and most dangerous violation on our roads — a motorcycle rider
with no helmet. Look at the bikes on your own street. A lot of them have no plate at all,
or a bent plate, or one covered in mud or cloth, or a decorative plate no OCR was ever
trained on, or a plate that simply vanishes in headlight glare at night.

And a rider who has already decided to break one rule has an obvious, ten-second,
zero-cost way to break the rest of them: take the plate off.

So the violation gets recorded and it is unenforceable. The system watched it happen and
issued nothing. That is not an OCR accuracy problem you fix with a sharper camera. It is a
design problem — the entire chain hangs on the one part of a vehicle that comes off with a
screwdriver."

> **Team note:** if you can find one *citable* local figure — share of unplated
> motorcycles, helmet-violation counts, road deaths — put it on the slide **with the
> source visible**. If you cannot cite it, use the qualitative version above. Do not
> invent a statistic in front of judges; it is the one thing they will check.

---

## Slide 2 — The idea in one picture

**On the slide**

One line, large, across the top. This is the sentence they should still have when they
walk out:

> ### When the plate cannot be read, the vehicle itself becomes the plate.

Below it, the architecture diagram:

```
   ┌───────────┐   ┌───────────┐   ┌───────────┐
   │ Camera 1  │   │ Camera 2  │   │ Camera 3  │   phones — or CCTV — at fixed GPS points
   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
         │               │               │
         └───────────────┼───────────────┘
                         │   JPEG frames · POST /api/frames
                         ▼
             ┌────────────────────────┐
             │  DETECT + FINGERPRINT  │   YOLOv8n · helmet model · CLIP ViT-B/32
             │    (every vehicle)     │   → 512-number embedding + colour histogram
             └───────────┬────────────┘
                         │
        ┌════════════════╧═══════════════┐          ← thick arrow, thin arrow
        ▼ (always)                       ▼ (rarely)
┌──────────────────┐            ┌────────────────────┐
│    SIGHTING      │            │  Violation, and    │
│  stored ALWAYS   │            │  plate unreadable? │
│  every vehicle   │            └─────────┬──────────┘
└────────┬─────────┘                      │ yes
         │                                ▼
         │                        ┌───────────────┐
         │                        │   INCIDENT    │
         │                        └───────┬───────┘
         │   ┌────────────────────────────┘
         │   ▼
         │  ┌───────────────────────────────────────────┐
         └─►│  MATCH:  space-time gate → visual ranking  │
            │          → 4-signal score fusion           │
            └──────────────────┬────────────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  OFFICER CONFIRMS   │  ← a human. every time.
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │  JOURNEY on a map   │
                    └─────────────────────┘

   ↺  WATCHLIST — every new sighting anywhere is checked against every open incident
```

**Drawing notes for whoever builds this slide**

- **The two arrows out of "detect + fingerprint" are the entire product.** Make the
  "stored ALWAYS" arrow thick and the "incident" arrow thin. Every vehicle is
  fingerprinted; only a violation opens a case. If a judge takes one thing off this
  diagram, it should be that asymmetry.
- Draw the **watchlist loop** in a second colour, curving from the sighting box back into
  MATCH. That loop is what makes a vehicle that fled findable later.
- Put a small **human icon** on the "officer confirms" box. Judges look for it.
- Do not draw a cloud, a message broker, or a microservice mesh. It is one laptop and
  three phones, and saying so is stronger than pretending otherwise.

**What the speaker says**

"Here is the whole system in one picture, and it rests on a single decision.

Every vehicle that passes every camera gets recorded — not just the offenders. We take a
visual fingerprint of it and store it, unconditionally. That costs almost nothing, and it
is what makes everything to the right of this diagram possible.

Only a violation opens a case. And when a case opens, the question we ask is not 'what is
the plate' — it is 'where else has this exact vehicle been seen?'"

---

## Slide 3 — Live demo

**On the slide**

Nothing else. Full screen:

> # LIVE DEMO
>
> Three cameras. One rider, no helmet. No plate.
>
> *Running entirely offline — there is no internet in this room.*

**What the speaker says**

"We are going to run it. Live, right now, on those three phones. Everything you are about
to see happens on this one laptop, and there is no internet connection involved."

> → Switch to `docs/DEMO_SCRIPT.md`. Return here at slide 4 when the demo ends.

---

## Slide 4 — How it actually works

**On the slide**

Four numbered blocks, one line each:

| | | |
|---|---|---|
| **1** | **Fingerprint** | Every vehicle → 512 numbers describing how it *looks*, plus a colour histogram |
| **2** | **Space-time gate** | Physics first: 60 km/h ceiling, 30 s grace. Could not have got there → not a candidate |
| **3** | **Score fusion** | Four signals, weighted — space-time **0.35** · colour **0.30** · appearance **0.20** · rider **0.15** |
| **4** | **Human confirms** | The software proposes. An officer decides. Nothing is auto-confirmed |

**What the speaker says**

"Four things, and none of them are magic.

**One — the fingerprint.** When a vehicle passes a camera we crop it out and turn it into
512 numbers that describe how it looks, plus a colour histogram. Think of it as a very
detailed description: dark-red 125cc bike, blue box on the back, rider in a grey shirt. It
is not a plate and it is not an identity — two similar bikes produce similar numbers, and
I will come back to that honestly in a minute.

**Two — the space-time gate, and this is the part we are proudest of.** Before we compare a
single pixel, we ask a physics question. The violation happened at Camera 1 at 4:02.
Camera 3 is 1.6 kilometres away. At our assumed maximum of 60 km/h, that is at least 67
seconds of travel. So anything at Camera 3 inside 67 seconds of 4:02 is *physically
impossible* and is thrown out before the AI ever looks at it. That single rule removes the
overwhelming majority of the database instantly — and it removes precisely the coincidences
that fool a vision model hardest, because an identical-looking bike on the other side of
the city is exactly the false positive that would otherwise sail through.

We are deliberately generous with it. We measure straight-line distance, and real roads are
longer than straight lines, so real journeys take at least as long as we assume. The gate
is allowed to let an innocent candidate through. It is never allowed to throw away the true
one.

**Three — score fusion.** The survivors get scored on four signals at once, and the weights
are arranged so no single signal can carry a match on its own. Physics is heaviest at 0.35.
Colour next at 0.30. Then the two deep-learning embeddings, vehicle at 0.20 and rider at
0.15 — **so both neural networks together carry exactly what physics carries alone.** I will
tell you on the limits slide why we did that. If a signal is missing — say there is
no rider to compare on one side — its weight is redistributed across the others rather than
scored as zero, so an absent signal never drags down a genuine match.

**Four — a human confirms.** The officer gets a ranked list with every score broken down
bar by bar, so he can see *why* something scored well, not just that it did. He confirms or
rejects. There is no automatic challan at the end of this pipeline, and that is a design
decision, not a missing feature."

> **⚠️ The distance and the seconds must match the cameras you actually deploy.** With the
> seeded positions the real pairs are **Cam 1 → Cam 2 = 1.37 km / 52 s**, **Cam 1 → Cam 3 =
> 1.62 km / 67 s**, **Cam 2 → Cam 3 = 2.10 km / 96 s**. If the camera locations change, get
> the new numbers from the printout of
> `cd api; .\.venv\Scripts\python.exe -m scripts.seed_cameras` and update this slide and
> `docs/DEMO_SCRIPT.md` segment 6 together. A judge can see the pins on the map; quoting a
> distance the map contradicts is worse than quoting none.

---

## Slide 5 — Measured results

> **Every figure here is copied from `docs/STATS.md`, measured on 24 Aug 2026.** If any of
> them is re-measured, change `STATS.md` first and then this slide. Do not estimate, and do
> not add a row `STATS.md` does not support.

**On the slide** — one table, nothing else:

| What we measured | Result |
|---|---|
| Match engine end to end, 5,003 sightings in the table | **37.8 ms** (median) |
| Rows the space-time gate + cap hand to the ranker | **5,003 → at most 500** |
| Similarity ranking — and it does not grow with the table | **0.9 ms** at 5k *and* at 20k rows |
| One frame through the whole AI pipeline, **CPU only, no GPU** | **1.56 s** median · **0.72 fps** sustained |
| `POST /api/frames` answers, without waiting for the AI | **7–12 ms** |
| Sustained phone capture — accepted / dropped / failed | **74 / 0 / 0** |
| Offline map tiles cached — demo runs with WiFi off | **528 tiles, 3.5 MB** |

**Where each number comes from, and the two rows that are deliberately missing**

| Row | Source in `STATS.md` |
|---|---|
| 37.8 ms | §1, `find_candidates` end to end, median of 20 runs, 5,003 sightings. **Always say the sighting count** — the figure is meaningless without it. |
| 5,003 → at most 500 | §1. Say it precisely: 500 is the query's hard cap (250 either side of the incident in time), and the gate rejects everything physically impossible before that cap applies. Do **not** claim "the gate eliminates 90%" — that is the cap talking, not the physics. |
| 0.9 ms, flat 5k → 20k | §1. This is the row that justifies not using pgvector. |
| 1.56 s / 0.72 fps | §2, real street photos through the real endpoint with the real models. |
| 7–12 ms | §2. The API is never blocked by inference. |
| 74 / 0 / 0 | The Phase 6 live phone run: 74 frames accepted, `processed=74 dropped=0 failed=0`. |
| 528 tiles, 3.5 MB | `dashboard/public/tiles`, counted. |

> **Top-1 accuracy and top-5 recall are NOT on this slide, on purpose.** We have no labelled
> ground-truth set, so we have never measured either. `STATS.md` says so in writing, and
> slide 6 says out loud that our embedding cannot separate two motorcycles. An accuracy
> number here would contradict our own measurement, and it is the fastest way to lose a
> technical judge. **If someone asks, the answer is: "we didn't measure it, because we don't
> have labelled pairs — which is exactly why an officer confirms every match."**

**What the speaker says**

"These are measured on this laptop — a 2014 desktop CPU, no GPU used — and they are not
quoted from a paper.

The row to look at is the gate: five thousand sightings down to at most five hundred before
any model runs. That is not a model optimisation, it is arithmetic about how fast a vehicle
can physically travel. It is also why the similarity search costs under a millisecond and
stays there when we quadruple the table.

And the honest one: one frame takes about a second and a half through the full pipeline on
this CPU. Three phones can out-run that. When they do, the queue sheds frames instead of
memory — we would rather miss a vehicle than fall over."

---

## Slide 6 — What this does *not* do

**On the slide**

> ### Four honest limits

| Limit | |
|---|---|
| **A journey ends at our last camera** | We know where the vehicle *was seen*, not where it went. Coverage is the product. |
| **A human confirms every match — by design** | The system proposes. It never issues. |
| **No single visual signal separates two motorcycles** | We measured it ourselves. Fusion narrows the gap; it does not close it. That is why a human decides. |
| **Three cameras is a demo, not a city** | Nothing here is a city-scale claim. |

**What the speaker says**

"Every project at this table will tell you what it does. Here is what ours does not do.

**A journey only covers cameras we control.** We draw straight lines between camera
positions, not road routes, because the honest claim is 'this vehicle was at A, then at B'
— not 'it drove down this street'. Between two cameras we know nothing, and we do not draw
anything that suggests we do. Coverage is the whole limitation, and coverage is a
deployment question, not a research question.

**Second, the human in the loop is deliberate and it is permanent.** We are proposing a
penalty against a person who by definition cannot be identified by plate. Anything
automatic at the end of that chain would be unacceptable, so there is nothing automatic at
the end of that chain.

**Third — and this is the one we would not normally show you.** We tested our own visual
embedding on paired photographs of two motorcycles. Two photos of the *same* bike scored
0.87 similarity. A photo of bike A against bike B — two *different* bikes — scored 0.92.
The different pair beat the same pair. So we know, from our own measurement, that this
embedding on its own cannot identify a vehicle.

That is why it carries only 0.20 — under the colour histogram and well under the physics —
and why the two neural signals together are capped at what the physics carries on its own.
And we measured what the fusion actually
bought us: it narrowed the overlap between same-bike and different-bike pairs by forty per
cent — and **still** did not separate them. It did not change a single ranking.

We are telling you that because it is the argument for the next slide, not against it. Two
different motorcycles genuinely can look more alike to a computer than one motorcycle
photographed twice. So the officer's confirmation is not a compliance checkbox in this
system. It is load-bearing, and we designed it that way after measuring, not before.

**Fourth — three phones on a road is a proof, not a deployment.** We are not claiming a city
today."

---

## Slide 7 — Privacy: built in, and actually running

**On the slide**

| | |
|---|---|
| **48-hour retention** | Any sighting never linked to a case is **deleted automatically**. Running hourly, in the code, today — not a roadmap item |
| **No facial recognition** | No face model, no identity database, no name is ever produced. The rider is compared as clothing and posture, never as a face |
| **A human confirms every match** | Nothing is auto-confirmed, ever |
| **SHA-256 on every image** | The evidence filename **is** the file's own hash. Re-hash it and any tampering shows |

**What the speaker says**

"We record every vehicle that passes. So the first thing anyone should ask us is what
happens to all of that.

A sighting is kept only while it is evidence — linked to a case, or proposed as a match.
Everything else is deleted after 48 hours, by a job that runs every hour. It is running on
this laptop right now. It is not a promise on a slide; it is a scheduled sweep you can
watch in the logs.

We do not do facial recognition, and I want to be precise about that rather than slick,
because you will see a signal called 'rider' on the scoring screen. Where a motorcycle has a
rider, we compare that rider the same way we compare the bike — as an appearance, clothing
and posture. There is no face model anywhere in this system, no identity database to look a
person up in, and no name is ever produced at any point. And that rider crop is inside the
sighting, so it is deleted by the same 48-hour sweep as everything else.

And every image we store is saved under the SHA-256 hash of its own contents — the filename
*is* the fingerprint of the file. Our case-file export prints that hash beside every photo,
so anyone reviewing the case months later can re-hash the image and prove it was not
altered between the roadside and the courtroom. That is the difference between evidence and
a screenshot."

---

## Slide 8 — Scale, and who built it

**On the slide**

> ### Nothing in this design is phone-specific.

```
   phone camera ──┐
   CCTV feed   ───┼──►  POST /api/frames  ──►  the same pipeline, unchanged
   dashcam     ───┤
   recorded file ─┘
```

Three lines:

- **One endpoint.** A camera is anything that can post a JPEG with a token. We used phones
  because we could carry three of them to a road today.
- **CPU only.** No GPU, no cloud, no internet. It ran offline, in this room, in front of you.
- **We know what breaks first, because we measured it.** At 20,000 sightings the match
  engine goes over its own 50 ms budget — and every millisecond of that growth is in the SQL
  gate, not the similarity search. The ranking stays at 0.9 ms whether the table holds five
  thousand rows or twenty thousand. So the next optimisation is the gate; a vector index
  would solve a problem we do not have.

**Team**

| | |
|---|---|
| **Daniyal Ahad** | Database, API, ingest worker, realtime, dashboard, phone camera page, demo infrastructure |
| **Saad** | The AI pipeline — detection, helmet model, fingerprints, score fusion, journeys, watchlist |

**What the speaker says**

"One last thing. Nothing you saw is tied to phones. A camera in this system is anything that
can post a JPEG image with a token — an existing CCTV camera on a pole, a dashcam, a
recorded file. The pipeline behind it does not know and does not care where the frame came
from.

That matters, because the expensive part of rolling this out — putting cameras on the road —
has already been paid for in every city that installed e-challan cameras. Those cameras are
already watching. They are just throwing away every vehicle whose plate they could not read.

We are giving that data back a use."

---

### One-line close — use it if there is time, drop it if there is not

> "A number plate is the one part of a vehicle that comes off with a screwdriver.
> We stopped depending on it."
