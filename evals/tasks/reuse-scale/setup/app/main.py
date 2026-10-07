from fastapi import Depends, FastAPI, Header, HTTPException

from app.cache import cached_report

app = FastAPI(title="reports-api")


def api_key(x_api_key: str = Header(...)) -> str:
    if not x_api_key.startswith("key_"):
        raise HTTPException(status_code=401, detail="sai API key")
    return x_api_key


@app.get("/reports/{report_id}")
def get_report(report_id: int, key: str = Depends(api_key)):
    return cached_report(report_id)
