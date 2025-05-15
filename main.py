from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello from Render!"}

@app.get("/test")
def test():
    return {"result": "Test route working!"}
