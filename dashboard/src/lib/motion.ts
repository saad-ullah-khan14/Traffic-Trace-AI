/**
 * Cheap motion detection, used to decide when to speed up capture.
 *
 * An empty street does not need 5 frames per second, but a vehicle crossing the
 * frame does — at 1 frame per 2 seconds a motorcycle can pass through entirely
 * between two captures. So the loop idles slowly and bursts on movement.
 *
 * The comparison runs on a tiny greyscale thumbnail (32x24). Full-resolution
 * differencing on a mid-range phone costs more than the capture itself, and at
 * this scale we only need "did a large region change", not what changed.
 */

export const MOTION_WIDTH = 32;
export const MOTION_HEIGHT = 24;

/** Mean per-pixel difference (0-255) above which we call it motion. */
export const MOTION_THRESHOLD = 12;

export function toGreyscaleThumbnail(
  source: CanvasImageSource,
  canvas: HTMLCanvasElement,
): Uint8ClampedArray | null {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;

  canvas.width = MOTION_WIDTH;
  canvas.height = MOTION_HEIGHT;
  ctx.drawImage(source, 0, 0, MOTION_WIDTH, MOTION_HEIGHT);

  const { data } = ctx.getImageData(0, 0, MOTION_WIDTH, MOTION_HEIGHT);
  const grey = new Uint8ClampedArray(MOTION_WIDTH * MOTION_HEIGHT);

  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    // Rec. 601 luma. Cheaper than a colour comparison and immune to the
    // white-balance shifts phone cameras make constantly.
    grey[p] = (data[i] * 299 + data[i + 1] * 587 + data[i + 2] * 114) / 1000;
  }
  return grey;
}

export function meanAbsoluteDifference(
  a: Uint8ClampedArray | null,
  b: Uint8ClampedArray | null,
): number {
  if (!a || !b || a.length !== b.length) return 0;

  let total = 0;
  for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i]);
  return total / a.length;
}
