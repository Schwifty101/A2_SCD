"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter).
Uses OpenAI-compatible endpoint with JSON mode, Pydantic validation, retry, and fallback.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from ...config import Settings
from ...schemas import Answer, Passage
from .ollama import SYSTEM_INSTRUCTION, _safe_fallback

log = logging.getLogger("rahbar.llm.hosted")


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = (settings.hosted_base_url or "https://api.groq.com/openai/v1").rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.temperature = settings.temperature
        self.timeout = 60.0

    def _build_messages(self, question: str, passages: list[Passage]) -> list[dict[str, str]]:
        evidence_lines = []
        for idx, p in enumerate(passages, start=1):
            evidence_lines.append(
                f"[Passage {idx}] Source: {p.source} | Section: {p.section} | Page: {p.page or 'N/A'}\n"
                f"<<<EVIDENCE\n{p.text}\nEVIDENCE>>>"
            )
        evidence_block = "\n\n".join(evidence_lines) if evidence_lines else "No relevant passages found."

        schema = Answer.model_json_schema()
        user_content = (
            f"Here is the retrieved context:\n{evidence_block}\n\n"
            f"Question: {question}\n\n"
            f"Please respond strictly in JSON matching this JSON schema:\n{json.dumps(schema)}"
        )

        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_content},
        ]

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        messages = self._build_messages(question, passages)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Request JSON mode / response_format
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": self.temperature,
        }

        url = f"{self.base_url}/chat/completions"
        max_attempts = 2
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise ValueError("No choices returned in API response")
                    raw_content = choices[0].get("message", {}).get("content", "")

                    # Validate with Pydantic
                    answer = Answer.model_validate_json(raw_content)
                    return answer

            except (ValidationError, json.JSONDecodeError, ValueError) as val_err:
                last_error = f"Validation failed: {val_err}"
                log.warning("Attempt %d validation failure on hosted provider: %s. Retrying...", attempt, val_err)
            except httpx.TimeoutException as time_err:
                last_error = f"Hosted provider timeout after {self.timeout}s: {time_err}"
                log.error("Attempt %d timeout calling hosted endpoint: %s", attempt, time_err)
            except Exception as exc:
                last_error = f"Hosted provider error: {exc}"
                log.error("Attempt %d error calling hosted endpoint: %s", attempt, exc)

        log.error("All hosted generation attempts failed. Activating fallback: %s", last_error)
        return _safe_fallback(last_error)
