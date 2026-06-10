# services/voice-gateway/scripts.py

GREETING_TEMPLATE = (
    "Hi! You've reached {business_name}. "
    "I'm an AI assistant and I can help schedule service or get you a quick estimate. "
    "What's the issue you're dealing with today?"
)

CLARIFY_ADDRESS = "Got it. What's the address where you need the service?"

CLARIFY_PROBLEM = "Can you tell me a bit more about what's happening?"

ESTIMATE_RESPONSE = (
    "Based on what you've described, the estimate for {service_type} is typically "
    "between ${min_price} and ${max_price}. "
    "I can get a technician out {time_window}. Does that work for you?"
)

EMERGENCY_RESPONSE = (
    "That sounds urgent. We can have someone at {address} within {eta}. "
    "The estimate is ${min_price}–${max_price}. Shall I book that now?"
)

CONFIRM_BOOKING = (
    "Perfect. I've booked {tech_name} to come to {address} {time_window}. "
    "You'll receive a text confirmation at {phone_number} shortly. "
    "Is there anything else you need?"
)

FALLBACK_CAPTURE = (
    "I'm having a little trouble on my end. "
    "Let me take your name and number and have someone call you right back."
)


def format_script(template: str, **kwargs) -> str:
    """Fill a script template with caller/tenant context."""
    return template.format(**kwargs)
