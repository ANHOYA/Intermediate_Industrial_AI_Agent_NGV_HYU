from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

IMG_DIR = Path("img data")
OUT_DIR = Path("roi_edges_only")

# Target holes on the bottom row in grid coordinates.
TARGET_COLS = (1, 2, 3)


@dataclass
class GridModel:
    col_centers: list[float]
    row_centers: list[float]
    pitch_x: float
    pitch_y: float
    bottom_row_y: float


def load_images() -> list[Path]:
    return sorted(IMG_DIR.glob("DEV_*.png"))


def detect_holes(gray: np.ndarray) -> list[tuple[float, float]]:
    """Detect circular holes using adaptive threshold + connected components."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thr = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )
    # Reduce thin vertical-line influence.
    hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, hor_kernel, iterations=1)

    num, labels, stats, centroids = cv2.connectedComponentsWithStats(thr, connectivity=8)
    holes: list[tuple[float, float]] = []
    for i in range(1, num):
        x, y, w, h, area = stats[i].tolist()
        if area < 120 or area > 2200:
            continue
        ratio = max(w, h) / max(1, min(w, h))
        if ratio > 1.6:
            continue
        cx, cy = centroids[i]
        holes.append((float(cx), float(cy)))
    return holes


def kmeans_1d(values: Iterable[float], k: int) -> list[float]:
    arr = np.array(list(values), dtype=np.float32).reshape(-1, 1)
    if len(arr) < k:
        # Fallback: unique sorted values.
        uniq = sorted(set(float(v) for v in arr.flatten().tolist()))
        return uniq
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _compactness, labels, centers = cv2.kmeans(
        arr, k, None, criteria, 8, cv2.KMEANS_PP_CENTERS
    )
    centers = [float(c[0]) for c in centers]
    centers.sort()
    return centers


def median_pitch(centers: list[float]) -> float:
    if len(centers) < 2:
        return 1.0
    diffs = np.diff(np.array(centers, dtype=np.float32))
    return float(np.median(diffs))


def build_grid_model(holes: list[tuple[float, float]]) -> GridModel:
    if not holes:
        raise RuntimeError("No holes detected; cannot build grid model.")

    xs = [p[0] for p in holes]
    ys = [p[1] for p in holes]

    # We observe roughly 5 columns and 4 rows in these images.
    col_centers = kmeans_1d(xs, k=5)
    row_centers = kmeans_1d(ys, k=4)

    pitch_x = median_pitch(col_centers)
    pitch_y = median_pitch(row_centers)

    bottom_row_y = max(row_centers) if row_centers else float(max(ys))
    return GridModel(
        col_centers=col_centers,
        row_centers=row_centers,
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        bottom_row_y=bottom_row_y,
    )


def clamp_roi(x0: int, y0: int, x1: int, y1: int, w: int, h: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(x0, w - 1))
    y0 = max(0, min(y0, h - 1))
    x1 = max(x0 + 1, min(x1, w))
    y1 = max(y0 + 1, min(y1, h))
    return x0, y0, x1, y1


def hole_roi_above(
    col_x: float,
    row_y: float,
    pitch_x: float,
    pitch_y: float,
    w: int,
    h: int,
) -> tuple[int, int, int, int]:
    """ROI just above a bottom-row hole (avoid the row above)."""
    # Slightly wider ROI to capture more context while still centered on the hole.
    half_w = int(round(0.60 * pitch_x))
    x0 = int(round(col_x)) - half_w
    x1 = int(round(col_x)) + half_w

    # Keep the bottom (hole center) fixed, with moderate vertical span.
    y1 = int(np.ceil(row_y + 0.12 * pitch_y))
    y0 = int(round(row_y - 0.60 * pitch_y))
    return clamp_roi(x0, y0, x1, y1, w=w, h=h)


def edges_in_roi(gray: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = roi
    patch = gray[y0:y1, x0:x1]
    blur = cv2.GaussianBlur(patch, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    return edges


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = load_images()
    if not paths:
        raise RuntimeError(f"No DEV_*.png found in {IMG_DIR}")

    for path in paths:
        img_bgr = cv2.imread(str(path))
        if img_bgr is None:
            print(f"[skip] failed to read {path}")
            continue

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        holes = detect_holes(gray)
        model = build_grid_model(holes)

        h, w = gray.shape[:2]
        for col_idx in TARGET_COLS:
            col_x = model.col_centers[col_idx]
            row_y = model.bottom_row_y
            roi = hole_roi_above(col_x, row_y, model.pitch_x, model.pitch_y, w=w, h=h)
            edges = edges_in_roi(gray, roi)

            out_name = f"{path.stem}_edges_{col_idx}_0.png"
            cv2.imwrite(str(OUT_DIR / out_name), edges)

        print(f"[ok] {path.name} -> edges saved")


if __name__ == "__main__":
    main()
