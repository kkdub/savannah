from fastapi import FastAPI
from . import auth

app = FastAPI()

app.include_router(auth.router)


@app.get("/")
def read_root():
    return {"message": "Savannah API"}
