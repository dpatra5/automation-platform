import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1 import projects, test_cases, runs, run_batches, recordings, integrations
from app.exceptions import RewindError, NotFoundError
from app.db.migrations import upgrade_schema
from app.db.session import engine
import app.models.models  # ensure models are imported for metadata
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure artifacts directory exists before mounting static files
    os.makedirs(settings.artifacts_dir, exist_ok=True)
    # Creates missing tables and backfills columns added since this database
    # was made, so an existing rewind.db keeps working after an upgrade.
    await upgrade_schema(engine)
    yield


app = FastAPI(title="Rewind API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for evidence artifacts (directory created in lifespan)
os.makedirs(settings.artifacts_dir, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=settings.artifacts_dir), name="artifacts")

app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(test_cases.router, prefix="/api/v1/test-cases", tags=["test-cases"])
app.include_router(runs.router, prefix="/api/v1/runs", tags=["runs"])
app.include_router(
    run_batches.router, prefix="/api/v1/run-batches", tags=["run-batches"]
)
app.include_router(recordings.router, prefix="/api/v1/recordings", tags=["recordings"])
app.include_router(
    integrations.router, prefix="/api/v1/integrations", tags=["integrations"]
)


@app.get("/health", tags=["health"])
async def health():
    """Used by the docker-compose healthcheck the frontend waits on."""
    return {"status": "ok"}


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"message": str(exc)})


@app.exception_handler(RewindError)
async def rewind_error_handler(request: Request, exc: RewindError):
    return JSONResponse(status_code=400, content={"message": str(exc)})


@app.get("/", include_in_schema=False)
async def root():
    """Root entry: redirect users to the interactive docs."""
    return RedirectResponse(url="/docs")
