"""Claude via the official Anthropic SDK."""

from __future__ import annotations

import base64

import anthropic

from app.llm.contracts import LLMRequest, ProviderError, ProviderResult
from app.llm.providers.base import validate_output


def _supports_effort(model: str) -> bool:
    # Haiku 4.5 rejects output_config.effort.
    return not model.startswith("claude-haiku")


class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        # Retries are owned by the gateway so that every attempt is traced.
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)

    def complete(self, model: str, req: LLMRequest) -> ProviderResult:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.standard_b64encode(image.data).decode("ascii"),
                },
            }
            for image in req.images
        ]
        content.append({"type": "text", "text": req.text})

        kwargs: dict = {
            "model": model,
            "max_tokens": req.max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if req.system:
            kwargs["system"] = req.system
        if req.effort and _supports_effort(model):
            kwargs["output_config"] = {"effort": req.effort}

        try:
            if req.output_schema is not None:
                kwargs["output_format"] = req.output_schema
            # Streamed so long extractions never hit the non-streaming time limit.
            with self._client.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
                request_id = getattr(stream, "request_id", None) or response.id
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"rate limited: {exc.message}", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"HTTP {exc.status_code}: {exc.message}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"connection error: {exc}", retryable=True) from exc

        if response.stop_reason == "refusal":
            raise ProviderError("model refused the request", retryable=False)
        if response.stop_reason == "max_tokens":
            raise ProviderError("output truncated at max_tokens", retryable=False)

        text = "".join(block.text for block in response.content if block.type == "text")
        parsed = validate_output(req, text, getattr(response, "parsed_output", None))
        usage = response.usage
        return ProviderResult(
            text=text,
            parsed=parsed,
            input_tokens=usage.input_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0),
            output_tokens=usage.output_tokens,
            served_model=response.model,
            request_id=request_id,
        )
