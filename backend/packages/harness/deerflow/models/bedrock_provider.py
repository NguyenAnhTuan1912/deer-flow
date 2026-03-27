import logging
import time
from typing import Any

from botocore.exceptions import ClientError
from langchain_core.messages import BaseMessage
from langchain_aws import ChatBedrockConverse

logger = logging.getLogger(__name__)

RETRYABLE_ERROR_CODES = {"ThrottlingException", "InternalServerException", "ModelErrorException", "ServiceUnavailableException"}
MAX_RETRIES = 3
THINKING_BUDGET_RATIO = 0.8

class BedrockChatModel(ChatBedrockConverse):
  # Custom fields
  enable_prompt_caching: bool = True
  prompt_cache_size: int = 3
  auto_thinking_budget: bool = True
  retry_max_attempts: int = MAX_RETRIES
  _is_oauth: bool = False

  # Access key / Profile
  _aws_access_key_id: str | None = None
  _aws_secret_access_key: str | None = None
  _aws_profile: str = "default"

  model_config = {"arbitrary_types_allowed": True}
  
  def _apply_prompt_caching(self, payload: dict) -> None:
    """Apply ephemeral cache_control to system and recent messages."""
    # Cache system messages
    system = payload.get("system")
    if system and isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                block["cache_control"] = {"type": "ephemeral"}
    elif system and isinstance(system, str):
        payload["system"] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    # Cache recent messages
    messages = payload.get("messages", [])
    cache_start = max(0, len(messages) - self.prompt_cache_size)
    for i in range(cache_start, len(messages)):
        msg = messages[i]
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block["cache_control"] = {"type": "ephemeral"}
        elif isinstance(content, str) and content:
            msg["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

    # Cache the last tool definition
    tools = payload.get("tools", [])
    if tools and isinstance(tools[-1], dict):
        tools[-1]["cache_control"] = {"type": "ephemeral"}

  def _apply_thinking_budget(self, payload: dict) -> None:
    """Auto-allocate thinking budget (80% of max_tokens)."""
    thinking = payload.get("thinking")
    if not thinking or not isinstance(thinking, dict):
        return
    if thinking.get("type") != "enabled":
        return
    if thinking.get("budget_tokens"):
        return

    max_tokens = payload.get("max_tokens", 8192)
    thinking["budget_tokens"] = int(max_tokens * THINKING_BUDGET_RATIO)

  def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> Any:
    """Override with OAuth patching and retry logic."""
    if self._is_oauth:
        self._patch_client_oauth(self._client)

    last_error = None
    for attempt in range(1, self.retry_max_attempts + 1):
        try:
            return super()._generate(messages, stop=stop, **kwargs)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code not in RETRYABLE_ERROR_CODES or attempt >= self.retry_max_attempts:
                raise
            last_error = e
            wait_ms = self._calc_backoff_ms(attempt, e)
            logger.warning(f"Bedrock {error_code}, retrying {attempt}/{self.retry_max_attempts} after {wait_ms}ms")
            time.sleep(wait_ms / 1000)
    raise last_error

  async def _agenerate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> Any:
    """Async override with OAuth patching and retry logic."""
    import asyncio

    if self._is_oauth:
        self._patch_client_oauth(self._async_client)

    last_error = None
    for attempt in range(1, self.retry_max_attempts + 1):
        try:
            return await super()._agenerate(messages, stop=stop, **kwargs)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code not in RETRYABLE_ERROR_CODES or attempt >= self.retry_max_attempts:
                raise
            last_error = e
            wait_ms = self._calc_backoff_ms(attempt, e)
            logger.warning(f"Bedrock {error_code}, retrying {attempt}/{self.retry_max_attempts} after {wait_ms}ms")
            await asyncio.sleep(wait_ms / 1000)
    raise last_error