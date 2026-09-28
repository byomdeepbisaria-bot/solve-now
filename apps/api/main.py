from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from contextlib import asynccontextmanager
import time
import uuid
import logging
import os

from core.config import settings
from core.database import get_db, engine
from core.redis import init_redis

# â”€â”€ Structured JSON Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from pythonjsonlogger import jsonlogger

log_handler = logging.StreamHandler()
if settings.is_production:
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "severity"},
    )
    log_handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[log_handler])
logger = logging.getLogger("solvenow.api")

# â”€â”€ Sentry Error Tracking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,  # Never send PII to Sentry
    )
    logger.info("Sentry error tracking initialized")



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up SolveNow API...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection established.")

        # Run database migrations automatically on startup
        try:
            from alembic.config import Config
            from alembic import command
            alembic_ini_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
            if os.path.exists(alembic_ini_path):
                alembic_cfg = Config(alembic_ini_path)
                script_dir = os.path.join(os.path.dirname(__file__), "migrations")
                alembic_cfg.set_main_option("script_location", script_dir)
                command.upgrade(alembic_cfg, "head")
                logger.info("Database migrations applied successfully.")
            else:
                logger.warning(f"alembic.ini not found at {alembic_ini_path}")
        except Exception as me:
            logger.error(f"Failed to apply database migrations on startup: {me}")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")

    try:
        await init_redis()
        logger.info("Async Redis connection established.")
    except Exception as e:
        logger.error(f"Failed to connect to Async Redis: {e}")
        
    yield
    pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if not settings.is_production else None,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)


# Prometheus metrics endpoint (internal use only â€” restrict at reverse proxy)


# Secure Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Strict CORS handling using CORS_ORIGINS
if settings.is_production and not settings.CORS_ORIGINS:
    raise ValueError(
        "CORS_ORIGINS must be set in production. "
        "CORS cannot default to localhost in a production environment."
    )

_cors_origins = []
if settings.CORS_ORIGINS:
    _cors_origins = [origin.strip().rstrip("/") for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

if not settings.is_production and not _cors_origins:
    _cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Body size limit middleware
class LimitUploadSize(BaseHTTPMiddleware):
    def __init__(self, app, max_upload_size: int = 10 * 1024 * 1024): # 10MB
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_upload_size:
                return Response("Payload too large", status_code=413)
        return await call_next(request)

app.add_middleware(LimitUploadSize, max_upload_size=10 * 1024 * 1024)

# Request ID Middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.correlation_id = request_id
        return record

    logging.setLogRecordFactory(record_factory)

    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        logger.error(f"Unhandled error: {exc}", exc_info=True)
        origin = request.headers.get("origin", "")
        resp = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id}
        )
        # Ensure CORS headers are present even on unhandled 500s
        if origin in _cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Vary"] = "Origin"
        return resp

@app.get("/health", tags=["monitoring"])
def health_check():
    """Liveness probe â€” always returns 200 if the process is alive."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}

@app.get("/ready", tags=["monitoring"])
def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe â€” checks database connectivity before accepting traffic."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "disconnected"})

# Expose Prometheus metrics at /metrics (restrict via nginx/Cloudflare to internal only)

from api.v1 import auth, problems, solutions, rooms, ws, files, knowledge, users, experts, notifications, moderation, admin, ai

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(experts.router, prefix=f"{settings.API_V1_STR}/experts", tags=["experts"])
app.include_router(notifications.router, prefix=f"{settings.API_V1_STR}/notifications", tags=["notifications"])
app.include_router(moderation.router, prefix=f"{settings.API_V1_STR}/moderation", tags=["moderation"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(ai.router, prefix=f"{settings.API_V1_STR}/ai", tags=["ai"])
app.include_router(problems.router, prefix=f"{settings.API_V1_STR}/problems", tags=["problems"])
app.include_router(solutions.router, prefix=f"{settings.API_V1_STR}", tags=["solutions"])
app.include_router(rooms.router, prefix=f"{settings.API_V1_STR}", tags=["rooms"])
app.include_router(ws.router, prefix=f"{settings.API_V1_STR}", tags=["websockets"])
app.include_router(files.router, prefix=f"{settings.API_V1_STR}", tags=["files"])
app.include_router(knowledge.router, prefix=f"{settings.API_V1_STR}/knowledge", tags=["knowledge"])

@app.get(f"{settings.API_V1_STR}/health")
def api_v1_health():
    return {"status": "ok", "version": "v1"}
