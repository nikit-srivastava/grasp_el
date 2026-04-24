"""Shared helpers used by the evaluation and expert Streamlit apps."""

import json
import os
from pathlib import Path

import streamlit as st
from pydantic import ValidationError
from universal_ml_utils.io import load_json, load_jsonl
from universal_ml_utils.logging import get_logger

from grasp.model import Message

logger = get_logger("EVALUATION SHARED")


def parse_model_name(filename: str) -> tuple[str, str]:
    """Parse model name and additional info from filename."""
    basename = os.path.basename(filename)
    if basename.endswith(".jsonl"):
        basename = basename[:-6]

    parts = basename.split(".", 1)
    model_name = parts[0]
    additional_info = parts[1] if len(parts) > 1 else ""

    return model_name, additional_info


def display_name_from_file(path) -> str:
    """Build the canonical display name (`name` or `name (info)`) from a file path."""
    name, info = parse_model_name(Path(path).stem)
    return f"{name} ({info})" if info else name


def _mtime(path) -> float:
    """Return mtime for cache keying; 0.0 if missing."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


@st.cache_data
def load_model_outputs(output_file: str, mtime: float) -> dict:
    """Load model outputs from a JSONL file and convert to dictionary by ID.

    Cached on (path, mtime) so repeated reruns hit the cache and file edits
    invalidate it automatically.
    """
    outputs_list = load_jsonl(output_file)
    outputs_dict = {}

    for output in outputs_list:
        if output is None:
            continue

        assert output["id"] not in outputs_dict, (
            f"Duplicate id {output['id']} in {output_file}"
        )
        outputs_dict[output["id"]] = output

    return outputs_dict


def try_load_model_outputs(path) -> dict:
    """Load model outputs; return {} on failure and log the reason."""
    try:
        return load_model_outputs(str(path), _mtime(path))
    except Exception as e:
        logger.warning(f"Failed to load model outputs from {path}: {e}")
        return {}


def try_load_json(path, default=None):
    """Load a JSON file; return `default` on failure and log the reason."""
    try:
        return load_json(str(path))
    except Exception as e:
        logger.warning(f"Failed to load JSON file {path}: {e}")
        return {} if default is None else default


@st.cache_data
def load_rank_json(path: str, mtime: float) -> dict:
    """Cached load of a ranking JSON file, keyed by path + mtime."""
    return load_json(path)


def try_load_rank_json(path) -> dict:
    """Load a ranking JSON via cache; return {} on failure and log the reason."""
    try:
        return load_rank_json(str(path), _mtime(path))
    except Exception as e:
        logger.warning(f"Failed to load ranking file {path}: {e}")
        return {}


def render_messages(output: dict, new_format: bool = True) -> None:
    """Render the generation process (messages/tool calls) for one output."""
    if "messages" not in output:
        st.info("No generation process (messages) available for this output.")
        return

    if new_format:
        try:
            messages = [Message(**msg) for msg in output["messages"]]
            for i, message in enumerate(messages):
                role = message.role.capitalize()
                if isinstance(message.content, str):
                    if not message.content:
                        continue

                    st.markdown(f"**{role}:**")
                    st.markdown(message.content)

                else:
                    content = message.content.get_content()
                    if not content and not message.content.tool_calls:
                        continue

                    if "reasoning" in content:
                        st.markdown("**Reasoning:**")
                        st.markdown(content["reasoning"])

                    if "content" in content:
                        if "reasoning" in content:
                            st.markdown("**Content:**")
                        st.markdown(content["content"])

                    for tool_call in message.content.tool_calls:
                        st.markdown(f"**Tool: {tool_call.name}**")
                        st.code(
                            json.dumps(tool_call.args, indent=2), language="json"
                        )
                        st.markdown("**Result:**")
                        st.markdown(tool_call.result)

                if i < len(messages) - 1:
                    st.markdown("---")

            return
        except (TypeError, ValueError, KeyError, ValidationError) as e:
            logger.warning(
                f"New-format message parsing failed, falling back to legacy: {e}"
            )

    # legacy message format
    def display_tool_call(call, tool_responses):
        tool_call_id = call.get("id")
        tool_name = call.get("function", {}).get("name", "unknown")
        tool_args = call.get("function", {}).get("arguments", "{}")

        formatted_args = json.dumps(json.loads(tool_args), indent=2)

        st.markdown(f"**Tool: {tool_name}**")
        st.code(formatted_args, language="json")

        if tool_call_id in tool_responses:
            tool_response = tool_responses[tool_call_id]
            tool_content = tool_response.get("content", "")
            st.markdown("**Result:**")
            st.markdown(tool_content)

    tool_responses = {}
    for msg in output["messages"]:
        if msg["role"] == "tool":
            tool_responses[msg["tool_call_id"]] = msg

    for i, message in enumerate(output["messages"]):
        role = message.get("role", "unknown")

        if role == "tool":
            continue

        reasoning_content = message.get("reasoning_content", "").strip()
        content = message.get("content", "").strip()
        tool_calls = message.get("tool_calls", [])
        if not reasoning_content and not content and not tool_calls:
            continue

        st.markdown(f"**{role.capitalize()}:**")

        if reasoning_content:
            st.markdown("**Reasoning:**")
            st.markdown(reasoning_content)

        if content:
            if reasoning_content:
                st.markdown("**Content:**")
            st.markdown(content)

        for call in tool_calls:
            display_tool_call(call, tool_responses)

        if i < len(output["messages"]) - 1:
            st.markdown("---")


def render_output_panel(output_entry: dict | None, *, show_answer: bool = True) -> None:
    """Render SPARQL / Result / Selections / Answer for one output entry.

    Mirrors the candidate-column layout from the ranking view's sample explorer.
    """
    if not output_entry:
        st.info("No output available for this example.")
        return

    output_payload = {}
    if isinstance(output_entry, dict):
        output_field = output_entry.get("output", output_entry)
        if isinstance(output_field, dict):
            output_payload = output_field

    rendered_any = False
    sparql_query = output_payload.get("sparql")
    if sparql_query:
        st.markdown("**SPARQL**")
        st.code(sparql_query, language="sparql")
        rendered_any = True

    result_data = output_payload.get("result")
    if result_data is not None:
        st.markdown("**Result**")
        if isinstance(result_data, (dict, list)):
            st.json(result_data)
        else:
            st.code(str(result_data), language="json")
        rendered_any = True

    selections_data = output_payload.get("selections")
    if selections_data:
        st.markdown("**Selections**")
        if isinstance(selections_data, (dict, list)):
            st.json(selections_data)
        else:
            st.write(selections_data)
        rendered_any = True

    if show_answer:
        answer_text = output_payload.get("answer")
        if answer_text:
            with st.expander("Answer"):
                st.markdown(answer_text)
            rendered_any = True

    if not rendered_any:
        fallback_data = (
            output_entry.get("output", output_entry)
            if isinstance(output_entry, dict)
            else output_entry
        )
        st.info("No structured SPARQL/result/selections/answer available.")
        st.write(fallback_data)
