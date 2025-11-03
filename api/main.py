"""
x402 Payment Gateway - Main FastAPI Application
Multi-chain payment verification for HTTP 402 Payment Required
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import database and middleware
from api.database import init_db, close_db
from api.x402.middleware import X402Middleware
from api.x402.routes import router as x402_router
from api.x402.config import get_x402_config

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Starting x402 Payment Gateway...")

    # Initialize database
    if os.getenv("AUTO_INIT_DB", "false").lower() == "true":
        logger.info("Auto-initializing database...")
        await init_db()

    # Load configuration
    config = get_x402_config()
    logger.info(f"Loaded configuration: PayAI={config.payai_enabled}, "
                f"UnifiedGateway={config.use_unified_gateway}")

    logger.info("x402 Payment Gateway started successfully")

    yield

    # Shutdown
    logger.info("Shutting down x402 Payment Gateway...")
    await close_db()
    logger.info("x402 Payment Gateway shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="x402 Payment Gateway",
    description="Multi-chain payment verification for HTTP 402 Payment Required",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add x402 payment middleware
x402_config = get_x402_config()
if x402_config.middleware_enabled:
    logger.info("x402 middleware enabled for payment-required endpoints")
    app.add_middleware(X402Middleware)

# Include routers
app.include_router(x402_router)


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "x402 Payment Gateway",
        "version": "1.0.0",
        "description": "Multi-chain payment verification for HTTP 402 Payment Required",
        "documentation": "/docs",
        "payment_endpoints": {
            "supported_chains": "/x402/supported-chains",
            "verify_payment": "/x402/verify-payment",
            "pricing": "/x402/pricing",
        },
        "supported_chains": ["base", "polygon", "avalanche", "solana", "sei", "iotex", "peaq"],
        "payment_methods": ["payai_network", "direct_onchain"]
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "x402-payment-gateway",
    }


@app.get("/ready")
async def ready():
    """
    Readiness check endpoint
    Returns 200 if service is ready to accept traffic
    """
    checks = {}
    all_ready = True

    # Check database connectivity
    try:
        from api.database import engine
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        checks["database"] = "error"
        all_ready = False

    # Check Redis cache
    try:
        from api.x402.cache import get_cache_manager
        cache = await get_cache_manager()
        if cache.redis:
            await cache.redis.ping()
            checks["cache"] = "ok"
        else:
            checks["cache"] = "not_connected"
    except Exception as e:
        logger.error(f"Cache check failed: {e}")
        checks["cache"] = "error"
        all_ready = False

    # Check critical RPC endpoints
    try:
        from api.x402.config import get_x402_config
        import httpx

        config = get_x402_config()
        rpc_checks = {}

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check Base RPC
            try:
                response = await client.post(
                    config.base_rpc_url,
                    json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
                )
                rpc_checks["base"] = "ok" if response.status_code == 200 else "degraded"
            except:
                rpc_checks["base"] = "error"
                all_ready = False

        checks["rpc_endpoints"] = rpc_checks
    except Exception as e:
        logger.error(f"RPC check failed: {e}")
        checks["rpc_endpoints"] = "error"
        all_ready = False

    status_code = 200 if all_ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "checks": checks
        }
    )


# Example protected endpoints (for demonstration)
@app.get("/exploits")
@limiter.limit("10/minute")
async def get_exploits(request: Request):
    """
    Example protected endpoint requiring payment
    This will be intercepted by x402 middleware if enabled
    """
    return {
        "exploits": [
            {
                "id": 1,
                "title": "CVE-2024-XXXX",
                "severity": "critical",
                "description": "Example vulnerability data",
            }
        ],
        "message": "This endpoint requires payment (x402 middleware enabled)"
    }


@app.get("/api/analysis")
@limiter.limit("5/minute")
async def get_analysis(request: Request):
    """
    Example protected endpoint with higher pricing
    Check X402_ENDPOINT_PRICES configuration
    """
    return {
        "analysis": {
            "threats_detected": 42,
            "risk_score": 8.5,
            "recommendations": ["Update dependencies", "Apply security patches"]
        },
        "message": "Premium analysis endpoint"
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "message": f"The endpoint {request.url.path} does not exist",
            "documentation": "/docs"
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Custom 500 handler"""
    logger.error(f"Internal error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )


if __name__ == "__main__":
    import uvicorn

    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    logger.info(f"Starting server on {host}:{port} with {workers} workers")

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level="info",
    )
