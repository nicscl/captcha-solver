from fastapi import FastAPI, File, HTTPException, UploadFile

from solver import solve

app = FastAPI(title="Captcha Solver")


@app.post("/solve")
async def solve_endpoint(file: UploadFile = File(...)):
    image_bytes = await file.read()
    try:
        text = solve(image_bytes, file.content_type or "image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"solution": text}
