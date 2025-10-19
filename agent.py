from typing import TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from utils_logger import setup_logger
from offline_model import offline_model
from online_model import online_llm, normalize_label

logger = setup_logger("upay.agent")


class AgentState(TypedDict, total=False):
    input_text: str
    offline_label: Optional[str]
    online_label: Optional[str]
    final_label: Optional[str]
    after_hours: bool
    meta: Dict[str, Any]


def offline_node(state: AgentState) -> AgentState:
    text = state.get("input_text", "")
    label = offline_model.predict(text)
    label = normalize_label(label) if isinstance(label, str) else label
    logger.info("Offline label: %s", label)
    return {"offline_label": label}


def online_node(state: AgentState) -> AgentState:
    text = state.get("input_text", "")
    label = online_llm.predict(text)
    label = normalize_label(label) if isinstance(label, str) else label
    logger.info("Online label: %s", label)
    return {"online_label": label}


def route_after_offline(state: AgentState) -> str:
    lab = state.get("offline_label")
    if lab is None or lab == "Mediate":
        return "online"
    return "finalize"


def finalize_node(state: AgentState) -> AgentState:
    offline_lab = state.get("offline_label")
    online_lab = state.get("online_label")
    after_hours = bool(state.get("after_hours", False))

    # Selection logic per requirements
    if offline_lab and offline_lab != "Mediate":
        chosen = offline_lab
        origin = "offline"
    else:
        chosen = online_lab or "Mediate"
        origin = "online" if online_lab else "default"

    if after_hours and chosen == "Mediate":
        # After 9 PM, mediate is treated as fraud before sending results
        chosen = "Fraud"

    logger.info("Final label: %s (origin=%s, after_hours=%s)", chosen, origin, after_hours)
    meta = {
        "origin": origin,
        "after_hours": after_hours,
        "offline_label": offline_lab,
        "online_label": online_lab,
    }
    return {"final_label": chosen, "meta": meta}


def build_agent():
    g = StateGraph(AgentState)
    g.add_node("offline", offline_node)
    g.add_node("online", online_node)
    g.add_node("finalize", finalize_node)

    g.set_entry_point("offline")
    g.add_conditional_edges("offline", route_after_offline, {"online": "online", "finalize": "finalize"})
    g.add_edge("online", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


# Singleton compiled graph
agent_graph = build_agent()
