# grouping.py - Apply LLM category assignments and create ComfyUI group nodes.
# No pattern matching. All categorisation comes from the LLM analysis dict.

from config import NODE_CATEGORIES, GROUP_PADDING, CONSOLE_GROUP_LABELS

# Input/Output console groups get larger font and extra padding to stand out
_CONSOLE_FONT_SIZE = 32
_CONSOLE_EXTRA_PADDING = 20
_DEFAULT_FONT_SIZE = 24


def apply_categories(workflow: dict, analysis: dict) -> dict[str, list]:
    """
    Stamp each node with _category from the LLM analysis and return nodes
    grouped by category. Falls back to "Utility" for unrecognised ids.
    """
    node_categories: dict[str, str] = {
        str(k): v for k, v in analysis.get("node_categories", {}).items()
    }
    valid_categories = set(NODE_CATEGORIES.keys())
    grouped: dict[str, list] = {cat: [] for cat in NODE_CATEGORIES}

    for node in workflow.get("nodes", []):
        nid = str(node.get("id"))
        cat = node_categories.get(nid, "Utility")
        if cat not in valid_categories:
            print(f"  [grouping] Unknown category '{cat}' for node id={nid}, using Utility")
            cat = "Utility"
        node["_category"] = cat
        grouped[cat].append(node)

    # Log Input/Output console contents
    for console in ("Input", "Output"):
        nodes = grouped.get(console, [])
        if nodes:
            types = [n.get("type", "?") for n in nodes]
            print(f"  [grouping] {console} Console: {types}")

    return grouped


def create_groups(workflow: dict, grouped: dict[str, list]) -> dict:
    """Generate ComfyUI group nodes (bounding boxes) for each non-empty category.
    Input and Output console groups get distinct titles, larger font, and extra padding.
    """
    groups = []
    for category, nodes in grouped.items():
        if not nodes:
            continue

        color = NODE_CATEGORIES[category]["color"]
        is_console = category in ("Input", "Output")
        pad = GROUP_PADDING + (_CONSOLE_EXTRA_PADDING if is_console else 0)
        font_size = _CONSOLE_FONT_SIZE if is_console else _DEFAULT_FONT_SIZE
        title = CONSOLE_GROUP_LABELS.get(category, category)

        xs  = [n.get("pos", [0, 0])[0] for n in nodes]
        ys  = [n.get("pos", [0, 0])[1] for n in nodes]
        x2s = [n.get("pos", [0, 0])[0] + (n.get("size") or [240, 100])[0] for n in nodes]
        y2s = [n.get("pos", [0, 0])[1] + (n.get("size") or [240, 100])[1] for n in nodes]

        gx = min(xs)  - pad
        gy = min(ys)  - pad - 40   # extra for title bar
        gw = max(x2s) - min(xs) + pad * 2
        gh = max(y2s) - min(ys) + pad * 2 + 40

        groups.append({
            "title": title,
            "bounding": [gx, gy, gw, gh],
            "color": color,
            "font_size": font_size,
            "locked": False,
        })

    workflow["groups"] = groups
    return workflow
