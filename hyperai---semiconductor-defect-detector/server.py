from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent_logic
from fastapi.middleware.cors import CORSMiddleware
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DefectDetectorServer")

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    id: str
    img_url: str

class AnalyzeResponse(BaseModel):
    id: str
    label: int
    confidence: float
    status: str
    logs: list[str]
    details: dict = {}

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(req: AnalyzeRequest):
    logger.info(f"Received request for {req.id}: {req.img_url}")
    try:
        # Run the LangChain logic
        result = run_agent_logic(req.img_url)
        
        return AnalyzeResponse(
            id=req.id,
            label=result.get("label", 0),
            confidence=result.get("confidence", 0.0),
            status=result.get("status", "completed"),
            logs=result.get("logs", []),
            details=result.get("details", {})
        )
    except Exception as e:
        logger.error(f"Error processing {req.id}: {e}")
        return AnalyzeResponse(
            id=req.id,
            label=0,
            confidence=0.0,
            status="error",
            logs=[str(e)]
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
