from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/eval")
async def evaluate(request: Request):
    data = await request.json()
    print("Evaluation request received:", data)
    return {"status": "success", "message": "Evaluation received"}