"""Local Reader — keyless web_extract backend for Hermes.

Fills the gap left by search-only providers (brave-free / ddgs / searxng):
those do web_search fine but cannot extract full page content. This provider
does extraction with NO API key and NO self-hosting, using a two-stage
strategy per URL:

  1. LOCAL & PRIVATE first — fetch the static HTML and extract clean
     main-content markdown with ``trafilatura`` (best-in-class boilerplate
     removal, F1 ~0.91). The URL and page content never leave the machine.
     Requires ``trafilatura`` in Hermes' venv (optional — see stage 2).

  2. FALLBACK — if trafilatura is not installed, errors, or returns too little
     (typically a JavaScript/SPA page that ships an empty HTML shell), call
     Jina AI Reader (``https://r.jina.ai/<URL>``). It is keyless, renders JS
     server-side in a real browser, and returns clean markdown. The target
     URL is proxied through Jina's servers — set ``LOCAL_READER_DISABLE_JINA=1``
     to stay 100% local and never fall back.

Capability: extract only. Pair with brave-free / ddgs / searxng for web_search.

Config (config.yaml)::

    web:
      search_backend: brave-free     # keep your existing search
      extract_backend: local-reader  # route web_extract here

Env (ALL optional)::

    JINA_API_KEY=...               # optional — raises Jina rate limit
                                   #   (keyless ~20 RPM -> ~500 RPM keyed)
    LOCAL_READER_DISABLE_JINA=1    # never fall back to Jina (fully local only)
    LOCAL_READER_MIN_CHARS=200     # trafilatura output below this = "thin" -> fall back
    JINA_READER_BASE=...           # override https://r.jina.ai

Enable::

    hermes plugins enable web/local_reader
    # then set web.extract_backend: local-reader  and restart Hermes
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_JINA_DEFAULT_BASE = "https://r.jina.ai"


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _min_chars() -> int:
    try:
        return max(0, int(os.getenv("LOCAL_READER_MIN_CHARS", "200")))
    except (TypeError, ValueError):
        return 200


class LocalReaderProvider(WebSearchProvider):
    """Keyless extract provider: trafilatura (local) + Jina Reader fallback."""

    @property
    def name(self) -> str:
        return "local-reader"

    @property
    def display_name(self) -> str:
        return "Local Reader (trafilatura + Jina fallback)"

    def is_available(self) -> bool:
        # Keyless Jina fallback is always reachable, and trafilatura is local;
        # per-URL failures are surfaced as {"error": ...} rather than making
        # the whole backend "unavailable".
        return True

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    # -- stage 1: local, private -------------------------------------------
    def _extract_trafilatura(self, url: str) -> Dict[str, Any] | None:
        """Return a result dict from local trafilatura extraction, or None to fall back."""
        try:
            import trafilatura  # type: ignore
        except Exception:  # noqa: BLE001 — not installed
            return None

        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            content = trafilatura.extract(
                downloaded,
                url=url,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            ) or ""
            if len(content.strip()) < _min_chars():
                # Likely a JS shell or a page trafilatura can't parse — fall back.
                return None
            title = ""
            try:
                meta = trafilatura.extract_metadata(downloaded)
                title = (getattr(meta, "title", "") or "") if meta else ""
            except Exception:  # noqa: BLE001
                pass
            logger.info("Local Reader: trafilatura extracted %s (%d chars)", url, len(content))
            return {
                "url": url,
                "title": title,
                "content": content,
                "raw_content": content,
                "metadata": {"sourceURL": url, "title": title, "engine": "trafilatura"},
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local Reader: trafilatura failed for %s: %s", url, exc)
            return None

    # -- stage 2: keyless hosted fallback ----------------------------------
    def _extract_jina(self, url: str) -> Dict[str, Any]:
        import httpx

        base = os.getenv("JINA_READER_BASE", _JINA_DEFAULT_BASE).strip().rstrip("/")
        headers = {"Accept": "application/json", "X-Return-Format": "markdown"}
        key = os.getenv("JINA_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                resp = client.get(f"{base}/{url}", headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            title = str(data.get("title", "") or "")
            content = str(data.get("content", "") or data.get("text", "") or "")
            logger.info("Local Reader: Jina extracted %s (%d chars)", url, len(content))
            return {
                "url": str(data.get("url", url) or url),
                "title": title,
                "content": content,
                "raw_content": content,
                "metadata": {"sourceURL": url, "title": title, "engine": "jina-reader"},
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local Reader: Jina failed for %s: %s", url, exc)
            return {
                "url": url, "title": "", "content": "", "raw_content": "",
                "error": f"Local Reader extract failed (trafilatura + Jina): {exc}",
            }

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        try:
            from tools.interrupt import is_interrupted
        except Exception:  # noqa: BLE001
            def is_interrupted() -> bool:  # type: ignore
                return False

        disable_jina = _env_flag("LOCAL_READER_DISABLE_JINA")
        results: List[Dict[str, Any]] = []
        for url in urls:
            if is_interrupted():
                results.append({"url": url, "title": "", "content": "",
                                "raw_content": "", "error": "Interrupted"})
                continue
            local = self._extract_trafilatura(url)
            if local is not None:
                results.append(local)
                continue
            if disable_jina:
                results.append({
                    "url": url, "title": "", "content": "", "raw_content": "",
                    "error": ("Local-only mode (LOCAL_READER_DISABLE_JINA=1): trafilatura "
                              "could not extract this page. Install trafilatura "
                              "(`venv/bin/pip install trafilatura`) or allow the Jina fallback."),
                })
                continue
            results.append(self._extract_jina(url))
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Local Reader (trafilatura + Jina fallback)",
            "badge": "free",
            "tag": "Keyless extract: local trafilatura first, Jina Reader fallback for JS pages.",
            "env_vars": [
                {"key": "JINA_API_KEY",
                 "prompt": "Jina API key (OPTIONAL — keyless works; a key raises the rate limit)",
                 "url": "https://jina.ai/reader"},
            ],
        }


def register(ctx) -> None:
    """Register the Local Reader provider with Hermes' plugin context."""
    ctx.register_web_search_provider(LocalReaderProvider())
