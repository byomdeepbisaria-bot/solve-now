from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette_prometheus import metrics as prometheus_metrics, PrometheusMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
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
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")

    try:
        await init_redis()
        logger.info("Async Redis connection established.")
    except Exception as e:
        logger.error(f"Failed to connect to Async Redis: {e}")
        
    yield
    pass

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if not settings.is_production else None,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Strict CORS â€” fails closed in production if NEXT_PUBLIC_API_URL is not set
if settings.is_production and not settings.NEXT_PUBLIC_API_URL:
    raise ValueError(
        "NEXT_PUBLIC_API_URL must be set in production. "
        "CORS cannot default to localhost in a production environment."
    )

_cors_origins = (
    [settings.NEXT_PUBLIC_API_URL]
    if settings.NEXT_PUBLIC_API_URL
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)
if not settings.is_production:
    if "http://localhost:3000" not in _cors_origins:
        _cors_origins.append("http://localhost:3000")
    if "http://127.0.0.1:3000" not in _cors_origins:
        _cors_origins.append("http://127.0.0.1:3000")
# Allow both API URL and APP URL if they differ (e.g. api.example.com serving app.example.com)
if settings.NEXT_PUBLIC_APP_URL and settings.NEXT_PUBLIC_APP_URL not in _cors_origins:
    _cors_origins.append(settings.NEXT_PUBLIC_APP_URL)

 main

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
app.add_route("/metrics", prometheus_metrics)

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
