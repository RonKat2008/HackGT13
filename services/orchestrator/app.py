from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
