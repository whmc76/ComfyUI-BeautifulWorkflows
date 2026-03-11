# llm.py - Core LLM engine. All intelligent decisions flow through here.

import json
import re
import urllib.request
import urllib.error
from config import OLLAMA_BASE_URL, OLLAMA_MODELS, OLLAMA_TIMEOUT, NODE_CATEGORIES
from search import search_workflow_context


# ---------------------------------------------------------------------------
# Raw API
# ---------------------------------------------------------------------------

def _ollama_generate(model: str, prompt: str) -> str | None:
    """Call Ollama /api/generate. Returns the response text or None on failure."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,  # disable chain-of-thought for thinking models (qwen3/deepseek-r1)
        "options": {"temperature": 0.1},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        print(f"  [llm] Ollama request failed ({model}): {exc}")
        return None


def _parse_json_response(text: str) -> dict | None:
    """
    Robustly extract a JSON object from an LLM response.
    Always uses first-{ to last-} extraction to handle nested objects correctly.
    The old regex approach was non-greedy and would stop at the first closing brace.
    """
    if not text:
        return None

    # Strip markdown code fences if present (but still use outermost braces below)
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    # Extract from outermost { to outermost } (handles nested objects correctly)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Strip trailing commas (common LLM mistake: {"a": 1,})
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _extract_ad_candidates(workflow: dict) -> dict[str, dict]:
    """
    Extract text that could contain ads for LLM inspection:
    - Note/Markdown node widget text
    - Any node's custom title field
    - Image nodes with a filename/path widget (could be a promo image)
    Returns {node_id: {type, title, text}} for nodes with non-empty ad-candidate text.
    """
    # Image-type nodes that could carry promotional images
    IMAGE_NODE_TYPES = {"LoadImage", "ImageFromBase64", "ETN_LoadImageBase64", "PreviewImage"}

    candidates = {}
    for node in workflow.get("nodes", []):
        nid = str(node.get("id"))
        ntype = node.get("type", "")
        title = node.get("title", "")
        text = ""

        # Note/Markdown nodes: grab widget text
        if ntype == "Note" or "note" in ntype.lower() or "markdown" in ntype.lower():
            widgets = node.get("widgets_values", [])
            if isinstance(widgets, dict):
                widgets = list(widgets.values())
            if widgets and isinstance(widgets[0], str):
                text = widgets[0][:300]

        # Image loader nodes: expose filename as text for LLM to judge
        elif ntype in IMAGE_NODE_TYPES:
            widgets = node.get("widgets_values", [])
            if isinstance(widgets, dict):
                widgets = list(widgets.values())
            if widgets and isinstance(widgets[0], str):
                text = f"[image file: {widgets[0][:100]}]"

        if title or text:
            candidates[nid] = {
                "type": ntype,
                "title": title[:120] if title else "",
                "text": text,
            }
    return candidates


def _extract_tech_identifiers(workflow: dict) -> str:
    """
    Scan node type names for model/version identifiers so the LLM can use
    precise names instead of inventing abbreviations.
    Returns a short summary string, e.g. "LTX2, LTXV, SDXL".
    """
    import re
    all_types = " ".join(n.get("type", "") for n in workflow.get("nodes", []))
    # Patterns that signal specific model versions / frameworks
    patterns = [
        r"LTX2(?:\.\d+)?",    # LTX2, LTX2.3
        r"LTXV",
        r"SDXL",
        r"SD3(?:\.\d+)?",
        r"Flux(?:Dev|Schnell)?",
        r"HunyuanVideo",
        r"WanVideo",
        r"CogVideo",
        r"Mochi",
        r"ELLA",
        r"AnimateDiff",
        r"IPAdapter",
        r"InstantID",
        r"FaceDetailer",
        r"ADetailer",
        r"ControlNet",
        r"\bSAM2?\b",
        r"GroundingDINO",
    ]
    found = []
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, all_types, re.IGNORECASE):
            token = m.group(0)
            key = token.upper()
            if key not in seen:
                seen.add(key)
                found.append(token)
    return ", ".join(found) if found else ""


def _build_analysis_prompt(workflow: dict, user_info_text: str, web_context: str = "") -> str:
    """
    Minimal prompt: LLM sees id+type list, ad candidates, web search context,
    and user info. Widget values and links stay in Python - LLM owns strategy only.
    """
    nodes = workflow.get("nodes", [])
    node_list = "\n".join(f"  {n.get('id')}: {n.get('type', 'unknown')}" for n in nodes)
    node_ids = [str(n.get("id")) for n in nodes]

    tech_ids = _extract_tech_identifiers(workflow)
    tech_section = f"\n## DETECTED TECH IDENTIFIERS (use these EXACT strings in filename and header, do not abbreviate or invent alternatives)\n{tech_ids}\n" if tech_ids else ""

    ad_candidates = _extract_ad_candidates(workflow)
    ad_section = ""
    if ad_candidates:
        lines = []
        for nid, info in ad_candidates.items():
            parts = [f"  id={nid} type={info['type']}"]
            if info["title"]:
                parts.append(f"title={info['title']!r}")
            if info["text"]:
                parts.append(f"text={info['text']!r}")
            lines.append(" | ".join(parts))
        ad_section = "\n## AD CANDIDATES (titles + note texts)\n" + "\n".join(lines) + "\n"

    web_section = f"\n{web_context}\n" if web_context else ""

    return f"""You are a ComfyUI workflow analyst. Return ONLY a JSON object with your strategy decisions.

## USER INFO
{user_info_text or "(none)"}

## NODE LIST (id: type)
{node_list}
{tech_section}{ad_section}{web_section}
## OUTPUT SCHEMA
{{
  "filename": "<snake_case, max 5 words, no extension>",
  "node_categories": {{ "<id>": "<category>", ... }},
  "ad_node_ids": ["<id>", ...],
  "cleaned_notes": {{ "<id>": "<note text with ads removed>" }},
  "cleaned_titles": {{ "<id>": "<cleaned title, or empty string to clear it>" }},
  "header_note": "<STYLE: use emoji, horizontal rules (---), bold labels, code spans for node/model names. Structure: big title with emoji, --- divider, metadata badges (🎨 Type / 🤖 Model / ⚡ Technique), --- divider, numbered usage steps with emoji bullets, --- divider, tips/notes section. Make it look like a polished README card, not plain text.>",
  "footer_note": "<STYLE: mini card with emoji. Use --- dividers, bold author name, emoji per platform (🎬 YouTube, 📺 Bilibili, 📕 Xiaohongshu, 🌐 Website etc.), each platform on its own line. End with a motivational or creative tagline.>"
}}

## CATEGORY RULES (assign ALL ids: {', '.join(node_ids)})
Priority: Input and Output override all other categories.
- **Input**: nodes the USER directly interacts with to start the workflow — image/video upload nodes (LoadImage, VHS_LoadVideo), prompt text nodes (CLIPTextEncode where user writes prompts), seed/config primitive nodes the user typically tweaks. These become the leftmost "Input Console" column.
- **Output**: nodes that produce final results — SaveImage, SaveVideo, PreviewImage, VHS_VideoCombine, any node that writes files or shows results. These become the rightmost "Output Console" column.
- Loader: model/checkpoint/VAE/LoRA/CLIP/UNET loaders (NOT image upload)
- Conditioning: conditioning, guidance, style, flux guidance
- ControlNet: controlnet load/apply, preprocessors
- Sampler: KSampler, scheduler, sigmas, noise
- Latent: latent image, VAE encode/decode, empty latent
- Image: image processing/upscale/resize/composite (NOT save/preview)
- Utility: everything else (math, text, primitive, note, switch, get/set)

## AD DETECTION RULES
- ad_node_ids: purely promotional nodes (discord, patreon, social shilling). Remove entirely.
- cleaned_notes: mixed content notes - return text with ad lines stripped.
- cleaned_titles: ad-only titles - return "" to clear.

Return valid JSON only. No markdown fences. No trailing commas.
"""


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

MAX_RETRIES = 3


def analyze_workflow(workflow: dict, user_info_text: str, model: str | None = None) -> dict:
    """
    Web search -> LLM analysis with retry. Raises RuntimeError if all attempts fail.
    No heuristic fallback - quality matters more than always succeeding.
    """
    print("  [search] Fetching web context for workflow nodes...")
    web_context = search_workflow_context(workflow)
    if web_context:
        print(f"  [search] Got {web_context.count(chr(10))} lines of context")
    else:
        print("  [search] No web context (offline or no results)")

    prompt = _build_analysis_prompt(workflow, user_info_text, web_context)
    m = model or OLLAMA_MODELS[0]

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  [llm] Calling {m} (attempt {attempt}/{MAX_RETRIES})...")
        raw = _ollama_generate(m, prompt)
        if not raw:
            print(f"  [llm] No response from {m}, retrying...")
            continue
        result = _parse_json_response(raw)
        if result and _validate_analysis(result, workflow):
            _log_analysis(result)
            return result
        print(f"  [llm] Response failed validation, retrying...")

    raise RuntimeError(f"LLM analysis failed after {MAX_RETRIES} attempts with model {m}")


def _validate_analysis(result: dict, workflow: dict) -> bool:
    """Check that the parsed JSON has the required keys and sensible content."""
    required = {"filename", "node_categories", "ad_node_ids", "header_note", "footer_note"}
    if not required.issubset(result.keys()):
        missing = required - result.keys()
        print(f"  [llm] Missing keys in response: {missing}")
        return False
    if not isinstance(result.get("node_categories"), dict):
        print("  [llm] node_categories is not a dict")
        return False
    if not isinstance(result.get("ad_node_ids"), list):
        print("  [llm] ad_node_ids is not a list")
        return False
    return True


def _log_analysis(result: dict) -> None:
    """Print a readable summary of LLM decisions."""
    print(f"  [llm] Filename: {result.get('filename')}")
    cats = result.get("node_categories", {})
    # Tally categories
    tally: dict[str, int] = {}
    for cat in cats.values():
        tally[cat] = tally.get(cat, 0) + 1
    print(f"  [llm] Node categories: {dict(sorted(tally.items()))}")
    ad_ids = result.get("ad_node_ids", [])
    if ad_ids:
        print(f"  [llm] Ad nodes to remove: {ad_ids}")
    cleaned = result.get("cleaned_notes", {})
    if cleaned:
        print(f"  [llm] Notes to clean: {list(cleaned.keys())}")
    cleaned_titles = result.get("cleaned_titles", {})
    if cleaned_titles:
        print(f"  [llm] Titles to clean: {list(cleaned_titles.keys())}")


# ---------------------------------------------------------------------------
# Fallback heuristics (minimal, not the main path)
# ---------------------------------------------------------------------------

_AD_SIGNALS = [
    "discord.gg", "discord.com/invite", "t.me/", "patreon.com",
    "ko-fi.com", "buymeacoffee", "civitai.com/user",
    "join our discord", "follow me on", "subscribe to", "support me",
    "like and subscribe", "check out my", "patreon", "donation",
]

_LOADER_HINTS = {"load", "checkpoint", "lora", "vaeload", "clip", "unet", "dualclip"}
_CONDITIONING_HINTS = {"clip", "conditioning", "encode", "prompt", "guidance", "style"}
_CONTROLNET_HINTS = {"controlnet", "apply", "preprocessor", "detector"}
_SAMPLER_HINTS = {"sampler", "scheduler", "sigmas", "noise"}
_LATENT_HINTS = {"latent", "vae", "empty"}
_IMAGE_HINTS = {"image", "preview", "save", "upscale", "resize", "blend", "composite"}


def _heuristic_category(node_type: str) -> str:
    t = node_type.lower()
    if any(h in t for h in _LOADER_HINTS):
        return "Loader"
    if any(h in t for h in _CONTROLNET_HINTS):
        return "ControlNet"
    if any(h in t for h in _SAMPLER_HINTS):
        return "Sampler"
    if any(h in t for h in _LATENT_HINTS):
        return "Latent"
    if any(h in t for h in _IMAGE_HINTS):
        return "Image"
    if any(h in t for h in _CONDITIONING_HINTS):
        return "Conditioning"
    return "Utility"


def _heuristic_filename(workflow: dict) -> str:
    types = {n.get("type", "") for n in workflow.get("nodes", [])}
    parts = []
    if any("flux" in t.lower() for t in types):
        parts.append("flux")
    elif any("sdxl" in t.lower() for t in types):
        parts.append("sdxl")
    if any("video" in t.lower() or "ltx" in t.lower() for t in types):
        parts.append("video")
    if any("controlnet" in t.lower() for t in types):
        parts.append("controlnet")
    if any("load" in t.lower() and "image" in t.lower() for t in types):
        parts.append("img2img")
    else:
        parts.append("txt2img")
    parts.append("workflow")
    return "_".join(parts)


def _heuristic_contains_ad(text: str) -> bool:
    tl = text.lower()
    return any(sig in tl for sig in _AD_SIGNALS)


def _fallback_analysis(workflow: dict, user_info_text: str) -> dict:
    """Minimal heuristic analysis when LLM is unavailable."""
    nodes = workflow.get("nodes", [])
    node_categories: dict[str, str] = {}
    ad_node_ids: list[str] = []
    cleaned_notes: dict[str, str] = {}

    for node in nodes:
        nid = str(node.get("id"))
        ntype = node.get("type", "")
        node_categories[nid] = _heuristic_category(ntype)

        if ntype in ("Note", "Markdown") or "note" in ntype.lower():
            widgets = node.get("widgets_values", [])
            if widgets and isinstance(widgets[0], str):
                text = widgets[0]
                if _heuristic_contains_ad(text):
                    lines = [ln for ln in text.splitlines() if not _heuristic_contains_ad(ln)]
                    cleaned = "\n".join(lines).strip()
                    if not cleaned:
                        ad_node_ids.append(nid)
                    else:
                        cleaned_notes[nid] = cleaned

    # Build simple header/footer from user_info_text
    header = "# Workflow\n\nBeautified ComfyUI workflow.\n\n## Usage\n1. Load in ComfyUI\n2. Adjust prompts\n3. Queue Prompt"
    footer = "Made with ComfyUI-BeautifulWorkflows"
    if user_info_text:
        lines = user_info_text.splitlines()
        for ln in lines:
            if ln.startswith("# "):
                header = ln + "\n\n" + "\n".join(header.splitlines()[1:])
            if "Footer" in ln:
                idx = user_info_text.find("## Footer")
                if idx != -1:
                    footer = user_info_text[idx + 9:].strip().splitlines()[0].strip()

    return {
        "filename": _heuristic_filename(workflow),
        "node_categories": node_categories,
        "ad_node_ids": ad_node_ids,
        "cleaned_notes": cleaned_notes,
        "cleaned_titles": {},
        "header_note": header,
        "footer_note": footer,
    }


# ---------------------------------------------------------------------------
# Model comparison utility
# ---------------------------------------------------------------------------

def compare_models(workflows: list[dict], user_info_text: str = "") -> dict:
    """
    Run each configured model on sample workflows and return comparison results.
    Each model gets the full analysis prompt; results are compared side by side.
    """
    results: dict[str, list] = {m: [] for m in OLLAMA_MODELS}
    for wf in workflows[:3]:
        web_context = search_workflow_context(wf)
        prompt = _build_analysis_prompt(wf, user_info_text, web_context)
        for model in OLLAMA_MODELS:
            raw = _ollama_generate(model, prompt)
            parsed = _parse_json_response(raw) if raw else None
            results[model].append({
                "filename": parsed.get("filename") if parsed else None,
                "categories_count": len(parsed.get("node_categories", {})) if parsed else 0,
                "ad_ids": parsed.get("ad_node_ids", []) if parsed else [],
                "raw_snippet": (raw or "")[:200],
                "valid": parsed is not None and _validate_analysis(parsed, wf),
            })
    return results


def sanitize_filename(name: str) -> str:
    """Clean an LLM-returned filename into a filesystem-safe snake_case string."""
    name = name.strip().strip('"\'').lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:60] or "workflow"
