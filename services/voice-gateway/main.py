from fastapi import FastAPI

app = FastAPI(title="voice-gateway")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-gateway"}
