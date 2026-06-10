from .intents import ENTITY_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
from .responses import ENTITY_FOLLOW_UP_PROMPTS, INTENT_ADDRESS_FOLLOW_UP

NODE_SYSTEM_PROMPTS: dict[str, str] = {
    "intent": INTENT_SYSTEM_PROMPT,
    "entity": ENTITY_SYSTEM_PROMPT,
}

NODE_RESPONSE_PROMPTS: dict[str, str | dict[str, str]] = {
    "intent": INTENT_ADDRESS_FOLLOW_UP,
    "entity": ENTITY_FOLLOW_UP_PROMPTS,
}

__all__ = [
    "ENTITY_FOLLOW_UP_PROMPTS",
    "ENTITY_SYSTEM_PROMPT",
    "INTENT_ADDRESS_FOLLOW_UP",
    "INTENT_SYSTEM_PROMPT",
    "NODE_RESPONSE_PROMPTS",
    "NODE_SYSTEM_PROMPTS",
    "get_response_prompt",
    "get_system_prompt",
]


def get_system_prompt(node: str) -> str:
    """Return the system prompt for a LangGraph node by name."""
    try:
        return NODE_SYSTEM_PROMPTS[node]
    except KeyError as exc:
        raise KeyError(f"Unknown system prompt for node: {node}") from exc


def get_response_prompt(node: str, *, field: str | None = None) -> str:
    """Return a fixed spoken response prompt for a node (optional field key)."""
    try:
        prompt = NODE_RESPONSE_PROMPTS[node]
    except KeyError as exc:
        raise KeyError(f"Unknown response prompt for node: {node}") from exc

    if isinstance(prompt, dict):
        if field is None:
            raise ValueError(f"Node '{node}' requires a field for response prompt lookup")
        try:
            return prompt[field]
        except KeyError as exc:
            raise KeyError(f"Unknown response field '{field}' for node: {node}") from exc

    return prompt
