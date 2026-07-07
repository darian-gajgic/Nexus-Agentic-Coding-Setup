"""Enhanced Brave web backend — OVERRIDES the built-in ``brave-free`` provider.

Why it registers under the name ``brave-free``: Hermes' ``web_search`` /
``web_extract`` dispatch resolves the active backend through a legacy allowlist
(``tools.web_tools._is_backend_available``) that only recognizes a fixed set of
names (exa, parallel, firecrawl, tavily, searxng, brave-free, ddgs, xai). A
custom name is silently ignored and the tool falls back to ``web.backend``. So a
custom-named provider never actually gets used. Registering under ``brave-free``
(user plugins override bundled ones by name) makes this the provider Hermes
actually calls when ``web.backend: brave-free`` — i.e. it upgrades brave-free
in place, and survives Hermes updates (no core edits).

Behavior:

* ``web_search`` → Brave ``/res/v1/llm/context`` — real extracted page content
  (~4k tokens/result), not one-line snippets. Falls back to Brave's classic
  ``/res/v1/web/search`` (with ``extra_snippets``) if that endpoint errors.
* ``web_extract`` → LOCAL full-page reader: ``trafilatura`` (fully local,
  private, whole page) then Jina AI Reader (``https://r.jina.ai``, keyless,
  renders JS). Returns the COMPLETE page — used when the agent decides the
  search content is not enough.

Every Brave request is sent with ``safesearch=off`` (override BRAVE_SAFESEARCH).

Env::

    BRAVE_SEARCH_API_KEY=...              # required for search
    BRAVE_SAFESEARCH=off                  # off | moderate | strict (default off)
    BRAVE_CONTEXT_TOKENS_PER_URL=4096     # 512-8192 (Brave default 4096)
    BRAVE_CONTEXT_MAX_CHARS=8000          # per-result search-content cap
    JINA_API_KEY=...                      # optional, raises Jina rate limit
    LOCAL_READER_DISABLE_JINA=1           # keep extract 100% local (no Jina)
    LOCAL_READER_MIN_CHARS=200            # trafilatura output below this = "thin"
    JINA_READER_BASE=...                  # override https://r.jina.ai
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_LLM_CONTEXT = "https://api.search.brave.com/res/v1/llm/context"
_WEB_SEARCH = "https://api.search.brave.com/res/v1/web/search"
_JINA_DEFAULT_BASE = "https://r.jina.ai"


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(os.getenv(name, str(default))), hi))
    except (TypeError, ValueError):
        return default


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safesearch() -> str:
    val = os.getenv("BRAVE_SAFESEARCH", "off").strip().lower()
    return val if val in {"off", "moderate", "strict"} else "off"


def _join_snippets(snippets: List[Any], max_chars: int) -> str:
    joined = "\n".join(
        s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
        for s in (snippets or [])
    ).strip()
    if len(joined) > max_chars:
        joined = joined[:max_chars] + "…[truncated — call web_extract on this URL for the full page]"
    return joined


# --- local full-page readers (used by web_extract) ------------------------
def _extract_trafilatura(url: str) -> Optional[Dict[str, Any]]:
    try:
        import trafilatura  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        content = trafilatura.extract(
            downloaded, url=url, output_format="markdown",
            include_comments=False, include_tables=True, favor_recall=True,
        ) or ""
        if len(content.strip()) < _int_env("LOCAL_READER_MIN_CHARS", 200, 0, 100_000):
            return None
        title = ""
        try:
            meta = trafilatura.extract_metadata(downloaded)
            title = (getattr(meta, "title", "") or "") if meta else ""
        except Exception:  # noqa: BLE001
            pass
        logger.info("brave-free(extract): trafilatura got %s (%d chars)", url, len(content))
        return {"url": url, "title": title, "content": content, "raw_content": content,
                "metadata": {"sourceURL": url, "title": title, "engine": "trafilatura"}}
    except Exception as exc:  # noqa: BLE001
        logger.warning("brave-free(extract): trafilatura failed for %s: %s", url, exc)
        return None


def _extract_jina(url: str) -> Dict[str, Any]:
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
        logger.info("brave-free(extract): Jina got %s (%d chars)", url, len(content))
        return {"url": str(data.get("url", url) or url), "title": title,
                "content": content, "raw_content": content,
                "metadata": {"sourceURL": url, "title": title, "engine": "jina-reader"}}
    except Exception as exc:  # noqa: BLE001
        logger.warning("brave-free(extract): Jina failed for %s: %s", url, exc)
        return {"url": url, "title": "", "content": "", "raw_content": "",
                "error": f"extract failed (trafilatura + Jina): {exc}"}


def _local_extract(url: str) -> Dict[str, Any]:
    local = _extract_trafilatura(url)
    if local is not None:
        return local
    if _env_flag("LOCAL_READER_DISABLE_JINA"):
        return {"url": url, "title": "", "content": "", "raw_content": "",
                "error": ("Local-only mode (LOCAL_READER_DISABLE_JINA=1): trafilatura could not "
                          "extract this page. Allow the Jina fallback or try another URL.")}
    return _extract_jina(url)


class BraveEnhancedProvider(WebSearchProvider):
    """Content-rich Brave search + local full-page extract (overrides brave-free)."""

    @property
    def name(self) -> str:
        # Overrides the bundled brave-free so the legacy dispatch actually uses it.
        return "brave-free"

    @property
    def display_name(self) -> str:
        return "Brave (content-rich search + local full-page extract)"

    def is_available(self) -> bool:
        return bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    # -- search: Brave LLM Context (content-rich), plain-Brave fallback ----
    def _brave_context_items(self, query: str, count: int, tokens_per_url: int) -> List[Dict[str, Any]]:
        import httpx
        api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            raise ValueError("BRAVE_SEARCH_API_KEY is not set")
        resp = httpx.get(
            _LLM_CONTEXT,
            params={"q": query, "count": count, "maximum_number_of_urls": count,
                    "maximum_number_of_tokens_per_url": tokens_per_url,
                    "safesearch": _safesearch()},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        grounding = resp.json().get("grounding") or {}
        return grounding.get("generic", []) if isinstance(grounding, dict) else []

    def _brave_web_search(self, query: str, limit: int) -> Dict[str, Any]:
        import httpx
        api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            return {"success": False, "error": "BRAVE_SEARCH_API_KEY is not set"}
        try:
            resp = httpx.get(
                _WEB_SEARCH,
                params={"q": query, "count": max(1, min(limit, 20)),
                        "extra_snippets": "true", "safesearch": _safesearch()},
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            results = (resp.json().get("web") or {}).get("results", []) or []
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Brave web search failed: {exc}"}
        web = []
        for i, r in enumerate(results[:limit]):
            desc = str(r.get("description", "") or "")
            extra = r.get("extra_snippets") or []
            if extra:
                desc = desc + "\n" + "\n".join(str(x) for x in extra)
            web.append({"title": str(r.get("title", "") or ""), "url": str(r.get("url", "") or ""),
                        "description": desc.strip(), "position": i + 1})
        logger.info("brave-free(search): plain web/search fallback, %d results", len(web))
        return {"success": True, "data": {"web": web}}

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        count = max(1, min(int(limit), 20))
        tokens_per_url = _int_env("BRAVE_CONTEXT_TOKENS_PER_URL", 4096, 512, 8192)
        max_chars = _int_env("BRAVE_CONTEXT_MAX_CHARS", 8000, 500, 200_000)
        try:
            items = self._brave_context_items(query, count, tokens_per_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("brave-free(search): LLM Context failed (%s); using web/search", exc)
            return self._brave_web_search(query, limit)
        if not items:
            return self._brave_web_search(query, limit)
        web = [{
            "title": str(it.get("title", "") or ""),
            "url": str(it.get("url", "") or ""),
            "description": _join_snippets(it.get("snippets"), max_chars),
            "position": i + 1,
        } for i, it in enumerate(items[:count])]
        logger.info("brave-free(search): LLM Context '%s': %d content-rich results (~%d chars each)",
                    query, len(web), (len(web[0]["description"]) if web else 0))
        return {"success": True, "data": {"web": web}}

    # -- extract: local full page -----------------------------------------
    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        try:
            from tools.interrupt import is_interrupted
        except Exception:  # noqa: BLE001
            def is_interrupted() -> bool:  # type: ignore
                return False
        results: List[Dict[str, Any]] = []
        for url in urls:
            if is_interrupted():
                results.append({"url": url, "title": "", "content": "",
                                "raw_content": "", "error": "Interrupted"})
                continue
            results.append(_local_extract(url))
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Brave (content-rich + local extract)",
            "badge": "paid",
            "tag": "Brave LLM-Context search + local full-page extract. Overrides brave-free.",
            "env_vars": [
                {"key": "BRAVE_SEARCH_API_KEY",
                 "prompt": "Brave Search API key (paid Search plan for LLM Context)",
                 "url": "https://api-dashboard.search.brave.com/"},
            ],
        }


# --------------------------------------------------------------------------- #
# Tool-description guidance — put the "how to use these" instructions ON the
# web_search / web_extract tool definitions the model receives (the most robust
# place: always sent with the tool, can't be skipped, survives Hermes updates
# because this plugin lives outside the repo). Applied at load by mutating the
# registered schema dict; registry.get_definitions() reads entry.schema live.
# --------------------------------------------------------------------------- #
_WEB_SEARCH_GUIDANCE = (
    " NOTE: this backend returns REAL extracted page content in each result's "
    "'description' field (up to ~4000 tokens per result), not a one-line snippet "
    "— usually enough to answer directly, so read the result content before "
    "deciding to extract. SafeSearch is off. If a result's content is cut off "
    "(marked '…[truncated]') or you need a page's complete text, call web_extract "
    "on that URL."
)
_WEB_EXTRACT_GUIDANCE = (
    " Prefer this when a web_search result is truncated or you need the COMPLETE "
    "text/tables/code of a specific page: it fetches the whole page locally "
    "(private), with no source-side length cap."
)


def _patch_tool_descriptions() -> None:
    """Append usage guidance to the web_search / web_extract tool descriptions."""
    try:
        import tools.web_tools  # noqa: F401 — ensure core web tools are registered
        from tools.registry import registry
    except Exception as exc:  # noqa: BLE001
        logger.debug("brave-free: could not import registry to patch tool docs: %s", exc)
        return
    for tool_name, guidance in (("web_search", _WEB_SEARCH_GUIDANCE),
                                ("web_extract", _WEB_EXTRACT_GUIDANCE)):
        try:
            schema = registry.get_schema(tool_name)  # mutable ref to entry.schema
            if not schema:
                continue
            desc = schema.get("description", "")
            if guidance.strip()[:32] not in desc:  # idempotent
                schema["description"] = desc.rstrip() + guidance
                logger.info("brave-free: patched %s tool description with usage guidance", tool_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("brave-free: failed to patch %s description: %s", tool_name, exc)


def register(ctx) -> None:
    """Register the enhanced provider under the name 'brave-free' (overrides bundled)
    and put web-tool usage guidance directly on the tool definitions."""
    ctx.register_web_search_provider(BraveEnhancedProvider())
    _patch_tool_descriptions()
