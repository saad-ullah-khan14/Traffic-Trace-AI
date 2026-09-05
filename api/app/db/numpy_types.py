"""Load Postgres real[] straight into numpy arrays, skipping Python floats.

Why this exists: profiling the Phase 3 matching path showed Postgres executing
the gate query in 8 ms while psycopg spent ~90 ms turning 500 x 512 values into
Python float objects. Converting the raw binary buffer with numpy instead makes
that step effectively free, which is the difference between missing and meeting
the 50 ms budget.

Only the BINARY wire format is handled. Text-format cursors keep psycopg's
default behaviour and return lists, so every consumer must accept either — in
practice they all go through np.asarray, which takes both.

If the buffer is ever shaped unexpectedly (multi-dimensional, or containing NULL
elements), this falls back to returning a list rather than guessing. A wrong
embedding would corrupt matching silently, which is far worse than being slow.
"""

import numpy as np
from psycopg.adapt import Loader
from psycopg.pq import Format

# oid 1021 = float4[] (what `real[]` is stored as)
FLOAT4_ARRAY_OID = 1021

# Postgres binary array header for a 1-D array:
#   int32 ndim | int32 has_null | int32 element_oid | int32 dim | int32 lower_bound
_HEADER_BYTES = 20
# Each element is int32 length prefix + 4 bytes of big-endian float32.
_ELEMENT_BYTES = 8


# One element as Postgres lays it out: a big-endian length prefix followed by a
# big-endian float32. Viewing the payload as this structured type lets numpy
# read the whole array in a single pass, with exactly one copy at the end.
_ELEMENT_DTYPE = np.dtype([("length", ">i4"), ("value", ">f4")])


class NumpyFloat4ArrayLoader(Loader):
    """Binary float4[] -> np.ndarray(dtype=float32)."""

    format = Format.BINARY

    def load(self, data) -> object:
        view = memoryview(data)

        if len(view) < _HEADER_BYTES:
            return []

        header = np.frombuffer(view, dtype=">i4", count=5)
        ndim = int(header[0])
        has_null = int(header[1])
        length = int(header[3])

        # Anything unusual: hand back a plain list rather than risk misreading.
        if (
            ndim != 1
            or has_null
            or length < 0
            or len(view) - _HEADER_BYTES != length * _ELEMENT_BYTES
        ):
            return _fallback_list(bytes(view[_HEADER_BYTES:]), max(length, 0))

        elements = np.frombuffer(
            view, dtype=_ELEMENT_DTYPE, count=length, offset=_HEADER_BYTES
        )

        # Every element must declare a 4-byte payload, or the layout is not what
        # we assume and reinterpreting it would silently corrupt the embedding.
        if not np.all(elements["length"] == 4):
            return _fallback_list(bytes(view[_HEADER_BYTES:]), length)

        # astype does the byte-swap and the single allocation together.
        return elements["value"].astype(np.float32)


def _fallback_list(payload: bytes, length: int) -> list:
    """Decode element by element. Slow, but only ever hits unexpected data."""
    out = []
    offset = 0
    for _ in range(length):
        size = int.from_bytes(payload[offset:offset + 4], "big", signed=True)
        offset += 4
        if size == -1:
            out.append(None)
            continue
        out.append(np.frombuffer(payload[offset:offset + size], dtype=">f4")[0].item())
        offset += size
    return out


def register_numpy_loaders(context=None) -> None:
    """Install the loader. Called once from app.db.session on pool creation."""
    from psycopg import adapters

    target = context.adapters if context is not None else adapters
    target.register_loader(FLOAT4_ARRAY_OID, NumpyFloat4ArrayLoader)
