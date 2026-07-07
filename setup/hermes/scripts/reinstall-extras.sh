#!/bin/bash
# Re-assert venv packages that are NOT in Hermes' lockfile.
# You do NOT need this after a normal `hermes update` (that install is additive and
# preserves them). Run it ONLY after a venv REBUILD — i.e. if you re-run
# setup-hermes.sh or scripts/install.sh, which do `uv sync --locked` and prune extras.
set -e
PY=/home/sinep/.hermes/hermes-agent/venv/bin/python
/home/sinep/.local/bin/uv pip install --python "$PY" \
  langfuse==4.13.0 ollama==0.6.2 mem0ai==2.0.11 qdrant-client==1.18.0 fastembed
echo "Re-asserted langfuse + ollama + mem0ai + qdrant-client. Now: hermes gateway restart"
