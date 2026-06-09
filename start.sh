echo "🚀 Booting Zsh AI Copilot Backend..."
source venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
