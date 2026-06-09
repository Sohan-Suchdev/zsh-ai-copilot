from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class QueryRequest(BaseModel):
    query: str


@app.post("/query")
def handle_query(request: QueryRequest):
    return {"command": "echo 'AI Copilot is alive!'"}
