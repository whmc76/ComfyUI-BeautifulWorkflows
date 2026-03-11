# search.py - Web search via local SearXNG to enrich LLM context with real docs.

import urllib.request
import urllib.parse
import urllib.error
import json
from config import SEARXNG_URL


def _searxng_search(query: str, max_results: int = 4) -> list[dict]:
    """Query local SearXNG JSON API. Returns list of {title, content, url}."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": "en",
        "categories": "general",
    })
    try:
        req = urllib.request.Request(
            f"{SEARXNG_URL}?{params}",
            headers={"User-Agent": "ComfyUI-BeautifulWorkflows/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        results = []
        for r in data.get("results", [])[:max_results]:
            snippet = r.get("content", "") or r.get("title", "")
            results.append({
                "title": r.get("title", "")[:100],
                "snippet": snippet[:300],
                "url": r.get("url", ""),
            })
        return results
    except Exception:
        return []


def _extract_key_node_types(workflow: dict) -> list[str]:
    """Pick the most distinctive node types for searching."""
    generic = {
        "Note", "MarkdownNote", "PrimitiveNode", "GetNode", "SetNode",
        "BasicScheduler", "ModelSamplingSD3", "PrimitiveBoolean",
        "CLIPTextEncode", "VAEDecode", "VAEEncode",
    }
    all_types = [n.get("type", "") for n in workflow.get("nodes", []) if n.get("type")]
    unique = list(dict.fromkeys(t for t in all_types if t not in generic))
    unique.sort(key=lambda t: -len(t))  # longer names = more specific
    return unique[:5]


def search_workflow_context(workflow: dict) -> str:
    """
    Search SearXNG for key node types and return a condensed context string
    for the LLM prompt to write accurate usage tips.
    """
    key_types = _extract_key_node_types(workflow)
    if not key_types:
        return ""

    snippets: list[str] = []
    seen: set[str] = set()

    # One broad query covering the top nodes together
    broad_query = f"ComfyUI {' '.join(key_types[:3])} workflow guide"
    for r in _searxng_search(broad_query, max_results=3):
        key = r["snippet"][:60]
        if key and key not in seen:
            seen.add(key)
            snippets.append(f"[{r['title']}] {r['snippet']}")

    # Individual queries for each distinctive node
    for node_type in key_types[:3]:
        for r in _searxng_search(f"ComfyUI {node_type} node how to use", max_results=2):
            key = r["snippet"][:60]
            if key and key not in seen:
                seen.add(key)
                snippets.append(f"[{r['title']}] {r['snippet']}")
        if len(snippets) >= 7:
            break

    if not snippets:
        return ""

    lines = "\n".join(f"- {s}" for s in snippets[:7])
    return f"## WEB SEARCH CONTEXT (use to write accurate usage tips)\n{lines}"
