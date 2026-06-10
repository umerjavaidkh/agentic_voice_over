# services/agent-brain/prompts/responses.py
# Fixed agent spoken responses after node processing.

INTENT_ADDRESS_FOLLOW_UP = "Got it. What's the address where you need the service?"

ENTITY_FOLLOW_UP_PROMPTS = {
    "address": "What's the address for the service?",
    "caller_name": "And what's your name?",
}
