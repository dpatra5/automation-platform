"""
Main application entry point for Jira SprintGuard.
FastAPI server with CORS support.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .config import API_HOST, API_PORT, DEBUG_MODE
from .routes import router


app = FastAPI(
    title="Jira SprintGuard",
    description="LLM-powered problem statement analysis and Jira story generation",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Jira SprintGuard API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "frontend": "http://localhost:3000"
    }


if __name__ == "__main__":
    print(f"Starting Jira SprintGuard API server on http://{API_HOST}:{API_PORT}")
    print(f"API documentation available at http://localhost:{API_PORT}/api/docs")
    print(f"Frontend should run on http://localhost:3000")
    uvicorn.run(
        "backend.sprintguard.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG_MODE,
    )
