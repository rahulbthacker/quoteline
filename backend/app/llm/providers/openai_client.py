"""GPT via the OpenAI SDK (Responses API). Used for the JUDGE role in the eval harness."""

from __future__ import annotations

import base64

import openai

from app.llm.contracts import LLMRequest, ProviderError, ProviderResult
from app.llm.providers.base import validate_output


class OpenAIClient:
    name = "openai"

    def __init__(self, api_key: str) -> None:
        self._client = openai.OpenAI(api_key=api_key, max_retries=0)

    def complete(self, model: str, req: LLMRequest) -> ProviderResult:
        content: list[dict] = [
            {
                "type": "input_image",
                "image_url": f"data:{image.media_type};base64,"
                + base64.standard_b64encode(image.data).decode("ascii"),
            }
            for image in req.images
        ]
        content.append({"type": "input_text", "text": req.text})

        kwargs: dict = {
            "model": model,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": req.max_tokens,
            "store": False,
        }
        if req.system:
            kwargs["instructions"] = req.system
        if req.effort:
            kwargs["reasoning"] = {"effort": "high" if req.effort == "max" else req.effort}

        try:
            if req.output_schema is not None:
                response = self._client.responses.parse(text_format=req.output_schema, **kwargs)
            else:
                response = self._client.responses.create(**kwargs)
        except openai.RateLimitError as exc:
            raise ProviderError(f"rate limited: {exc.message}", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                f"HTTP {exc.status_code}: {exc.message}", retryable=exc.status_code >= 500
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"connection error: {exc}", retryable=True) from exc

        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", "unknown")
            raise ProviderError(f"response incomplete: {reason}", retryable=False)

        text = response.output_text or ""
        parsed = validate_output(req, text, getattr(response, "output_parsed", None))
        usage = response.usage
        return ProviderResult(
            text=text,
            parsed=parsed,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            served_model=response.model,
            request_id=response.id,
        )
