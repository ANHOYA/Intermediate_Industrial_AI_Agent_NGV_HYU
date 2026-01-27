from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import sys

import cv2
import numpy as np


def ensure_logic_path(logic_dir: Path) -> None:
    logic_path = str(Path(logic_dir))
    if logic_path not in sys.path:
        sys.path.insert(0, logic_path)


@dataclass
class BodyRoiResult:
    roi: Any
    crop: np.ndarray


@dataclass
class PinExtractionResult:
    rois: dict[tuple[int, int], tuple[int, int, int, int]]
    model: Any
    holes: list[tuple[float, float]]
    patches: list[Any]
    target_row: int
    target_cols: tuple[int, ...]
    tile_zoom: np.ndarray
    pin_meta: dict[str, Any]
    pin_meta_json: str


def extract_body_roi_image(img_bgr: np.ndarray, logic_dir: Path) -> BodyRoiResult:
    ensure_logic_path(logic_dir)
    from body_roi_crop import adaptive_body_roi

    roi = adaptive_body_roi(img_bgr)
    crop = img_bgr[roi.y0:roi.y1, roi.x0:roi.x1].copy()
    return BodyRoiResult(roi=roi, crop=crop)


def build_pin_meta(
    image_id: str,
    target_row: int,
    target_cols: tuple[int, ...],
    rois: dict[tuple[int, int], tuple[int, int, int, int]],
    patches: list[Any],
) -> dict[str, Any]:
    patch_by_col = {int(p.col): p for p in patches}
    meta: dict[str, Any] = {
        "image_id": image_id,
        "target_row": target_row,
        "targets": [],
    }
    for col in target_cols:
        key = (col, target_row)
        if key not in rois:
            continue
        x0, y0, x1, y1 = rois[key]
        patch = patch_by_col.get(col)
        zoom_roi = None
        target_hole = None
        if patch is not None:
            zx0, zy0, zx1, zy1 = patch.zoom_roi
            zoom_roi = {
                "x0": int(zx0),
                "y0": int(zy0),
                "x1": int(zx1),
                "y1": int(zy1),
            }
            hx, hy = patch.target_hole
            target_hole = {"x": int(hx), "y": int(hy)}
        meta["targets"].append(
            {
                "col": int(col),
                "row": int(target_row),
                "roi": {"x0": int(x0), "y0": int(y0), "x1": int(x1), "y1": int(y1)},
                "target_hole": target_hole,
                "zoom_roi": zoom_roi,
            }
        )
    return meta


def build_pin_tiles_and_meta(
    img_bgr: np.ndarray,
    image_id: str,
    logic_dir: Path,
) -> PinExtractionResult:
    ensure_logic_path(logic_dir)
    import pin_tile_pack as pin_pack
    import hole_grid_roi_experiment as grid_logic

    rois, model, holes = pin_pack.compute_rois(img_bgr)
    patches = pin_pack.build_pin_patches(img_bgr, rois, model, holes)

    target_row = int(grid_logic.TARGET_ROW)
    target_cols = tuple(int(c) for c in grid_logic.TARGET_COLS)

    zoom_by_col = {int(p.col): p.zoom_patch for p in patches}
    zoom_imgs = [zoom_by_col[col] for col in target_cols if col in zoom_by_col]
    tile_zoom = pin_pack.tile_horizontal(zoom_imgs) if zoom_imgs else img_bgr.copy()

    pin_meta = build_pin_meta(
        image_id=image_id,
        target_row=target_row,
        target_cols=target_cols,
        rois=rois,
        patches=patches,
    )
    pin_meta_json = json.dumps(pin_meta, ensure_ascii=False, indent=2)

    return PinExtractionResult(
        rois=rois,
        model=model,
        holes=holes,
        patches=patches,
        target_row=target_row,
        target_cols=target_cols,
        tile_zoom=tile_zoom,
        pin_meta=pin_meta,
        pin_meta_json=pin_meta_json,
    )


def build_edge_vis_tile(
    img_bgr: np.ndarray,
    rois: dict[tuple[int, int], tuple[int, int, int, int]],
    target_row: int,
    target_cols: tuple[int, ...],
    logic_dir: Path,
    gray: np.ndarray | None = None,
) -> np.ndarray:
    ensure_logic_path(logic_dir)
    import hole_grid_roi_experiment as grid_logic
    import pin_tile_pack as pin_pack

    if gray is None:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    edge_vis_patches: list[np.ndarray] = []
    vmask = None
    for col in target_cols:
        key = (col, target_row)
        if key not in rois:
            continue
        roi_box = rois[key]
        edges = grid_logic.edges_in_roi(gray, roi_box, vmask=vmask, mask_vertical=False)
        x0, y0, x1, y1 = roi_box
        patch = img_bgr[y0:y1, x0:x1].copy()
        patch[edges > 0] = (0, 0, 255)
        edge_vis_patches.append(patch)

    tile_edgevis = pin_pack.tile_horizontal(edge_vis_patches) if edge_vis_patches else img_bgr.copy()
    return tile_edgevis
