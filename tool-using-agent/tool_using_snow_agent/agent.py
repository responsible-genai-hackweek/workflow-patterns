"""LangGraph agent builder for the Snow Cover Analysis Agent."""

import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, TypedDict

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from .llm import llm
from .tools import get_location, set_date_range, run_analysis
from .state import get_state
from .confirmation import handle_confirmation
from .responses import ResponseStatus, get_response, build_tool_response


SYSTEM_PROMPT = f"""You are a Snow Cover Analysis Assistant.

You help users analyze MODIS Snow Cover data from Planetary Computer.

TOOLS:
- get_location(query): Resolve a place name. Returns status and place info.
- set_date_range(start, end): Set analysis date range. MUST be ISO-8601 format: YYYY-MM-DD/YYYY-MM-DD
- run_analysis(): Run the snow cover analysis. Reads location and dates from internal state - no parameters needed.

TODAY'S DATE: {datetime.now().strftime("%Y-%m-%d")}

DATE RULES:
1. Convert ALL natural language dates to ISO-8601 format before calling set_date_range.
2. The date range MUST use a single "/" separator: YYYY-MM-DD/YYYY-MM-DD
3. Season examples: "summer 2021" → "2021-06-01/2021-08-31", "winter 2023" → "2023-12-01/2024-02-28"
4. Month examples: "February 2023" → "2023-02-01/2023-02-28"
5. You must know: Northern hemisphere seasons (summer=Jun-Aug, winter=Dec-Feb, spring=Mar-May, fall/Sep-Nov)
6. February in leap years has 29 days.
7. For relative dates like "last February", use TODAY'S DATE to calculate the correct year.
8. "Last February" when today is 2026-08-24 → "2026-02-01/2026-02-28"
9. "Last winter" when today is 2026-08-24 → "2025-12-01/2026-02-28"

FLOW RULES:
1. When a tool returns status='pending_confirmation', output the message EXACTLY and wait for user confirmation.
2. When a tool returns status='complete', output the message EXACTLY and proceed.
3. When a tool returns status='error', output the message EXACTLY and ask for correction.
4. Do NOT rephrase tool messages - output them exactly as provided.
5. Do NOT add summaries or additional text - the tool response includes everything.
6. The run_analysis tool reads from state - just call it with no arguments.

WORKFLOW:
1. Call get_location AND set_date_range in parallel (both at the same time)
2. Output date range result first, then location confirmation
3. Wait for user confirmation on location
4. Run analysis

MISSING INFO RULES:
- If location is missing, respond EXACTLY: "I need a location to proceed. Please provide a place name."
- If date is missing, respond EXACTLY: "I need a date range to proceed. Please provide start and end dates."
- Do NOT add extra text or rephrase these messages."""


tools = [get_location, set_date_range, run_analysis]


class GraphState(TypedDict):
    messages: Annotated[list, add_messages]


def _extract_tool_message(tool_message_content: str) -> str:
    """Extract the 'message' field from a tool's JSON response."""
    try:
        data = json.loads(tool_message_content)
        if isinstance(data, dict) and "message" in data:
            return data["message"]
    except (json.JSONDecodeError, TypeError):
        pass
    return tool_message_content


def _last_tool_was_analysis(messages: list) -> bool:
    """Check if the most recent tool call was run_analysis."""
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return any(tc.get("name") == "run_analysis" for tc in msg.tool_calls)
        if isinstance(msg, ToolMessage):
            continue
        break
    return False


def _get_last_human_message(messages: list) -> str | None:
    """Get the content of the last HumanMessage."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return None


def _reorder_tool_messages(messages: list) -> list:
    """Reorder ToolMessages so set_date_range comes before get_location."""
    if len(messages) < 2:
        return messages
    
    last_two = messages[-2:]
    if (len(last_two) == 2 and
        hasattr(last_two[0], "name") and last_two[0].name == "get_location" and
        hasattr(last_two[1], "name") and last_two[1].name == "set_date_range"):
        messages[-2:] = [last_two[1], last_two[0]]
    
    return messages


def build_tool_calling_agent():
    """Build a tool calling agent with LangGraph."""
    llm_with_tools = llm.bind_tools(tools)
    
    def should_continue(state: GraphState) -> Literal["tools", END]:
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END
    
    def call_model(state: GraphState) -> GraphState:
        messages = state["messages"]
        last_message = messages[-1] if messages else None

        # If the last message is a ToolMessage from run_analysis, return the
        # tool's message directly without another LLM call.
        if isinstance(last_message, ToolMessage) and last_message.name == "run_analysis":
            return {"messages": [AIMessage(content=_extract_tool_message(last_message.content))]}

        # Check if this is a confirmation response - handle deterministically
        confirmation_response = None
        info = None
        if isinstance(last_message, HumanMessage):
            response_text, info = handle_confirmation(last_message.content, get_state())
            if response_text is not None:
                confirmation_response = AIMessage(content=response_text)

        # If the user just confirmed and we have everything we need, call
        # run_analysis deterministically without an LLM.
        if (info and info.get("action") == "affirm" and
            not get_state().get("pending_confirmation") and
            get_state().get("location_name") and
            get_state().get("date_start") and
            get_state().get("date_end")):
            run_analysis_call = AIMessage(
                content="",
                tool_calls=[{
                    "id": str(uuid.uuid4()),
                    "name": "run_analysis",
                    "args": {},
                }],
            )
            if confirmation_response:
                return {"messages": [confirmation_response, run_analysis_call]}
            return {"messages": [run_analysis_call]}

        # Build messages for LLM
        llm_messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]

        # Reorder ToolMessages: date range before location
        llm_messages = _reorder_tool_messages(llm_messages)

        response = llm_with_tools.invoke(llm_messages)

        # Return both confirmation response and LLM response
        if confirmation_response:
            return {"messages": [confirmation_response, response]}

        return {"messages": [response]}
    
    # Build graph
    workflow = StateGraph(GraphState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


