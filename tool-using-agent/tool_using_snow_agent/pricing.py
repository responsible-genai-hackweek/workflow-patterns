"""Pricing and token analysis utilities for the Snow Cover Analysis Agent."""

import pandas as pd
from langchain_core.messages import AIMessage


# Anthropic Claude Sonnet 4.5 pricing
# Source: https://platform.claude.com/docs/en/about-claude/pricing
PRICING = {
    "input": 3.00,        # $ per 1M base input tokens
    "output": 15.00,      # $ per 1M output tokens
    "cache_write": 3.75,  # $ per 1M cache write tokens (5m TTL)
    "cache_read": 0.30,   # $ per 1M cache read tokens (90% discount!)
}


def analyze_token_usage(messages: list) -> pd.DataFrame:
    """Analyze token usage and cost for a list of messages.
    
    Returns a DataFrame with one row per LLM API call and a total row.
    """
    llm_calls = [
        (idx, msg) for idx, msg in enumerate(messages)
        if isinstance(msg, AIMessage) and getattr(msg, "usage_metadata", None)
    ]
    
    rows = []
    for call_num, (msg_idx, msg) in enumerate(llm_calls, 1):
        usage = msg.usage_metadata
        
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        
        details = usage.get("input_token_details") or {}
        cache_read = details.get("cache_read", 0) or 0
        cache_write = details.get("ephemeral_5m_input_tokens", 0) or 0
        
        base_input = max(input_tokens - cache_read - cache_write, 0)
        
        cost = (
            base_input / 1e6 * PRICING["input"]
            + cache_write / 1e6 * PRICING["cache_write"]
            + cache_read / 1e6 * PRICING["cache_read"]
            + output_tokens / 1e6 * PRICING["output"]
        )
        
        tool_calls = getattr(msg, "tool_calls", None) or []
        tool_names = [tc.get("name") for tc in tool_calls] if tool_calls else []
        
        rows.append({
            "Call #": call_num,
            "Msg Idx": msg_idx,
            "Tools Called": ", ".join(tool_names) if tool_names else "(text)",
            "Input": input_tokens,
            "Cache Write": cache_write,
            "Cache Read": cache_read,
            "Output": output_tokens,
            "Cost ($)": round(cost, 6),
        })
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    
    totals = {
        "Call #": "",
        "Msg Idx": "",
        "Tools Called": "TOTAL",
        "Input": df["Input"].sum(),
        "Cache Write": df["Cache Write"].sum(),
        "Cache Read": df["Cache Read"].sum(),
        "Output": df["Output"].sum(),
        "Cost ($)": round(df["Cost ($)"].sum(), 6),
    }
    df = pd.concat([df, pd.DataFrame([totals])], ignore_index=True)
    
    return df
