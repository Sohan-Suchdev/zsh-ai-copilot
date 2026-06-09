from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from backend.generator import generateCommand

app = FastAPI()


class TerminalContext(BaseModel):
    pwd: str
    shell: str


class QueryRequest(BaseModel):
    query: str
    context: TerminalContext
    threadId: str
    osInfo: str = ""
    isQuestion: bool = False


@app.post("/query")
def handleQuery(request: QueryRequest):
    # Accepts a natural language query with terminal context and returns a bash command or explanation.
    try:
        result = generateCommand(
            request.query,
            request.context.model_dump(),
            request.threadId,
            request.osInfo,
            request.isQuestion,
        )
    except ValueError as e:
        # The validator rejected the command — surface the reason to the caller.
        raise HTTPException(status_code=422, detail=str(e))
    return {"command": result, "isQuestion": request.isQuestion}
