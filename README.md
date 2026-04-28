# Fairlytics Prototype (Full Copy)

This is a separate hackathon-friendly full project copy with:

- `backend/`: FastAPI multi-agent fairness audit service
- `frontend/`: simple UI for dataset/model upload and results

## UX supported

1. User uploads dataset (CSV) or model file.
2. System runs agents to detect different types of bias.
3. Orchestrator merges agent findings.
4. Explanation agent returns simple human language summary.
5. System suggests mitigation actions.

## Run backend

```bash
cd fairlytics_prototype/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Run frontend

Serve static files from `fairlytics_prototype/frontend` using any static server.

Example (Python):

```bash
cd fairlytics_prototype/frontend
python -m http.server 5173
```

Then open `http://localhost:5173`.

## Notes

- If `ANTHROPIC_API_KEY` is set, explanation generation will attempt LLM output.
- Without the key, explanation falls back to rule-based plain-language messaging.
