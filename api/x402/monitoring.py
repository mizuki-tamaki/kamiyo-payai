"""
Prometheus Monitoring for x402 Payment Gateway
Comprehensive metrics collection and instrumentation
"""

import time
import logging
from typing import Callable
from functools import wraps
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST
)
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# =============================================================================
# PAYMENT METRICS
# =============================================================================

# Payment verification metrics
payment_verifications_total = Counter(
    'x402_payment_verifications_total',
    'Total number of payment verifications attempted',
    ['chain', 'status']
)

payment_verification_duration = Histogram(
    'x402_payment_verification_duration_seconds',
    'Time spent verifying payments',
    ['chain', 'method'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

payment_amount_usdc = Histogram(
    'x402_payment_amount_usdc',
    'Payment amounts in USDC',
    ['chain'],
    buckets=[0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
)

# Payment success/failure tracking
payments_successful_total = Counter(
    'x402_payments_successful_total',
    'Total number of successful payment verifications',
    ['chain']
)

payments_failed_total = Counter(
    'x402_payments_failed_total',
    'Total number of failed payment verifications',
    ['chain', 'reason']
)

# =============================================================================
# RISK SCORING METRICS
# =============================================================================

risk_score_distribution = Histogram(
    'x402_risk_score_distribution',
    'Distribution of risk scores',
    ['chain'],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

high_risk_payments_total = Counter(
    'x402_high_risk_payments_total',
    'Total number of high-risk payments detected',
    ['chain', 'risk_factor']
)

# =============================================================================
# TOKEN METRICS
# =============================================================================

tokens_generated_total = Counter(
    'x402_tokens_generated_total',
    'Total number of payment tokens generated'
)

tokens_validated_total = Counter(
    'x402_tokens_validated_total',
    'Total number of token validations',
    ['status']
)

active_tokens = Gauge(
    'x402_active_tokens',
    'Number of currently active payment tokens'
)

# =============================================================================
# USAGE METRICS
# =============================================================================

api_requests_with_payment = Counter(
    'x402_api_requests_with_payment_total',
    'Total API requests that included payment',
    ['endpoint', 'payment_type']
)

payment_requests_remaining = Gauge(
    'x402_payment_requests_remaining',
    'Requests remaining for active payments',
    ['payment_id']
)

# =============================================================================
# CACHE METRICS
# =============================================================================

cache_hits_total = Counter(
    'x402_cache_hits_total',
    'Total number of cache hits',
    ['cache_type']
)

cache_misses_total = Counter(
    'x402_cache_misses_total',
    'Total number of cache misses',
    ['cache_type']
)

cache_size_bytes = Gauge(
    'x402_cache_size_bytes',
    'Current cache size in bytes'
)

# =============================================================================
# BLOCKCHAIN RPC METRICS
# =============================================================================

rpc_requests_total = Counter(
    'x402_rpc_requests_total',
    'Total RPC requests to blockchain nodes',
    ['chain', 'method', 'status']
)

rpc_request_duration = Histogram(
    'x402_rpc_request_duration_seconds',
    'Duration of RPC requests',
    ['chain', 'method'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

rpc_errors_total = Counter(
    'x402_rpc_errors_total',
    'Total RPC errors',
    ['chain', 'error_type']
)

# =============================================================================
# DATABASE METRICS
# =============================================================================

db_queries_total = Counter(
    'x402_db_queries_total',
    'Total database queries',
    ['operation', 'table']
)

db_query_duration = Histogram(
    'x402_db_query_duration_seconds',
    'Duration of database queries',
    ['operation', 'table'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

db_connection_pool_size = Gauge(
    'x402_db_connection_pool_size',
    'Current database connection pool size'
)

db_connection_pool_available = Gauge(
    'x402_db_connection_pool_available',
    'Available database connections in pool'
)

# =============================================================================
# SYSTEM METRICS
# =============================================================================

system_info = Info(
    'x402_system',
    'System information'
)

active_payments_gauge = Gauge(
    'x402_active_payments',
    'Number of currently active payments'
)

total_revenue_usdc = Gauge(
    'x402_total_revenue_usdc',
    'Total revenue in USDC'
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def track_payment_verification(chain: str):
    """Decorator to track payment verification metrics"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "unknown"

            try:
                result = await func(*args, **kwargs)
                status = "success" if result.get("is_valid") else "failed"
                payments_successful_total.labels(chain=chain).inc()
                return result
            except Exception as e:
                status = "error"
                payments_failed_total.labels(chain=chain, reason=type(e).__name__).inc()
                raise
            finally:
                duration = time.time() - start_time
                payment_verification_duration.labels(
                    chain=chain,
                    method="async"
                ).observe(duration)
                payment_verifications_total.labels(
                    chain=chain,
                    status=status
                ).inc()

        return wrapper
    return decorator


def track_rpc_request(chain: str, method: str):
    """Decorator to track RPC request metrics"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "unknown"

            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                rpc_errors_total.labels(
                    chain=chain,
                    error_type=type(e).__name__
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                rpc_request_duration.labels(
                    chain=chain,
                    method=method
                ).observe(duration)
                rpc_requests_total.labels(
                    chain=chain,
                    method=method,
                    status=status
                ).inc()

        return wrapper
    return decorator


def track_db_query(operation: str, table: str):
    """Decorator to track database query metrics"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                db_query_duration.labels(
                    operation=operation,
                    table=table
                ).observe(duration)
                db_queries_total.labels(
                    operation=operation,
                    table=table
                ).inc()

        return wrapper
    return decorator


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect x402-specific metrics"""

    async def dispatch(self, request: Request, call_next):
        # Check if request includes payment headers
        has_payment = (
            request.headers.get("X-PAYMENT") or
            request.headers.get("x-payment-tx") or
            request.headers.get("x-payment-token")
        )

        if has_payment:
            payment_type = "token"
            if request.headers.get("x-payment-tx"):
                payment_type = "direct"
            elif request.headers.get("X-PAYMENT"):
                payment_type = "payai"

            api_requests_with_payment.labels(
                endpoint=request.url.path,
                payment_type=payment_type
            ).inc()

        response = await call_next(request)
        return response


# =============================================================================
# INITIALIZATION
# =============================================================================

def setup_monitoring(app):
    """
    Set up Prometheus monitoring for FastAPI app

    Usage:
        from api.x402.monitoring import setup_monitoring
        setup_monitoring(app)
    """
    # Add FastAPI instrumentator
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=False,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/ready"],
        env_var_name="PROMETHEUS_ENABLED",
        inprogress_name="x402_requests_inprogress",
        inprogress_labels=True,
    )

    # Add custom metrics
    instrumentator.add(
        metrics=[
            # Already provided by default instrumentator
        ]
    )

    # Instrument the app
    instrumentator.instrument(app)

    # Add metrics endpoint
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)

    # Add custom middleware
    app.add_middleware(MetricsMiddleware)

    # Set system info
    system_info.info({
        'version': '1.0.0',
        'service': 'x402-payment-gateway'
    })

    logger.info("Prometheus monitoring setup complete - metrics available at /metrics")


def get_metrics():
    """Get current Prometheus metrics in text format"""
    return generate_latest()


def get_metrics_content_type():
    """Get content type for Prometheus metrics"""
    return CONTENT_TYPE_LATEST
