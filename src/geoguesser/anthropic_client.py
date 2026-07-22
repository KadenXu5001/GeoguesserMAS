from __future__ import annotations

import os
from typing import Any, Mapping

import requests


class AnthropicMessagesClient:
    """Small Anthropic Messages API client with explicit-key authentication."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 180.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def create_message(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=dict(payload),
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            detail = response.text[:500].replace("\n", " ")
            raise RuntimeError(f"Anthropic API returned HTTP {response.status_code}: {detail}")
        document = response.json()
        if not isinstance(document, dict):
            raise RuntimeError("Anthropic API returned a non-object response")
        return document


def create_anthropic_client() -> AnthropicMessagesClient:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required; set it in .env or the process environment"
        )
    return AnthropicMessagesClient(api_key)
