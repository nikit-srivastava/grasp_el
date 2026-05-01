#!/usr/bin/env python3
## Sample usage:
# source ./venv_grasp/bin/activate
# python scripts/annotate_entities.py data/sample_questions.jsonl data/sample_annotated.jsonl --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql --openai-base-url http://lola.cs.uni-paderborn.de:9292/v1 --openai-api-key nokeyrequired --model qwen-3.6-27b --progress
# python scripts/annotate_entities.py data/qald10_questions.jsonl data/qald10_annotated.jsonl --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql --openai-base-url http://lola.cs.uni-paderborn.de:9292/v1 --openai-api-key nokeyrequired --model gpt-oss-120b --progress
# python scripts/annotate_entities.py data/qald10_questions.jsonl data/qald10_annotated.jsonl --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql --openai-base-url http://lola.cs.uni-paderborn.de:9292/v1 --openai-api-key nokeyrequired --model qwen-3.6-27b --progress
"""Annotate questions in a JSONL file with Wikidata entity and property links.

Each input record should have a text field (default: "question"). If an "id" field
is present it is used for resume tracking; otherwise a stable ID is derived from
the "sources" field (or the record index as fallback). All input fields (e.g.
"sources") are copied through to the output.

Annotation format:
  [{"span": "<text in question>", "identifier": "wd:Q183", "label": "Germany", "type": "entity"}, ...]

The Wikidata index is read from --index-dir (default: data/kg-index relative to this script).
"""

import argparse
import json
import os
import sys

from openai import OpenAI
from tqdm import tqdm

from grasp.configs import KgConfig, KgInfo
from grasp.functions import kg_functions, search_entity, search_property
from grasp.manager import KgManager, load_kg_manager

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_DEFAULT_INDEX_DIR = os.path.join(_PROJECT_ROOT, "data", "kg-index")

SYSTEM_PROMPT = """\
You are a knowledge graph entity linker. Given a question or text:
1. Identify all entity and property mentions that should be linked to the knowledge graph.
   - Entities: people, places, organisations, events, concepts → use search_entity
   - Properties: relationships and predicates → use search_property
2. Search for each mention using the provided tools. Pick the best matching candidate.
3. When all searches are done, output ONLY a JSON array — no prose, no markdown fences.

Output format (JSON array, nothing else):
[
  {"span": "<exact text from input>", "identifier": "<short id e.g. wd:Q183>", "label": "<label>", "type": "entity"},
  {"span": "<exact text from input>", "identifier": "<short id e.g. wdt:P35>", "label": "<label>", "type": "property"}
]

If nothing relevant is found, output: []"""


def _stable_id(rec: dict, index: int) -> str:
    """Derive a stable, unique ID for a record that may lack an 'id' field."""
    if "id" in rec:
        return rec["id"]
    sources = rec.get("sources")
    if sources and isinstance(sources, list) and len(sources) > 0:
        first = sources[0]
        if isinstance(first, dict):
            dataset = first.get("dataset", "")
            qid = first.get("qid", "")
            lang = first.get("lang", "")
            if dataset and qid:
                return f"{dataset}:{qid}:{lang}"
    return f"__idx_{index}__"


def _parse_json_annotations(content: str) -> list[dict] | None:
    """Parse a JSON array from LLM output, stripping markdown fences if present."""
    content = content.strip()
    if content.startswith("```"):
        # strip opening fence
        content = content[content.index("\n") + 1 :]
        # strip closing fence
        if "```" in content:
            content = content[: content.rindex("```")]
        content = content.strip()
    try:
        result = json.loads(content)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return None


def annotate(
    text: str,
    manager: KgManager,
    client: OpenAI,
    model: str,
    tools: list[dict],
    k: int,
    max_steps: int,
) -> list[dict]:
    known: set[str] = set()
    openai_tools = [{"type": "function", "function": t} for t in tools]

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]

    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
        )
        choice = resp.choices[0]
        msg = choice.message

        if choice.finish_reason != "tool_calls":
            return _parse_json_annotations(msg.content or "[]") or []

        # Build assistant message dict with tool calls
        assistant: dict = {"role": "assistant"}
        if msg.content:
            assistant["content"] = msg.content
        assistant["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
        messages.append(assistant)

        # Execute each tool call
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            query = args["query"]
            page = args.get("page", 1)

            if tc.function.name == "search_entity":
                result = search_entity([manager], manager.kg, query, k, known, page=page)
            elif tc.function.name == "search_property":
                result = search_property([manager], manager.kg, query, k, known, page=page)
            else:
                result = f"Unknown function: {tc.function.name}"

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Ran out of steps — ask for final output without tools
    messages.append({
        "role": "user",
        "content": "Output the final JSON annotations array now based on your searches above.",
    })
    final = client.chat.completions.create(model=model, messages=messages)
    return _parse_json_annotations(final.choices[0].message.content or "[]") or []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Annotate questions in a JSONL file with Wikidata entity/property links",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Input JSONL file (records with 'id' + text field)")
    parser.add_argument("output", help="Output JSONL file")
    parser.add_argument(
        "--sparql-endpoint",
        required=True,
        metavar="URL",
        help="Wikidata SPARQL endpoint",
    )
    parser.add_argument(
        "--index-dir",
        default=_DEFAULT_INDEX_DIR,
        metavar="DIR",
        help="Directory containing GRASP KG indices (expects a 'wikidata' subdirectory)",
    )
    parser.add_argument(
        "--openai-base-url",
        default=None,
        metavar="URL",
        help="OpenAI API base URL (omit to use the official OpenAI API)",
    )
    parser.add_argument(
        "--openai-api-key",
        default=None,
        metavar="KEY",
        help="OpenAI API key (defaults to OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Model name",
    )
    parser.add_argument(
        "--field",
        default="question",
        metavar="FIELD",
        help="JSONL field containing the text to annotate",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        metavar="N",
        help="Search candidates returned per query",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        metavar="N",
        help="Max tool-call iterations per question",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file (default: resume from where it left off)",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show a progress bar",
    )
    args = parser.parse_args()

    # --- Validate output ---
    if os.path.exists(args.output) and args.overwrite:
        os.remove(args.output)

    # --- Load KG manager ---
    # GRASP resolves indices via the GRASP_INDEX_DIR env var; set it before loading.
    os.environ["GRASP_INDEX_DIR"] = os.path.abspath(args.index_dir)
    manager = load_kg_manager(
        KgConfig(
            kg="wikidata",
            info=KgInfo(endpoint=args.sparql_endpoint),
        )
    )
    manager.load_models()

    # --- Build tool list, validate indices exist ---
    tools = [
        t
        for t in kg_functions(
            [manager], "search", list_k=args.k, search_k=args.k, search_max_pages=3
        )
        if t["name"] in {"search_entity", "search_property"}
    ]
    if not tools:
        wikidata_index_dir = os.path.join(os.path.abspath(args.index_dir), "wikidata")
        print(
            f"No search indices found under {wikidata_index_dir!r}.\n"
            "Build them first:\n"
            f"  GRASP_INDEX_DIR={args.index_dir} grasp data wikidata --endpoint {args.sparql_endpoint}\n"
            f"  GRASP_INDEX_DIR={args.index_dir} grasp index wikidata",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- OpenAI client ---
    api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
    client = OpenAI(base_url=args.openai_base_url, api_key=api_key)

    # --- Load inputs ---
    with open(args.input) as f:
        records = [json.loads(line) for line in f if line.strip()]

    # Assign stable IDs for resume tracking (don't mutate original 'id' if present)
    for i, rec in enumerate(records):
        rec["_stable_id"] = _stable_id(rec, i)

    # --- Resume: skip already-done IDs (only those without errors) ---
    done: set[str] = set()
    if os.path.exists(args.output):
        with open(args.output) as read_f:
            lines = [json.loads(line) for line in read_f if line.strip()]
        # Rewrite output keeping only successful records, so errored ones are retried
        with open(args.output, "w") as write_f:
            for rec in lines:
                if "error" not in rec:
                    done.add(rec.get("_stable_id", ""))
                    write_f.write(json.dumps(rec) + "\n")

    pending = [r for r in records if r["_stable_id"] not in done]
    if not pending:
        print("All records already annotated. Use --overwrite to redo.", file=sys.stderr)
        return

    print(
        f"Annotating {len(pending)} records "
        f"({len(done)} already done, {len(records)} total)",
        file=sys.stderr,
    )

    it = tqdm(pending, desc="Annotating") if args.progress else pending

    with open(args.output, "a") as out_f:
        for rec in it:
            text = rec.get(args.field)
            if not text:
                out = {**rec, "annotations": [], "error": f"field '{args.field}' missing or empty"}
            else:
                try:
                    annotations = annotate(
                        text, manager, client, args.model, tools, args.k, args.max_steps
                    )
                    out = {**rec, "annotations": annotations}
                except Exception as e:
                    out = {**rec, "annotations": [], "error": str(e)}

            out_f.write(json.dumps(out) + "\n")
            out_f.flush()


if __name__ == "__main__":
    main()
