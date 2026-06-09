#!/usr/bin/env bash
# Installs the AI Copilot backend, configures the API key, and wires the
# shell function into the user's rc files. Safe to re-run — all steps are idempotent.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/venv"
ENV_FILE="${PROJECT_DIR}/.env"
KNOWLEDGE_DIR="${HOME}/.ai-copilot-knowledge"

echo "=== AI Copilot Installer ==="
echo ""

# ── 1. Python 3 ────────────────────────────────────────────────────────────────
echo "[1/5] Checking for Python 3..."
if ! command -v python3 &>/dev/null; then
    echo "  ERROR: python3 not found. Install Python 3.9+ and re-run this script." >&2
    exit 1
fi
echo "  Found: $(python3 --version)"

# ── 2. Virtual environment + dependencies ──────────────────────────────────────
echo "[2/5] Setting up virtual environment..."
if [[ -d "$VENV_DIR" ]]; then
    echo "  venv already exists — skipping creation."
else
    python3 -m venv "$VENV_DIR"
    echo "  Created venv/"
fi

echo "  Installing dependencies from requirements.txt..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${PROJECT_DIR}/requirements.txt"
echo "  Dependencies installed."

# ── 3. API key ─────────────────────────────────────────────────────────────────
echo "[3/5] Configuring API key..."
if [[ -f "$ENV_FILE" ]] && grep -q "^OPENAI_API_KEY=" "$ENV_FILE"; then
    echo "  OPENAI_API_KEY already present in .env — skipping."
else
    printf "  Please enter your OpenAI API Key: "
    read -rs apiKey
    echo ""
    if [[ -z "$apiKey" ]]; then
        echo "  WARNING: No key entered. Add OPENAI_API_KEY=<key> to .env manually before use." >&2
    else
        printf "OPENAI_API_KEY=%s\n" "$apiKey" >> "$ENV_FILE"
        echo "  Saved to .env"
    fi
fi

# ── 4. Knowledge directory ─────────────────────────────────────────────────────
echo "[4/5] Creating knowledge directory..."
mkdir -p "$KNOWLEDGE_DIR"
echo "  ${KNOWLEDGE_DIR} is ready."
echo "  Drop .txt or .md files there to extend the AI's local knowledge base."

# ── 5. Shell configuration ─────────────────────────────────────────────────────
echo "[5/5] Configuring shell..."
SOURCE_LINE="source \"${PROJECT_DIR}/shell/ai.zsh\""

for rcFile in "${HOME}/.zshrc" "${HOME}/.bashrc"; do
    # Create the rc file if it does not exist yet.
    [[ -f "$rcFile" ]] || touch "$rcFile"

    if grep -qF "${PROJECT_DIR}/shell/ai.zsh" "$rcFile"; then
        echo "  $(basename "$rcFile"): already configured — skipping."
    else
        printf "\n# AI Copilot\n%s\n" "$SOURCE_LINE" >> "$rcFile"
        echo "  $(basename "$rcFile"): source line added."
    fi
done

echo ""
echo "=== Installation complete ==="
echo "Open a new terminal, or reload your shell with:  source ~/.zshrc"
