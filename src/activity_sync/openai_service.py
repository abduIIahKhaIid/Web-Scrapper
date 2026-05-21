from __future__ import annotations

import json
import random
import time
from typing import Any, Dict, List

from loguru import logger
from openai import OpenAI

from activity_sync.settings import Settings


class OpenAIService:
    """
    OpenAI wrapper with retry/backoff.

    This fixes temporary OpenAI errors such as:
    - InternalServerError 500
    - RateLimitError 429
    - APIConnectionError
    - APITimeoutError
    """

    RETRYABLE_ERROR_NAMES = {
        "InternalServerError",
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

        # Simple in-memory cache for the current run.
        # This prevents repeated embedding calls for same activity names.
        self._embedding_cache: Dict[str, List[float]] = {}

    def _is_retryable_error(self, error: Exception) -> bool:
        error_name = error.__class__.__name__

        if error_name in self.RETRYABLE_ERROR_NAMES:
            return True

        status_code = getattr(error, "status_code", None)

        if status_code in {408, 409, 429, 500, 502, 503, 504}:
            return True

        return False

    def _sleep_before_retry(self, attempt: int) -> None:
        # Exponential backoff with jitter.
        # attempt=1 -> around 2s
        # attempt=2 -> around 4s
        # attempt=3 -> around 8s
        # capped to avoid very long waits
        base_delay = min(2 ** attempt, 30)
        jitter = random.uniform(0.25, 1.25)
        delay = base_delay + jitter

        logger.warning(f"Retrying OpenAI request after {delay:.2f} seconds...")
        time.sleep(delay)

    def _run_with_retries(self, operation_name: str, func, max_retries: int = 6):
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                return func()

            except Exception as error:
                last_error = error

                error_name = error.__class__.__name__
                status_code = getattr(error, "status_code", None)

                logger.warning(
                    f"OpenAI {operation_name} failed. "
                    f"Attempt {attempt}/{max_retries}. "
                    f"ErrorType={error_name}, StatusCode={status_code}, Error={error}"
                )

                if not self._is_retryable_error(error):
                    logger.error(
                        f"OpenAI {operation_name} failed with non-retryable error."
                    )
                    raise

                if attempt >= max_retries:
                    break

                self._sleep_before_retry(attempt)

        raise RuntimeError(
            f"OpenAI {operation_name} failed after {max_retries} retries. "
            f"Last error: {last_error}"
        ) from last_error

    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        cleaned_texts = [(text or "").strip() for text in texts]

        if any(not text for text in cleaned_texts):
            raise ValueError("Embedding text cannot be empty.")

        def request_embeddings():
            if self.settings.openai_embedding_model.startswith("text-embedding-3"):
                return self.client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=cleaned_texts,
                    dimensions=self.settings.embedding_dimensions,
                )

            return self.client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=cleaned_texts,
            )

        response = self._run_with_retries(
            operation_name="embeddings.create",
            func=request_embeddings,
            max_retries=6,
        )

        return [item.embedding for item in response.data]

    def create_embedding(self, text: str) -> List[float]:
        cleaned_text = (text or "").strip()

        if not cleaned_text:
            raise ValueError("Embedding text cannot be empty.")

        cache_key = f"{self.settings.openai_embedding_model}|{self.settings.embedding_dimensions}|{cleaned_text}"

        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        embedding = self.create_embeddings([cleaned_text])[0]
        self._embedding_cache[cache_key] = embedding

        return embedding

    def decide_activity_relation(
        self,
        fetched_activity: Dict[str, Any],
        candidate_activity: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = f"""
You are reconciling jurisdiction business activities.

Decide the relationship between the fetched activity and candidate base activity.

Return only valid JSON with this schema:
{{
  "relation": "same_activity" | "spelling_correction" | "different_activity" | "unclear",
  "confidence": number between 0 and 1,
  "reason": "short reason",
  "recommended_status": "Approved" | "Draft" | "Draft-Review"
}}

Definitions:
- same_activity: both names refer to the same business activity.
- spelling_correction: fetched name is the corrected official wording of candidate activity.
- different_activity: they are meaningfully different activities.
- unclear: not enough confidence.

Fetched activity:
{json.dumps(fetched_activity, ensure_ascii=False, indent=2)}

Candidate activity:
{json.dumps(candidate_activity, ensure_ascii=False, indent=2)}
"""

        def request_decision():
            return self.client.chat.completions.create(
                model=self.settings.openai_tiebreaker_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return only valid JSON. Be strict. "
                            "Do not over-match different business activities."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )

        response = self._run_with_retries(
            operation_name="chat.completions.create",
            func=request_decision,
            max_retries=6,
        )

        content = response.choices[0].message.content or "{}"

        try:
            return json.loads(content)

        except json.JSONDecodeError:
            return {
                "relation": "unclear",
                "confidence": 0,
                "reason": "Invalid JSON returned by OpenAI.",
                "recommended_status": "Draft-Review",
                "raw_response": content,
            }