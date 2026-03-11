# layout.py - Pure geometry: position nodes in a 16:9-friendly grid.
# Each category can wrap into multiple sub-columns if it exceeds MAX_COLUMN_HEIGHT,
# keeping the overall canvas aspect ratio close to 16:9.

import math
from config import (
    NODE_CATEGORIES,
    NODE_WIDTH, NODE_HEIGHT_BASE, NODE_HEIGHT_PER_WIDGET,
    COLUMN_GAP, ROW_GAP,
    CANVAS_START_X, CANVAS_START_Y,
)

# Target canvas height. Nodes that exceed this wrap into a new sub-column.
# ~1080px keeps a group readable without heavy vertical scrolling.
MAX_COLUMN_HEIGHT = 900


def _node_size(node: dict) -> tuple[int, int]:
    """
    Return (width, height) for layout calculations.
    Uses the node's existing size if present, otherwise estimates from content.
    Never overrides the original - we only use this for stacking math.
    """
    existing = node.get("size")
    if existing and len(existing) == 2 and existing[1] > 10:
        return int(existing[0]), int(existing[1])
    # Fallback estimate for nodes with no stored size
    widgets = node.get("widgets_values", [])
    if isinstance(widgets, dict):
        widgets = list(widgets.values())
    inputs  = len(node.get("inputs",  []))
    outputs = len(node.get("outputs", []))
    slots   = max(inputs, outputs)
    h = NODE_HEIGHT_BASE + len(widgets) * NODE_HEIGHT_PER_WIDGET + slots * 20
    return NODE_WIDTH, h


def _split_into_subcolumns(nodes: list[dict]) -> list[list[dict]]:
    """
    Split a flat node list into sub-columns so no sub-column exceeds
    MAX_COLUMN_HEIGHT. Tries to balance heights across sub-columns.
    """
    total_h = sum(_node_size(n)[1] + ROW_GAP for n in nodes)
    n_cols = max(1, math.ceil(total_h / MAX_COLUMN_HEIGHT))

    # Target height per sub-column
    target = total_h / n_cols
    cols: list[list[dict]] = [[]]
    current_h = 0.0

    for node in nodes:
        h = _node_size(node)[1] + ROW_GAP
        # Start new sub-column if adding this node would overshoot target
        # (but always fill at least one node per sub-column)
        if current_h + h > target * 1.1 and cols[-1] and len(cols) < n_cols:
            cols.append([])
            current_h = 0.0
        cols[-1].append(node)
        current_h += h

    return cols


def apply_layout(workflow: dict, grouped: dict[str, list]) -> dict:
    """
    Position every node in a multi-sub-column grid.

    Layout:
    - Categories ordered left-to-right by pipeline order (Input first, Output last).
    - Within each category, nodes wrap into sub-columns when height > MAX_COLUMN_HEIGHT.
    - All sub-columns of a category share the same color.
    - Sub-columns within a category are separated by COLUMN_GAP / 2.
    - Category groups are separated by COLUMN_GAP.
    """
    ordered_categories = sorted(
        NODE_CATEGORIES.items(),
        key=lambda item: item[1]["order"],
    )

    x = CANVAS_START_X
    for category, cat_config in ordered_categories:
        nodes = grouped.get(category, [])
        if not nodes:
            continue

        color = cat_config["color"]
        sub_cols = _split_into_subcolumns(nodes)
        inner_gap = 30  # tight gap between sub-columns of same category

        for sub_col in sub_cols:
            y = CANVAS_START_Y
            col_w = max(_node_size(n)[0] for n in sub_col)  # widest node in this sub-col
            for node in sub_col:
                w, h = _node_size(node)
                node["pos"]   = [x, y]
                # Only set color, never touch size - preserve original node dimensions
                node["color"] = color
                y += h + ROW_GAP
            x += col_w + inner_gap

        # Replace last inner gap with full category gap
        x = x - inner_gap + COLUMN_GAP

    return workflow
