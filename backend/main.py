from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from backend.generator import generateCommand

app = FastAPI()


class QueryRequest(BaseModel):
    query: str


@app.post("/query")
def handleQuery(request: QueryRequest):
    """Accepts a natural language query and returns a generated bash command."""
    generatedCommand = generateCommand(request.query)
    return {"command": generatedCommand}
