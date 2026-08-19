"""Query extraction prompt template."""

QUERY_EXTRACTION_PROMPT = """You are helping a thoughtful coach and author find relevant material \
from their own writing archive to ground a response to an online conversation.

Read the conversation below. Identify the core topic, question, or tension that a \
thoughtful response would need to address.

Return ONLY a focused semantic search query of 10 to 20 words. \
Do not include social media language, usernames, hashtags, platform names, or any commentary. \
Return the query text and nothing else.

CONVERSATION:
{conversation}

SEARCH QUERY:"""
