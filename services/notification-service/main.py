from fastapi import FastAPI

app = FastAPI(title="notification-service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification-service"}
