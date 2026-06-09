from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from backend.generator import generateCommand

app = FastAPI()


class QueryRequest(BaseModel):
    query: str


@app.post("/query")
def handleQuery(request: QueryRequest):
    """Accepts a natural language query and returns a validated bash command."""
    try:
        generatedCommand = generateCommand(request.query)
    except ValueError as e:
        # The validator rejected the command — surface the reason to the caller.
        raise HTTPException(status_code=422, detail=str(e))
    return {"command": generatedCommand}
