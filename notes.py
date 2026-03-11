# notes.py - Inject LLM-generated header and footer Note nodes into the workflow.
# No template logic or workflow-type detection here; text comes from the LLM.

import os
from config import CANVAS_START_X, CANVAS_START_Y


def load_user_info(path: str) -> str:
    """Read user_info.md and return its raw text (passed as-is to the LLM)."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _next_node_id(nodes: list[dict]) -> int:
    ids = [n.get("id", 0) for n in nodes]
    return max(ids, default=0) + 1


def inject_notes(workflow: dict, analysis: dict) -> dict:
    """
    Remove any previously injected header/footer notes, then prepend fresh
    header and footer Note nodes using the LLM-generated text from analysis.

    analysis keys used:
        header_note  - markdown string for the header node
        footer_note  - short string for the footer/credits node
    """
    header_text: str = analysis.get("header_note", "# Workflow\n\nBeautified with ComfyUI-BeautifulWorkflows.")
    footer_text: str = analysis.get("footer_note", "Made with ComfyUI-BeautifulWorkflows")

    nodes = workflow.get("nodes", [])

    # Strip previously injected notes so re-running is idempotent
    nodes = [n for n in nodes if not _is_injected_note(n)]

    NOTE_W = 500
    NOTE_GAP = 30

    if nodes:
        # Place notes to the RIGHT of all nodes, aligned to the top of the canvas
        max_x = max(
            n.get("pos", [0, 0])[0] + n.get("size", [240, 100])[0]
            for n in nodes
        )
        top_y = min(n.get("pos", [0, CANVAS_START_Y])[1] for n in nodes)
        note_x = max_x + 120   # 120px gap after the rightmost node/group
        note_y = top_y
    else:
        note_x, note_y = CANVAS_START_X, CANVAS_START_Y

    next_id = _next_node_id(nodes)

    # Estimate header height from line count so footer doesn't overlap
    header_lines = header_text.count("\n") + 1
    header_h = max(200, header_lines * 22 + 40)

    header_node = _make_note_node(
        node_id=next_id,
        title="Workflow Info",
        text=header_text,
        pos=[note_x, note_y],
        size=[NOTE_W, header_h],
    )
    footer_node = _make_note_node(
        node_id=next_id + 1,
        title="Credits",
        text=footer_text,
        pos=[note_x, note_y + header_h + NOTE_GAP],
        size=[NOTE_W, 160],
    )

    workflow["nodes"] = [header_node, footer_node] + nodes
    return workflow


def _make_note_node(
    node_id: int,
    title: str,
    text: str,
    pos: list[int],
    size: list[int],
) -> dict:
    return {
        "id": node_id,
        "type": "Note",
        "pos": pos,
        "size": size,
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "title": title,
        "widgets_values": [text],
        "_injected": True,  # marker for idempotent removal
    }


def _is_injected_note(node: dict) -> bool:
    """Detect previously injected header/footer notes so we can replace them."""
    if node.get("_injected"):
        return True
    # Legacy detection for notes created before the _injected marker existed
    if node.get("type") == "Note" and node.get("title") in ("Workflow Info", "Credits"):
        widgets = node.get("widgets_values", [])
        if widgets and isinstance(widgets[0], str):
            text = widgets[0]
            return text.startswith(("# ", "Made with", "Made by"))
    return False
