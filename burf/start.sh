#!/bin/bash
set -e
cd "$(dirname "$0")"

PORT=7878
RELOAD=false

usage() {
  echo "Usage: start.sh [--port PORT] [--reload] [--help]"
  echo ""
  echo "  --port PORT   Port to listen on (default: 7878)"
  echo "  --reload      Enable auto-reload on file changes"
  echo "  --help        Show this message"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --port)   PORT="$2"; shift 2 ;;
    --reload) RELOAD=true; shift ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

command -v uvicorn &>/dev/null || { echo "Error: uvicorn not found. Run: pip install uvicorn"; exit 1; }
[[ -f .env ]] || echo "Warning: no .env file found — ANTHROPIC_API_KEY may be missing"

ARGS="--host 0.0.0.0 --port $PORT"
$RELOAD && ARGS="$ARGS --reload"

echo ""
echo "  ╭──────────────────────────────╮"
echo "  │   Burf · Personal AI         │"
echo "  │   http://localhost:$PORT      │"
$RELOAD && echo "  │   reload: on                 │"
echo "  ╰──────────────────────────────╯"
echo ""

exec uvicorn main:app $ARGS
