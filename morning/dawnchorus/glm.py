"""Minimal GLM (z.ai) chat client, JSON mode.

Keys: GLM_API_KEY and GLM_BASE_URL from the environment, else from
~/.hermes/.env (where greg keeps them). Never logged.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path.home() / ".hermes" / ".env"


class QuotaError(Exception):
    """Rate limit or usage-window quota: stop the run, don't retry."""


def env(name):
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"{name} not set (environment or {ENV_FILE})")


def chat_json(model, system, user, temperature=0.3, timeout=120):
    """One call → parsed JSON object. Raises QuotaError, RuntimeError or ValueError."""
    body = {"model": model, "temperature": temperature, "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(
        env("GLM_BASE_URL").rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {env('GLM_API_KEY')}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.loads(r.read())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        # z.ai: 429 for rate and usage limits (codes 1302/1308/1310 in the body)
        if e.code == 429 or re.search(r'"code"\s*:\s*"?13(?:02|08|10)\b|usage limit|quota', detail, re.I):
            raise QuotaError(f"HTTP {e.code}: {detail}") from e
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in reply: {text[:200]}")
    return json.loads(m.group(0))
