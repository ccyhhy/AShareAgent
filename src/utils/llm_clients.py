import json
import os
import time
from abc import ABC, abstractmethod

import backoff
from google import genai
from openai import OpenAI

from src.utils.logging_config import ERROR_ICON, SUCCESS_ICON, WAIT_ICON, setup_logger

logger = setup_logger("llm_clients")


class LLMClient(ABC):
    @abstractmethod
    def get_completion(self, messages, **kwargs):
        pass


class GeminiClient(LLMClient):
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        if not self.api_key:
            logger.error(f"{ERROR_ICON} 未找到 GEMINI_API_KEY 环境变量")
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"{SUCCESS_ICON} Gemini 客户端初始化成功")

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=5,
        max_time=300,
        giveup=lambda e: "AFC is enabled" not in str(e),
    )
    def generate_content_with_retry(self, contents, config=None):
        try:
            logger.info(f"{WAIT_ICON} 正在调用 Gemini API...")
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            logger.info(f"{SUCCESS_ICON} API 调用成功")
            return response
        except Exception as e:
            error_msg = str(e)
            if "location" in error_msg.lower():
                logger.info("Gemini API 地理位置限制，请切换可用节点后重试")
                logger.error(f"详细错误: {error_msg}")
            elif "AFC is enabled" in error_msg:
                logger.warning(f"{ERROR_ICON} 触发 API 限制，等待重试: {error_msg}")
                time.sleep(5)
            else:
                logger.error(f"{ERROR_ICON} API 调用失败: {error_msg}")
            raise

    def get_completion(self, messages, max_retries=3, initial_retry_delay=1, **kwargs):
        try:
            logger.info(f"{WAIT_ICON} 使用 Gemini 模型: {self.model}")

            for attempt in range(max_retries):
                try:
                    prompt_parts = []
                    system_instruction = None

                    for message in messages:
                        role = message["role"]
                        content = message["content"]
                        if role == "system":
                            system_instruction = content
                        elif role == "user":
                            prompt_parts.append(f"User: {content}")
                        elif role == "assistant":
                            prompt_parts.append(f"Assistant: {content}")

                    config = {}
                    if system_instruction:
                        config["system_instruction"] = system_instruction

                    response = self.generate_content_with_retry(
                        contents="\n".join(prompt_parts),
                        config=config,
                    )

                    if response is None:
                        logger.warning(
                            f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries}: API 返回为空"
                        )
                        if attempt < max_retries - 1:
                            retry_delay = initial_retry_delay * (2**attempt)
                            logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        return None

                    text = getattr(response, "text", None)
                    logger.info(f"{SUCCESS_ICON} 成功获取 Gemini 响应")
                    return text

                except Exception as e:
                    logger.error(
                        f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries} 失败: {str(e)}"
                    )
                    if attempt < max_retries - 1:
                        retry_delay = initial_retry_delay * (2**attempt)
                        logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"{ERROR_ICON} 最终错误: {str(e)}")
                        return None
        except Exception as e:
            logger.error(f"{ERROR_ICON} get_completion 发生错误: {str(e)}")
            return None


class OpenAICompatibleClient(LLMClient):
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_COMPATIBLE_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_COMPATIBLE_BASE_URL")
        self.model = model or os.getenv("OPENAI_COMPATIBLE_MODEL")

        if not self.api_key:
            logger.error(f"{ERROR_ICON} 未找到 OPENAI_COMPATIBLE_API_KEY 环境变量")
            raise ValueError(
                "OPENAI_COMPATIBLE_API_KEY not found in environment variables"
            )
        if not self.base_url:
            logger.error(f"{ERROR_ICON} 未找到 OPENAI_COMPATIBLE_BASE_URL 环境变量")
            raise ValueError(
                "OPENAI_COMPATIBLE_BASE_URL not found in environment variables"
            )
        if not self.model:
            logger.error(f"{ERROR_ICON} 未找到 OPENAI_COMPATIBLE_MODEL 环境变量")
            raise ValueError(
                "OPENAI_COMPATIBLE_MODEL not found in environment variables"
            )

        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        logger.info(f"{SUCCESS_ICON} OpenAI Compatible 客户端初始化成功")

    @backoff.on_exception(backoff.expo, Exception, max_tries=5, max_time=300)
    def call_api_with_retry(self, messages, stream=False):
        try:
            logger.info(f"{WAIT_ICON} 正在调用 OpenAI Compatible API...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream,
            )
            logger.info(f"{SUCCESS_ICON} API 调用成功")
            return response
        except Exception as e:
            logger.error(f"{ERROR_ICON} API 调用失败: {str(e)}")
            raise

    @staticmethod
    def _extract_content_from_response(response):
        # 标准 OpenAI SDK 对象
        if hasattr(response, "choices"):
            return response.choices[0].message.content

        # 某些兼容网关会把流式响应拼成字符串返回
        if isinstance(response, str):
            content_parts = []
            reasoning_parts = []

            def _consume_chunk(obj):
                # chat.completions chunk format
                choices = obj.get("choices") or []
                if choices:
                    choice = choices[0] or {}
                    delta = choice.get("delta") or {}
                    if isinstance(delta, dict):
                        delta_content = delta.get("content")
                        if isinstance(delta_content, str) and delta_content:
                            content_parts.append(delta_content)

                        delta_reasoning = delta.get("reasoning_content")
                        if isinstance(delta_reasoning, str) and delta_reasoning:
                            reasoning_parts.append(delta_reasoning)

                    message = choice.get("message") or {}
                    if isinstance(message, dict):
                        message_content = message.get("content")
                        if isinstance(message_content, str) and message_content:
                            content_parts.append(message_content)
                    return

                # responses event-stream format
                event_type = obj.get("type")
                if event_type == "response.output_text.delta":
                    delta = obj.get("delta")
                    if isinstance(delta, str) and delta:
                        content_parts.append(delta)
                elif event_type == "response.completed":
                    response_obj = obj.get("response") or {}
                    output_items = response_obj.get("output") or []
                    for item in output_items:
                        parts = item.get("content") or []
                        for part in parts:
                            if part.get("type") == "output_text":
                                text = part.get("text")
                                if isinstance(text, str) and text:
                                    content_parts.append(text)

            for line in response.splitlines():
                line = line.strip()
                if not line:
                    continue

                payload = line
                if line.startswith("data:"):
                    payload = line[5:].strip()
                elif not line.startswith("{"):
                    continue

                if payload in {"", "[DONE]"}:
                    continue

                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                _consume_chunk(chunk)

            if content_parts:
                return "".join(content_parts)
            if reasoning_parts:
                return "".join(reasoning_parts)

            return response

        raise TypeError(f"Unsupported response type: {type(response).__name__}")

    def get_completion(self, messages, max_retries=3, initial_retry_delay=1, **kwargs):
        try:
            logger.info(f"{WAIT_ICON} 使用 OpenAI Compatible 模型: {self.model}")
            for attempt in range(max_retries):
                try:
                    response = self.call_api_with_retry(messages)
                    if response is None:
                        logger.warning(
                            f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries}: API 返回为空"
                        )
                        if attempt < max_retries - 1:
                            retry_delay = initial_retry_delay * (2**attempt)
                            logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        return None

                    content = self._extract_content_from_response(response)
                    if content is None:
                        return None
                    logger.info(f"{SUCCESS_ICON} 成功获取 OpenAI Compatible 响应")
                    return content
                except Exception as e:
                    logger.error(
                        f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries} 失败: {str(e)}"
                    )
                    if attempt < max_retries - 1:
                        retry_delay = initial_retry_delay * (2**attempt)
                        logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"{ERROR_ICON} 最终错误: {str(e)}")
                        return None
        except Exception as e:
            logger.error(f"{ERROR_ICON} get_completion 发生错误: {str(e)}")
            return None


class LLMClientFactory:
    @staticmethod
    def create_client(client_type="auto", **kwargs):
        if client_type == "auto":
            if (
                kwargs.get("api_key")
                and kwargs.get("base_url")
                and kwargs.get("model")
            ) or (
                os.getenv("OPENAI_COMPATIBLE_API_KEY")
                and os.getenv("OPENAI_COMPATIBLE_BASE_URL")
                and os.getenv("OPENAI_COMPATIBLE_MODEL")
            ):
                client_type = "openai_compatible"
                logger.info(f"{WAIT_ICON} 自动选择 OpenAI Compatible API")
            else:
                client_type = "gemini"
                logger.info(f"{WAIT_ICON} 自动选择 Gemini API")

        if client_type == "gemini":
            return GeminiClient(api_key=kwargs.get("api_key"), model=kwargs.get("model"))
        if client_type == "openai_compatible":
            return OpenAICompatibleClient(
                api_key=kwargs.get("api_key"),
                base_url=kwargs.get("base_url"),
                model=kwargs.get("model"),
            )
        raise ValueError(f"不支持的客户端类型: {client_type}")


def get_chat_completion(
    messages,
    model=None,
    max_retries=3,
    initial_retry_delay=1,
    client_type="auto",
    api_key=None,
    base_url=None,
):
    try:
        client = LLMClientFactory.create_client(
            client_type=client_type,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        return client.get_completion(
            messages=messages,
            max_retries=max_retries,
            initial_retry_delay=initial_retry_delay,
        )
    except Exception as e:
        logger.error(f"{ERROR_ICON} get_chat_completion 发生错误: {str(e)}")
        return None
