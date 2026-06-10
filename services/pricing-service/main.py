from fastapi import FastAPI

app = FastAPI(title="pricing-service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pricing-service"}
