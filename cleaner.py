# cleaner.py - Apply LLM analysis decisions to remove ads and clean note text.
# No regex pattern matching. All decisions come from the LLM analysis dict.


def apply_cleaning(workflow: dict, analysis: dict) -> dict:
    """
    Remove ad nodes and clean note text using LLM analysis results.

    analysis keys used:
        ad_node_ids   - list of node ids (str or int) to remove entirely
        cleaned_notes - {node_id: cleaned_text} for partial ad removal
    """
    ad_ids: set[int] = {
        int(nid) for nid in analysis.get("ad_node_ids", [])
        if str(nid).lstrip("-").isdigit()
    }
    cleaned_notes: dict[int, str] = {
        int(k): v
        for k, v in analysis.get("cleaned_notes", {}).items()
        if str(k).lstrip("-").isdigit()
    }
    # Nodes whose title field is ad content (LLM flags via cleaned_titles)
    cleaned_titles: dict[int, str] = {
        int(k): v
        for k, v in analysis.get("cleaned_titles", {}).items()
        if str(k).lstrip("-").isdigit()
    }

    nodes = workflow.get("nodes", [])
    kept_nodes: list[dict] = []
    removed_ids: set[int] = set()

    for node in nodes:
        nid: int = node.get("id", -1)

        if nid in ad_ids:
            removed_ids.add(nid)
            print(f"  [cleaner] Removed ad node id={nid} type={node.get('type')}")
            continue

        if nid in cleaned_notes:
            widgets = node.get("widgets_values", [])
            if widgets and isinstance(widgets[0], str):
                node["widgets_values"][0] = cleaned_notes[nid]
                print(f"  [cleaner] Cleaned ad content from note node id={nid}")

        if nid in cleaned_titles:
            node["title"] = cleaned_titles[nid]
            print(f"  [cleaner] Cleaned ad title from node id={nid} type={node.get('type')}")

        kept_nodes.append(node)

    # Remove links that involve removed nodes
    if removed_ids:
        links = workflow.get("links", [])
        workflow["links"] = [
            lnk for lnk in links
            if lnk[1] not in removed_ids and lnk[3] not in removed_ids
        ]
        remaining_link_ids = {lnk[0] for lnk in workflow["links"]}

        for node in kept_nodes:
            for slot in node.get("inputs", []):
                if slot.get("link") is not None and slot["link"] not in remaining_link_ids:
                    slot["link"] = None
            for slot in node.get("outputs", []):
                if "links" in slot:
                    slot["links"] = [lid for lid in slot["links"] if lid in remaining_link_ids]

    workflow["nodes"] = kept_nodes
    return workflow


def deduplicate_nodes(workflow: dict) -> dict:
    """
    Remove structurally identical nodes and rewire connections to the kept copy.
    This is a pure structural operation (no LLM needed).
    """
    nodes = workflow.get("nodes", [])
    links = workflow.get("links", [])

    seen: dict[tuple, int] = {}     # signature -> kept node id
    id_remap: dict[int, int] = {}   # removed id -> kept id
    kept_nodes: list[dict] = []

    for node in nodes:
        sig = _node_signature(node)
        nid: int = node["id"]
        if sig in seen:
            kept_id = seen[sig]
            id_remap[nid] = kept_id
            print(f"  [dedup] Removed duplicate id={nid} type={node.get('type')} -> kept id={kept_id}")
        else:
            seen[sig] = nid
            kept_nodes.append(node)

    if not id_remap:
        workflow["nodes"] = kept_nodes
        return workflow

    # Rewire links: replace removed src/dst ids with their kept equivalents
    new_links = []
    for lnk in links:
        src = id_remap.get(lnk[1], lnk[1])
        dst = id_remap.get(lnk[3], lnk[3])
        new_links.append([lnk[0], src, lnk[2], dst, lnk[4]] + lnk[5:])
    workflow["links"] = new_links

    # Deduplicate output link id lists
    for node in kept_nodes:
        for slot in node.get("outputs", []):
            if "links" in slot:
                slot["links"] = list(dict.fromkeys(slot["links"]))

    workflow["nodes"] = kept_nodes
    return workflow


def _node_signature(node: dict) -> tuple:
    """Hashable structural signature for deduplication."""
    def _hashable(v):
        match v:
            case list():
                return tuple(v)
            case dict():
                return tuple(sorted(v.items()))
            case _:
                return v

    widgets = tuple(_hashable(v) for v in node.get("widgets_values", []))
    inputs = tuple(slot.get("link") for slot in node.get("inputs", []))
    return (node.get("type", ""), widgets, inputs)
