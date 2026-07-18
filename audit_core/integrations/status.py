from __future__ import annotations

import os


def integration_status() -> dict[str, dict[str, str | bool]]:
    cognee_url = os.getenv("COGNEE_API_URL", "").strip()
    cognee_key = os.getenv("COGNEE_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    return {
        "cognee": {
            "configured": bool(cognee_url and cognee_key),
            "endpoint": cognee_url if cognee_url else "not configured",
            "purpose": "semantic graph and cross-document investigation",
        },
        "openai": {
            "configured": bool(openai_key),
            "extraction_model": os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-5-nano"),
            "reasoning_model": os.getenv("OPENAI_REASONING_MODEL", "gpt-5.4-mini"),
            "purpose": "ambiguous extraction and grounded explanations",
        },
    }

