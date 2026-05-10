import os

from langchain_gigachat import GigaChat

from config import (
    GIGA_BASE_URL,
    GIGA_CERT_FILE,
    GIGA_KEY_FILE,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)


def build_gigachat_llm() -> GigaChat:
    """GigaChat adapter (оставляем как было)."""
    return GigaChat(
        base_url=GIGA_BASE_URL,
        model="GigaChat-2-Max",
        temperature=0.6,
        verify_ssl_certs=False,
        timeout=3600,
        cert_file=GIGA_CERT_FILE,
        key_file=GIGA_KEY_FILE,
        profanity_check=False,
    )


def build_openrouter_llm():
    """
    OpenRouter/Qwen (OpenAI-compatible) адаптер.

    Важно: возвращает LangChain chat-model, совместимую с `create_react_agent`.
    """
    api_key = OPENROUTER_API_KEY
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set (see env.example.txt -> .env)")

    base_url = OPENROUTER_BASE_URL.rstrip("/")
    model = OPENROUTER_MODEL

    # Импорт делаем лениво, чтобы gigachat-режим не требовал дополнительных пакетов.
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.6,
    )


def get_llm():
    provider = os.getenv("LLM_PROVIDER", "gigachat").strip().lower()
    if provider == "openrouter":
        return build_openrouter_llm()
    return build_gigachat_llm()


# Экспорт для ServiceManager: агенты используют `llm` напрямую.
llm = get_llm()
