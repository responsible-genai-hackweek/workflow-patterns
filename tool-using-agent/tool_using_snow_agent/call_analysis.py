"""Utilities for explaining and breaking down agent responses in a conversation."""

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


def _summarize(content, max_len=80):
    """Shorten a string for display."""
    text = str(content).replace("\n", " ")
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _tool_names(tool_calls):
    """Extract tool names from a list of tool_calls."""
    return [tc.get("name") for tc in (tool_calls or []) if tc.get("name")]


def _find_trigger(messages, idx):
    """Find the most recent HumanMessage or ToolMessage before this message."""
    prev_idx = idx - 1
    prompt = "Initial model response"
    while prev_idx >= 0:
        prev = messages[prev_idx]
        if isinstance(prev, HumanMessage):
            prompt = f"User input: {_summarize(prev.content)}"
            break
        elif isinstance(prev, ToolMessage):
            tool_name = getattr(prev, "name", "unknown")
            # If there are multiple parallel tool results, summarize the group
            tool_names = [tool_name]
            lookback = prev_idx - 1
            while lookback >= 0 and isinstance(messages[lookback], ToolMessage):
                n = getattr(messages[lookback], "name", "unknown")
                if n not in tool_names:
                    tool_names.append(n)
                lookback -= 1
            tool_names.reverse()
            prompt = f"Tool result(s): {', '.join(tool_names)}"
            break
        # Skip over other AIMessages (they are not the trigger)
        prev_idx -= 1
    return prompt


def _deterministic_kind(msg, trigger):
    """Classify an AIMessage without usage_metadata."""
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        return "Deterministic tool call"
    if "Tool result" in trigger:
        return "Deterministic result summary"
    return "Deterministic confirmation/response"


def explain_llm_calls(messages):
    """Print a human-readable breakdown of every agent response.

    This includes both:
    - LLM API calls (with token usage and tool calls)
    - Deterministic responses (no LLM call, no tokens used)
    """
    agent_messages = [
        (idx, msg)
        for idx, msg in enumerate(messages)
        if isinstance(msg, AIMessage)
    ]

    if not agent_messages:
        print("No agent responses found in the conversation.")
        return

    llm_calls = [(idx, msg) for idx, msg in agent_messages if getattr(msg, "usage_metadata", None)]
    deterministic = [(idx, msg) for idx, msg in agent_messages if not getattr(msg, "usage_metadata", None)]

    print(f"Agent response breakdown: {len(agent_messages)} total")
    print(f"  - {len(llm_calls)} LLM API call(s)")
    print(f"  - {len(deterministic)} deterministic response(s) (no LLM / no tokens)")
    print()

    llm_num = 0
    for idx, msg in agent_messages:
        usage = getattr(msg, "usage_metadata", None)
        trigger = _find_trigger(messages, idx)

        if usage:
            llm_num += 1
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            details = usage.get("input_token_details") or {}
            cache_read = details.get("cache_read", 0) or 0
            cache_write = details.get("ephemeral_5m_input_tokens", 0) or 0

            next_tools = _tool_names(getattr(msg, "tool_calls", None))
            if next_tools:
                action = f"decided to call tool(s): {', '.join(next_tools)}"
            else:
                action = "produced final text response"

            print(f"[LLM Call #{llm_num}] message index {idx}")
            print(f"  Triggered by: {trigger}")
            print(f"  Model action: {action}")
            print(f"  Tokens: input={input_tokens} ({cache_read} cache read, {cache_write} cache write), output={output_tokens}")
            print(f"  Output preview: {_summarize(msg.content, 120)}")
        else:
            kind = _deterministic_kind(msg, trigger)
            next_tools = _tool_names(getattr(msg, "tool_calls", None))

            print(f"[{kind}] message index {idx}")
            print(f"  Triggered by: {trigger}")
            print("  No LLM call; tokens = 0")

            if next_tools:
                print(f"  Action: calling tool(s): {', '.join(next_tools)}")
                print(f"  Output preview: {_summarize(msg.content, 120)}")
            else:
                print(f"  Output: {_summarize(msg.content, 120)}")

        print()
