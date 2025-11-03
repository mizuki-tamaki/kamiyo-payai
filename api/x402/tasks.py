"""
Celery Background Tasks for x402 Payment Gateway
Periodic cleanup, analytics aggregation, and maintenance tasks
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from celery import Celery
from celery.schedules import crontab
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    'x402_tasks',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic task schedule
celery_app.conf.beat_schedule = {
    'cleanup-expired-payments': {
        'task': 'api.x402.tasks.cleanup_expired_payments',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'cleanup-expired-tokens': {
        'task': 'api.x402.tasks.cleanup_expired_tokens',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    'aggregate-hourly-analytics': {
        'task': 'api.x402.tasks.aggregate_hourly_analytics',
        'schedule': crontab(minute=5),  # Every hour at :05
    },
    'cleanup-cache-entries': {
        'task': 'api.x402.tasks.cleanup_cache_entries',
        'schedule': crontab(hour='*/6', minute=0),  # Every 6 hours
    },
    'health-check-rpc-endpoints': {
        'task': 'api.x402.tasks.health_check_rpc_endpoints',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
    'generate-daily-report': {
        'task': 'api.x402.tasks.generate_daily_report',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
}


# =============================================================================
# DATABASE CLEANUP TASKS
# =============================================================================

@celery_app.task(name='api.x402.tasks.cleanup_expired_payments')
def cleanup_expired_payments():
    """
    Mark expired payments and update their status
    Runs every 30 minutes
    """
    logger.info("Starting expired payment cleanup...")

    try:
        # Use synchronous database session for Celery
        from api.database import SyncSessionLocal
        from api.x402.models import X402Payment
        from sqlalchemy import and_

        with SyncSessionLocal() as db:
            # Find expired payments
            expired = db.query(X402Payment).filter(
                and_(
                    X402Payment.status == 'verified',
                    X402Payment.expires_at < datetime.utcnow()
                )
            ).all()

            count = 0
            for payment in expired:
                payment.status = 'expired'
                payment.updated_at = datetime.utcnow()
                count += 1

            db.commit()

            logger.info(f"Marked {count} payments as expired")
            return {"expired_count": count}

    except Exception as e:
        logger.error(f"Error in cleanup_expired_payments: {e}", exc_info=True)
        raise


@celery_app.task(name='api.x402.tasks.cleanup_expired_tokens')
def cleanup_expired_tokens():
    """
    Delete expired payment tokens
    Runs every 15 minutes
    """
    logger.info("Starting expired token cleanup...")

    try:
        from api.database import SyncSessionLocal
        from api.x402.models import X402Token

        with SyncSessionLocal() as db:
            # Delete expired tokens
            deleted = db.query(X402Token).filter(
                X402Token.expires_at < datetime.utcnow()
            ).delete(synchronize_session=False)

            db.commit()

            logger.info(f"Deleted {deleted} expired tokens")
            return {"deleted_count": deleted}

    except Exception as e:
        logger.error(f"Error in cleanup_expired_tokens: {e}", exc_info=True)
        raise


@celery_app.task(name='api.x402.tasks.cleanup_old_usage_records')
def cleanup_old_usage_records(days: int = 90):
    """
    Archive or delete old usage records
    Keep last 90 days by default
    """
    logger.info(f"Cleaning up usage records older than {days} days...")

    try:
        from api.database import SyncSessionLocal
        from api.x402.models import X402Usage

        cutoff = datetime.utcnow() - timedelta(days=days)

        with SyncSessionLocal() as db:
            deleted = db.query(X402Usage).filter(
                X402Usage.created_at < cutoff
            ).delete(synchronize_session=False)

            db.commit()

            logger.info(f"Deleted {deleted} old usage records")
            return {"deleted_count": deleted}

    except Exception as e:
        logger.error(f"Error in cleanup_old_usage_records: {e}", exc_info=True)
        raise


# =============================================================================
# ANALYTICS AGGREGATION TASKS
# =============================================================================

@celery_app.task(name='api.x402.tasks.aggregate_hourly_analytics')
def aggregate_hourly_analytics():
    """
    Aggregate payment data into hourly analytics
    Runs every hour
    """
    logger.info("Starting hourly analytics aggregation...")

    try:
        from api.database import SyncSessionLocal
        from api.x402.models import X402Payment, X402Analytics
        from sqlalchemy import func

        with SyncSessionLocal() as db:
            # Get the last hour bucket
            now = datetime.utcnow()
            hour_bucket = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

            # Check if already aggregated
            existing = db.query(X402Analytics).filter(
                X402Analytics.hour_bucket == hour_bucket
            ).first()

            if existing:
                logger.info(f"Analytics for {hour_bucket} already aggregated")
                return {"status": "skipped", "reason": "already_exists"}

            # Aggregate by chain
            chains = db.query(X402Payment.chain).distinct().all()
            aggregated = []

            for (chain,) in chains:
                # Query payments for this hour and chain
                payments = db.query(X402Payment).filter(
                    X402Payment.chain == chain,
                    X402Payment.created_at >= hour_bucket,
                    X402Payment.created_at < hour_bucket + timedelta(hours=1),
                    X402Payment.status.in_(['verified', 'used'])
                ).all()

                if not payments:
                    continue

                total_payments = len(payments)
                total_amount = sum(p.amount_usdc for p in payments)
                total_requests = sum(p.requests_used for p in payments)
                unique_payers = len(set(p.from_address for p in payments))
                avg_payment = total_amount / total_payments if total_payments > 0 else Decimal(0)

                # Create analytics record
                analytics = X402Analytics(
                    hour_bucket=hour_bucket,
                    chain=chain,
                    total_payments=total_payments,
                    total_amount_usdc=total_amount,
                    total_requests=total_requests,
                    unique_payers=unique_payers,
                    average_payment_usdc=avg_payment
                )
                db.add(analytics)
                aggregated.append(chain)

            db.commit()

            logger.info(f"Aggregated analytics for {len(aggregated)} chains: {aggregated}")
            return {"aggregated_chains": aggregated, "hour_bucket": str(hour_bucket)}

    except Exception as e:
        logger.error(f"Error in aggregate_hourly_analytics: {e}", exc_info=True)
        raise


# =============================================================================
# CACHE MAINTENANCE TASKS
# =============================================================================

@celery_app.task(name='api.x402.tasks.cleanup_cache_entries')
def cleanup_cache_entries():
    """
    Clean up old cache entries
    Runs every 6 hours
    """
    logger.info("Starting cache cleanup...")

    try:
        # This is a placeholder - actual implementation depends on cache backend
        # For Redis, expired keys are automatically removed
        # This task can do additional cleanup if needed

        from api.x402.cache import get_cache_manager
        import asyncio

        async def async_cleanup():
            cache = await get_cache_manager()
            stats = await cache.get_stats()
            return stats

        # Run async function in sync context
        stats = asyncio.run(async_cleanup())

        logger.info(f"Cache stats: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error in cleanup_cache_entries: {e}", exc_info=True)
        raise


# =============================================================================
# HEALTH CHECK TASKS
# =============================================================================

@celery_app.task(name='api.x402.tasks.health_check_rpc_endpoints')
def health_check_rpc_endpoints():
    """
    Check health of blockchain RPC endpoints
    Runs every 5 minutes
    """
    logger.info("Starting RPC endpoint health check...")

    try:
        from api.x402.config import get_x402_config
        import httpx

        config = get_x402_config()
        results = {}

        # Check each RPC endpoint
        rpc_endpoints = {
            'base': config.base_rpc_url,
            'ethereum': config.ethereum_rpc_url,
            'solana': config.solana_rpc_url,
        }

        for chain, url in rpc_endpoints.items():
            try:
                # Simple HTTP check
                response = httpx.get(url, timeout=5.0)
                results[chain] = {
                    'status': 'healthy' if response.status_code < 500 else 'degraded',
                    'status_code': response.status_code,
                    'response_time_ms': int(response.elapsed.total_seconds() * 1000)
                }
            except Exception as e:
                results[chain] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                logger.warning(f"RPC health check failed for {chain}: {e}")

        logger.info(f"RPC health check complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Error in health_check_rpc_endpoints: {e}", exc_info=True)
        raise


# =============================================================================
# REPORTING TASKS
# =============================================================================

@celery_app.task(name='api.x402.tasks.generate_daily_report')
def generate_daily_report():
    """
    Generate daily payment report
    Runs daily at midnight
    """
    logger.info("Generating daily report...")

    try:
        from api.database import SyncSessionLocal
        from api.x402.models import X402Payment, X402Usage
        from sqlalchemy import func

        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_time = datetime.combine(yesterday, datetime.min.time())
        end_time = datetime.combine(yesterday, datetime.max.time())

        with SyncSessionLocal() as db:
            # Payment stats
            payment_stats = db.query(
                func.count(X402Payment.id).label('total'),
                func.sum(X402Payment.amount_usdc).label('revenue'),
                func.count(func.distinct(X402Payment.from_address)).label('unique_users')
            ).filter(
                X402Payment.created_at >= start_time,
                X402Payment.created_at <= end_time,
                X402Payment.status.in_(['verified', 'used'])
            ).first()

            # API usage stats
            usage_stats = db.query(
                func.count(X402Usage.id).label('total_requests')
            ).filter(
                X402Usage.created_at >= start_time,
                X402Usage.created_at <= end_time
            ).first()

            report = {
                'date': str(yesterday),
                'payments': {
                    'total': payment_stats.total or 0,
                    'revenue_usdc': float(payment_stats.revenue or 0),
                    'unique_users': payment_stats.unique_users or 0
                },
                'usage': {
                    'total_requests': usage_stats.total_requests or 0
                }
            }

            logger.info(f"Daily report generated: {report}")
            return report

    except Exception as e:
        logger.error(f"Error in generate_daily_report: {e}", exc_info=True)
        raise


# =============================================================================
# MANUAL TASKS
# =============================================================================

@celery_app.task(name='api.x402.tasks.recalculate_payment_stats')
def recalculate_payment_stats():
    """
    Manually recalculate all payment statistics
    Recalculates requests_remaining and fixes any inconsistencies
    """
    logger.info("Recalculating payment stats...")

    try:
        from api.database import SyncSessionLocal
        from api.x402.models import X402Payment, X402Usage
        from sqlalchemy import func

        with SyncSessionLocal() as db:
            # Get all active payments
            payments = db.query(X402Payment).filter(
                X402Payment.status.in_(['verified', 'used', 'expired'])
            ).all()

            fixed_count = 0
            for payment in payments:
                # Count actual usage from usage records
                actual_usage = db.query(func.count(X402Usage.id)).filter(
                    X402Usage.payment_id == payment.id
                ).scalar() or 0

                # Check if requests_used matches actual usage
                if payment.requests_used != actual_usage:
                    logger.info(
                        f"Fixing payment {payment.id}: "
                        f"recorded={payment.requests_used}, actual={actual_usage}"
                    )
                    payment.requests_used = actual_usage
                    fixed_count += 1

                # Update status based on usage
                if payment.requests_used >= payment.requests_allocated:
                    if payment.status == 'verified':
                        payment.status = 'used'
                        fixed_count += 1

                # Check expiration
                if payment.expires_at < datetime.utcnow():
                    if payment.status == 'verified':
                        payment.status = 'expired'
                        fixed_count += 1

                payment.updated_at = datetime.utcnow()

            db.commit()

            logger.info(f"Recalculated stats for {len(payments)} payments, fixed {fixed_count} inconsistencies")
            return {
                "processed": len(payments),
                "fixed": fixed_count
            }

    except Exception as e:
        logger.error(f"Error in recalculate_payment_stats: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    # For testing tasks locally
    print("Celery tasks module loaded")
    print(f"Configured {len(celery_app.conf.beat_schedule)} periodic tasks")
