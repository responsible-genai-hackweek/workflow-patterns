"""LLM configuration for the Snow Cover Analysis Agent."""

import os

from langchain_anthropic import ChatAnthropic


# Set your API key (or use environment variable)
# NOTE: Keep your API key secret
os.environ.setdefault("ANTHROPIC_API_KEY", "")


# Claude via Anthropic API with prompt caching enabled
llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",
    model_kwargs={
        "extra_headers": {
            "anthropic-beta": "prompt-caching-2024-07-31"
        },
        # Automatic caching: system prompt and tools are cached automatically
        "cache_control": {"type": "ephemeral"}
    }
)
