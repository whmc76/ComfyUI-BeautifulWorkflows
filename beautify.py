#!/usr/bin/env python3
# beautify.py - CLI entry point for LLM-driven ComfyUI workflow beautification.

import argparse
import json
import os
import sys

from llm import analyze_workflow, compare_models, sanitize_filename
from cleaner import apply_cleaning, deduplicate_nodes
from grouping import apply_categories, create_groups
from layout import apply_layout
from notes import load_user_info, inject_notes

INPUTS_DIR = "inputs"
OUTPUTS_DIR = "outputs"
USER_INFO_PATH = os.path.join(INPUTS_DIR, "user_info.md")


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def process_workflow(
    input_path: str,
    output_path: str | None = None,
    model: str | None = None,
) -> str:
    print(f"\n[beautify] Processing: {input_path}")

    with open(input_path, encoding="utf-8") as fh:
        workflow = json.load(fh)

    user_info_text = load_user_info(USER_INFO_PATH)

    # Step 1: structural deduplication (no LLM needed)
    print("  -> Deduplicating nodes...")
    workflow = deduplicate_nodes(workflow)

    # Step 2: comprehensive LLM analysis - ONE call for all decisions
    print("  -> Calling LLM for comprehensive analysis...")
    analysis = analyze_workflow(workflow, user_info_text, model=model)

    # Step 3: apply cleaning decisions from analysis
    print("  -> Applying ad removal and note cleaning...")
    workflow = apply_cleaning(workflow, analysis)

    # Step 4: apply category assignments from analysis
    print("  -> Applying node categories...")
    grouped = apply_categories(workflow, analysis)

    # Step 5: layout (pure geometry)
    print("  -> Applying layout...")
    workflow = apply_layout(workflow, grouped)

    # Step 6: create group bounding boxes
    print("  -> Creating category groups...")
    workflow = create_groups(workflow, grouped)

    # Step 7: inject LLM-generated header/footer notes
    print("  -> Injecting header and footer notes...")
    workflow = inject_notes(workflow, analysis)

    # Step 8: determine output path
    # Use LLM-generated name derived from input filename to ensure stable, non-duplicating outputs.
    # LLM descriptive name is embedded in the header note, not used for the filename.
    if output_path is None:
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        # Use LLM descriptive name as primary, but append a hash of the original
        # filename to guarantee uniqueness across different input files.
        stem = os.path.splitext(os.path.basename(input_path))[0]
        import hashlib
        from llm import _extract_tech_identifiers, sanitize_filename as _sf
        suffix = hashlib.md5(stem.encode()).hexdigest()[:6]
        llm_name = sanitize_filename(analysis.get("filename", "workflow"))

        # Strip any tech identifier the LLM may have put in (could be partial/wrong)
        # then prepend the authoritative identifiers extracted directly from node names
        tech_ids = _extract_tech_identifiers(workflow)
        if tech_ids:
            tech_prefix = _sf("_".join(tech_ids.split(", ")))
            # Remove any existing tech prefix from llm_name to avoid duplication
            for token in tech_ids.lower().replace(", ", "_").split("_"):
                if llm_name.startswith(token + "_"):
                    llm_name = llm_name[len(token)+1:]
            llm_name = f"{tech_prefix}_{llm_name}"

        output_path = os.path.join(OUTPUTS_DIR, f"{llm_name}_{suffix}.json")

    # Strip internal-only fields before saving (ComfyUI doesn't need them)
    _INTERNAL_KEYS = {"_category", "_injected"}
    for node in workflow.get("nodes", []):
        for k in _INTERNAL_KEYS:
            node.pop(k, None)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(workflow, fh, indent=2, ensure_ascii=False)

    print(f"  -> Saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

def batch_process(model: str | None = None) -> None:
    if not os.path.isdir(INPUTS_DIR):
        print(f"[error] inputs/ directory not found. Create it and add workflow JSON files.")
        sys.exit(1)

    json_files = sorted(
        f for f in os.listdir(INPUTS_DIR)
        if f.endswith(".json") and os.path.isfile(os.path.join(INPUTS_DIR, f))
    )

    if not json_files:
        print("[info] No JSON files found in inputs/")
        return

    print(f"[beautify] Found {len(json_files)} workflow(s) to process")
    results: list[tuple[str, str | None, str | None]] = []

    for fname in json_files:
        input_path = os.path.join(INPUTS_DIR, fname)
        try:
            out = process_workflow(input_path, model=model)
            results.append((fname, out, None))
        except Exception as exc:
            print(f"  [error] Failed to process {fname}: {exc}")
            results.append((fname, None, str(exc)))

    print("\n=== Summary ===")
    for fname, out, err in results:
        if err:
            print(f"  FAIL  {fname}: {err}")
        else:
            print(f"  OK    {fname} -> {out}")


# ---------------------------------------------------------------------------
# Model comparison
# ---------------------------------------------------------------------------

def run_model_comparison() -> None:
    if not os.path.isdir(INPUTS_DIR):
        print("[error] inputs/ directory not found.")
        sys.exit(1)

    json_files = [
        os.path.join(INPUTS_DIR, f)
        for f in os.listdir(INPUTS_DIR)
        if f.endswith(".json")
    ][:3]

    if not json_files:
        print("[error] No JSON files in inputs/ for comparison")
        return

    workflows = []
    for p in json_files:
        with open(p, encoding="utf-8") as fh:
            workflows.append(json.load(fh))

    user_info_text = load_user_info(USER_INFO_PATH)
    print(f"[compare] Testing models on {len(workflows)} workflow(s)...\n")
    results = compare_models(workflows, user_info_text)

    for model_name, entries in results.items():
        print(f"=== {model_name} ===")
        for i, entry in enumerate(entries):
            print(f"  Workflow {i + 1}:")
            print(f"    filename:   {entry['filename']}")
            print(f"    categories: {entry['categories_count']} nodes classified")
            print(f"    ad_ids:     {entry['ad_ids']}")
            print(f"    valid JSON: {entry['valid']}")
            print(f"    raw[:200]:  {entry['raw_snippet']!r}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ComfyUI Workflow Beautifier - LLM-driven pipeline"
    )
    parser.add_argument(
        "input", nargs="?",
        help="Single workflow JSON file to process (omit for batch mode)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path for single-file mode",
    )
    parser.add_argument(
        "--model",
        help="Ollama model to use (e.g. qwen3:8b). Overrides config default.",
    )
    parser.add_argument(
        "--compare-models", action="store_true",
        help="Run all configured models on sample workflows and print comparison",
    )
    args = parser.parse_args()

    match (args.compare_models, args.input):
        case (True, _):
            run_model_comparison()
        case (False, str(path)):
            process_workflow(path, args.output, model=args.model)
        case _:
            batch_process(model=args.model)


if __name__ == "__main__":
    main()
