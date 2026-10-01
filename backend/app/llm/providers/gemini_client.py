"""Gemini via the google-genai SDK."""

from __future__ import annotations

from google import genai
from google.genai import errors, types

from app.llm.contracts import LLMRequest, ProviderError, ProviderResult
from app.llm.providers.base import validate_output


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def complete(self, model: str, req: LLMRequest) -> ProviderResult:
        parts = [
            types.Part.from_bytes(data=image.data, mime_type=image.media_type)
            for image in req.images
        ]
        parts.append(types.Part.from_text(text=req.text))

        config = types.GenerateContentConfig(
            system_instruction=req.system,
            max_output_tokens=req.max_tokens,
            # No tools are ever passed; this only silences the SDK's AFC notice.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if req.output_schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = req.output_schema

        try:
            response = self._client.models.generate_content(
                model=model, contents=[types.Content(role="user", parts=parts)], config=config
            )
        except errors.ServerError as exc:
            raise ProviderError(f"HTTP {exc.code}: {exc.message}", retryable=True) from exc
        except errors.ClientError as exc:
            raise ProviderError(
                f"HTTP {exc.code}: {exc.message}", retryable=exc.code == 429
            ) from exc
        except errors.APIError as exc:
            raise ProviderError(f"API error: {exc}", retryable=False) from exc

        candidate = response.candidates[0] if response.candidates else None
        finish = getattr(candidate, "finish_reason", None)
        finish_name = getattr(finish, "name", str(finish) if finish else None)
        if candidate is None:
            raise ProviderError("no candidates returned (prompt blocked)", retryable=False)
        if finish_name == "MAX_TOKENS":
            raise ProviderError("output truncated at max_output_tokens", retryable=False)
        if finish_name not in (None, "STOP"):
            raise ProviderError(f"generation stopped: {finish_name}", retryable=False)

        text = response.text or ""
        parsed = validate_output(req, text, None)
        usage = response.usage_metadata
        return ProviderResult(
            text=text,
            parsed=parsed,
            input_tokens=usage.prompt_token_count or 0,
            # Thinking tokens are billed as output.
            output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0),
            served_model=response.model_version or model,
            request_id=response.response_id,
        )
