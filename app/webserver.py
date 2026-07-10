from fastapi import FastAPI

app = FastAPI(title="Floptropica Bot Health")


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "floptropica-bot"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
