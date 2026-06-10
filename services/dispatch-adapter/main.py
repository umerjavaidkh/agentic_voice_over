from fastapi import FastAPI

app = FastAPI(title="dispatch-adapter")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dispatch-adapter"}
