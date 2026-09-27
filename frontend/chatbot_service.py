"""Crafty AI Concierge service for Atelier Form.

Connects to Google Gemini API (gemini-3.8-flash) with Crafty's slow-craft
artisan domain persona and fallback responses for offline/demo scenarios.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CRAFTY_SYSTEM_PROMPT = """
You are "Crafty" (匠心小助手), the warm, poetic, and knowledgeable artisan e-commerce concierge for Atelier Form (an independent handmade ceramics, slow-spun textiles, and bespoke crafts studio marketplace).

Your Persona & Tone:
- You are a passionate apprentice in the maker studio, deeply respectful of slow craftsmanship, human touch, and unhurried labor.
- You speak with sensory details: the warm scent of natural beeswax, the tactile grain of walnut wood, the reduction kiln atmosphere at 1,300°C, the evolving honey patina of Tuscan vegetable-tanned leather, the natural slub of hand-loomed linen.
- You celebrate natural handmade variations: wood grain diversity, fire marks, hand-hammered textures, and natural ash glaze drippings. Explain with warmth why these are not defects, but the unrepeatable heartbeat of the piece.
- You are transparent and honest about artisanal timelines: custom handmade pieces require days or weeks to air-dry, carve, cure, and inspect. Never promise unrealistic expedited rushes.
- When users seek gifts, ask thoughtful questions: who is the recipient, what is the occasion, their aesthetic style, and when is the gift needed?
- When users ask about orders (e.g., #AF-8921), explain the studio status (e.g., currently in the air-drying/secondary firing or hand-burnishing stage).
- When users ask for care, give practical, reassuring instructions (re-oiling wood with food-grade walnut oil, polishing brass, gentle hand-washing ash-glazed ceramics).
- Language: If user asks in Chinese, reply in beautiful, warm, natural Chinese. If in English, reply in warm, refined English.
- Formatting: Use structured Markdown with short paragraphs, clear bullet lists, and gentle emojis (🌿, 🏺, ✍️, 🪵, 🎁). Keep responses conversational, concise, and helpful (about 120-250 words).
"""


def get_gemini_api_key(client_override: str | None = None) -> str:
    """Return the client-provided key if valid, else the server-configured GEMINI_API_KEY."""
    if client_override and client_override.strip().startswith("AIzaSy"):
        return client_override.strip()
    return getattr(settings, "GEMINI_API_KEY", "").strip()


def call_gemini(
    user_prompt: str,
    history: list[dict[str, Any]] | None = None,
    model: str | None = None,
    api_key_override: str | None = None,
) -> dict[str, Any]:
    """Call Google Gemini API generateContent endpoint.

    Returns dict with keys:
      - 'reply': str
      - 'status': 'ok' | 'error'
      - 'model': str
      - 'error': str (optional)
      - 'fallback': bool (optional)
    """
    api_key = get_gemini_api_key(api_key_override)
    if not api_key:
        return {
            "status": "error",
            "error": "No Gemini API key configured. Provide an API key in settings or server .env.",
            "fallback": True,
        }

    target_model = model or getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"

    # Build conversation history
    contents: list[dict[str, Any]] = []
    if history:
        for item in history:
            role = item.get("role", "user")
            text = ""
            parts = item.get("parts")
            if isinstance(parts, list) and parts:
                text = parts[0].get("text", "")
            elif isinstance(item.get("text"), str):
                text = item["text"]
            if text:
                contents.append({
                    "role": "model" if role in ("model", "assistant") else "user",
                    "parts": [{"text": text}],
                })

    contents.append({
        "role": "user",
        "parts": [{"text": user_prompt}],
    })

    payload = {
        "systemInstruction": {
            "parts": [{"text": CRAFTY_SYSTEM_PROMPT.strip()}],
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1000,
        },
    }

    try:
        res = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if not res.ok:
            error_json = res.json() if res.headers.get("Content-Type", "").startswith("application/json") else {}
            msg = error_json.get("error", {}).get("message") or f"HTTP {res.status_code}: {res.reason}"
            logger.warning("Gemini API error: %s", msg)
            return {
                "status": "error",
                "error": msg,
                "model": target_model,
            }

        data = res.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return {
                "status": "error",
                "error": "Gemini returned empty candidate list.",
                "model": target_model,
            }

        reply_parts = candidates[0].get("content", {}).get("parts", [])
        reply_text = reply_parts[0].get("text", "") if reply_parts else ""
        if not reply_text:
            return {
                "status": "error",
                "error": "Gemini returned empty response body.",
                "model": target_model,
            }

        return {
            "status": "ok",
            "reply": reply_text,
            "model": target_model,
        }
    except requests.RequestException as exc:
        logger.exception("Failed to connect to Gemini API")
        return {
            "status": "error",
            "error": f"Network error connecting to Gemini API: {exc}",
            "model": target_model,
        }
