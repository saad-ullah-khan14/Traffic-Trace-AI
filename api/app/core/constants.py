"""Constants agreed with Teammate 1 at Integration Checkpoint A (Phase 2).

These are contract values, not tuning knobs. Changing one here without changing
it in pipeline/ silently breaks matching — the SQL gate and pipeline.is_reachable
must agree exactly or we hand the scorer candidates it never expected.

Once Teammate 1 ships pipeline/types.py, EMBEDDING_DIM should be imported from
there rather than duplicated. It is defined here only because that file does not
exist yet; contracts/schema.sql enforces the same number via a CHECK constraint.
"""

# CLIP ViT-B/32 output size.
EMBEDDING_DIM = 512

# Reachability: could a vehicle seen at camera A be at camera B in this gap?
MAX_SPEED_KMH = 60.0
GRACE_SECONDS = 30.0

# ⚠️ BENCH-TESTING OVERRIDE — set to None before any demo or deployment.
#
# The largest gap the gate is allowed to demand between two cameras. The real
# figure comes from the geometry: at the seeded spacing it is 25-116 seconds, so
# testing one phone at a time means standing around for two minutes between every
# camera. At 2.0 the gate effectively stops enforcing travel time, and a video
# can be shown to camera 1, 2 and 3 back to back.
#
# This does NOT affect scores. Space-time was removed from the identity score on
# 30 Aug (see services/matching.py), so how quickly the vehicle appears no longer
# changes any percentage — only whether the candidate is offered at all.
#
# **It does invalidate the pitch's central claim** — "a vehicle cannot be 3 km
# away four seconds later" — because with this set, it can. `scripts/preflight.py`
# fails loudly while it is on, so it cannot be forgotten quietly.
#
# Restored to None on 31 Aug, after measuring that real physics does not throw
# the true match away. At the current camera positions the gate demands:
#
#     Camera 1 -> Camera 2   0.90 km    >=  23.8 s
#     Camera 1 -> Camera 3   2.44 km    >= 117.0 s
#
# and the one confirmed cross-camera match of the 31 Aug run was a 30 s hop —
# through by 6 seconds. That margin is the filming rule: **leave ~30 s before
# showing the video to camera 2 and ~2 minutes before camera 3.** Faster than
# that and the real match is rejected before it is ever scored, and the review
# screen comes up empty.
#
# Set back to 2.0 only for bench testing, and set it to None again before any
# demo — preflight will fail while it is on.
GATE_MAX_REQUIRED_GAP_SECONDS = None

# How far back the space-time gate looks. Beyond this a "match" stops being
# evidence of a journey and starts being a coincidence.
MATCH_WINDOW_SECONDS = 30 * 60

# One pass of one vehicle past one camera is one candidate. Two sightings at the
# same camera closer together than this are frames of the same pass, and only the
# clearest is offered — see services/matching.collapse_bursts.
#
# Measured on the 31 Aug run, gaps between sightings at one camera:
#     same pass         1 - 2 seconds
#     different bike    120 - 346 seconds
# There is nothing in between, so 5 leaves margin for a bike held up in traffic
# without coming close to a second vehicle. Similarity was measured too and
# CANNOT be used: same pass 0.850-0.943 overlaps different bike 0.691-0.889.
BURST_WINDOW_SECONDS = 5.0

# The API ranks visually and hands this many to pipeline.score_candidates,
# which fuses the remaining signals.
CANDIDATE_TOP_K = 20

# How good a candidate must be before an officer is asked about it at all.
#
# The point of this product is to NARROW the search. Handing over twenty
# lookalike bikes and asking a human to sort them out is the work we exist to
# remove — as Daniyal put it, if we give the police every picture, they may as
# well find it themselves.
#
# Measured 30 Aug on labelled footage, once space-time was taken out of the
# identity score (see build_scoring_payload):
#     candidates he confirmed as the same rider   0.741  0.761  0.817
#     candidates he said were different bikes     0.632  0.638  0.637
# 0.70 appeared to sit in the gap with room on both sides.
#
# **31 Aug, on a second real run, that gap does not exist.** One incident, three
# candidates left after burst dedupe, labelled by Daniyal on the review screen:
#     0.856   different bike   (rider 0.818  vehicle 0.864  colour 0.870)
#     0.754   THE SAME BIKE    (rider 0.862  vehicle 0.851  colour 0.636)
#     0.719   different bike   (rider 0.805  vehicle 0.826  colour 0.605)
#
# The true match sits BETWEEN two false ones. No value of this constant separates
# them: raise it past 0.754 and the real vehicle is thrown away; lower it and
# nothing is excluded. **Do not tune this number to fix a bad candidate list** —
# on real footage there is nothing here to tune. It stays at 0.70 only to drop
# the obvious rubbish below every label seen so far.
#
# The one thing the run does suggest: `rider` ranked the true match first of the
# three, and `colour` is what lifted a different bike above it. That is a weight
# question, not a threshold question, and it is ONE labelled example — not enough
# to move a weight on. Collect labels across several runs first; every officer
# confirm/reject already stores one in `matches.decision`.
#
# ponytail: if a true match is ever missed, this number is the first place to
# look — the review screen says plainly when it has excluded everything, so a
# miss is visible rather than silent.
MIN_CANDIDATE_SCORE = 0.70

# Embeddings arrive already L2-normalized from process_frame. We verify rather
# than re-normalize: re-normalizing would hide it if Teammate 1's side ever
# stopped, and scores would quietly degrade with no error anywhere.
NORM_TOLERANCE = 1e-3
