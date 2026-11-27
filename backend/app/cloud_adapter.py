"""
cloud_adapter.py — Optional cloud LLM adapter.

If GEMINI_API_KEY or OPENAI_API_KEY is set (via env or request header),
the adapter enhances feedback. Otherwise returns engine_mode: "local".
"""
from __future__ import annotations

import os
from typing import Optional


def get_engine_info(
    gemini_key: Optional[str] = None,
    openai_key: Optional[str] = None,
) -> dict:
    """
    Determine which engine to use based on available keys.
    Keys can come from env vars or be passed explicitly (e.g. from a header).
    """
    effective_gemini = gemini_key or os.environ.get("GEMINI_API_KEY", "")
    effective_openai = openai_key or os.environ.get("OPENAI_API_KEY", "")

    if effective_gemini:
        return {
            "engine_mode": "gemini",
            "key_status": "key set",
            "model": "gemini-1.5-flash",
        }
    if effective_openai:
        return {
            "engine_mode": "openai",
            "key_status": "key set",
            "model": "gpt-4o-mini",
        }
    return {
        "engine_mode": "local",
        "key_status": "key not set",
        "model": "deterministic-local",
    }


async def enhance_feedback_cloud(
    prompt: str,
    engine_info: dict,
) -> Optional[str]:
    """
    Optionally call cloud LLM to enhance feedback.
    Returns enhanced string or None if local mode / API error.
    """
    if engine_info["engine_mode"] == "local":
        return None

    if engine_info["engine_mode"] == "gemini":
        return await _call_gemini(prompt, engine_info)
    if engine_info["engine_mode"] == "openai":
        return await _call_openai(prompt, engine_info)
    return None


async def _call_gemini(prompt: str, engine_info: dict) -> Optional[str]:
    """Call Gemini API asynchronously."""
    try:
        import httpx  # type: ignore

        api_key = os.environ.get("GEMINI_API_KEY", "")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{engine_info['model']}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 200},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


async def _call_openai(prompt: str, engine_info: dict) -> Optional[str]:
    """Call OpenAI API asynchronously."""
    try:
        import httpx  # type: ignore

        api_key = os.environ.get("OPENAI_API_KEY", "")
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": engine_info["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception:
        return None
