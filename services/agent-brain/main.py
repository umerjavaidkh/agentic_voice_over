from fastapi import FastAPI

app = FastAPI(title="agent-brain")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent-brain"}
