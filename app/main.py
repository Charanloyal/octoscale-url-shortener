import time
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, BackgroundTasks, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import logger
from app.database import engine, Base
from app.redis import redis_manager
from app.api.v1.endpoints import router as api_v1_router
from app.api.dependencies import get_url_service, rate_limiter
from app.services.url_service import URLService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("app_startup", env=settings.APP_ENV)
    
    # Create tables programmatically on startup (for simplicity and ease of local run/docker compose)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_verified")
    except Exception as e:
        logger.error("database_migration_failed", error=str(e))
        raise e
        
    # Initialize Redis Pool
    redis_manager.initialize()
    
    yield
    
    # Shutdown
    await redis_manager.close()
    await engine.dispose()
    logger.info("app_shutdown")

app = FastAPI(
    title="High-Scale URL Shortener API",
    description="A high-performance URL shortening service designed with OOP patterns, Redis caching, and structured logging.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = None
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=f"{process_time:.4f}s"
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "request_failed",
            method=request.method,
            path=request.url.path,
            error=str(e),
            duration=f"{process_time:.4f}s"
        )
        raise e

# Mount static and templates folders
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Mount API routes
app.include_router(api_v1_router, prefix="/api/v1")

# Route serving UI dashboard
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

async def record_click_background(short_code: str, referrer: Optional[str], user_agent: Optional[str]):
    """Background task to record clicks in a new transaction context to avoid closed-session errors."""
    from app.database import AsyncSessionLocal
    from app.repositories.url_repository import URLRepository
    from app.services.url_service import URLService
    from app.redis import redis_manager

    async with AsyncSessionLocal() as db:
        repo = URLRepository(db)
        redis_client = await redis_manager.get_client()
        service = URLService(repo, redis_client)
        try:
            await service.record_click(short_code, referrer, user_agent)
            await db.commit()
        except Exception as e:
            logger.error("background_click_failed", error=str(e))

# High-Performance Redirect Route (at Root level)
@app.get("/{short_code}", dependencies=[Depends(rate_limiter)])
async def redirect_to_original(
    short_code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    service: URLService = Depends(get_url_service)
):
    """
    Resolve short code and redirect to the original URL.
    Performs Redis-backed lookups and writes analytics in a background task.
    """
    try:
        original_url = await service.resolve_url(short_code)
        
        # Enqueue click recording in a background task to keep redirection response times minimal
        referrer = request.headers.get("referer")
        user_agent = request.headers.get("user-agent")
        background_tasks.add_task(
            record_click_background, 
            short_code=short_code, 
            referrer=referrer, 
            user_agent=user_agent
        )
        
        return RedirectResponse(url=original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    except KeyError:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": f"Short URL code '{short_code}' does not exist."},
            status_code=status.HTTP_404_NOT_FOUND
        )
