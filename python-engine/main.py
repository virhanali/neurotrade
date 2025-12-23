"""
NeuroTrade AI - Python Engine
FastAPI service for AI-powered trading signal generation
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(
    title="NeuroTrade AI Engine",
    description="AI-powered crypto trading signal generator",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


class WelcomeResponse(BaseModel):
    message: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="neurotrade-python-engine",
        timestamp=datetime.utcnow(),
    )


@app.get("/", response_model=WelcomeResponse)
async def root():
    """Root endpoint"""
    return WelcomeResponse(
        message="Welcome to NeuroTrade AI Engine",
        version="0.1.0",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
