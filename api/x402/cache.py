"""
Redis Caching Layer for x402 Payment Gateway
High-performance caching for payment verification results
"""

import json
import logging
import os
from typing import Optional, Any, Dict
from datetime import timedelta
import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Async Redis cache manager for x402 payment data

    Features:
    - Payment verification result caching
    - Transaction lookup caching
    - Address reputation caching
    - Automatic expiration
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        password: Optional[str] = None,
        max_connections: int = 50,
        default_ttl: int = 3600
    ):
        self.redis_url = redis_url
        self.password = password
        self.max_connections = max_connections
        self.default_ttl = default_ttl
        self.redis: Optional[Redis] = None

    async def connect(self):
        """Initialize Redis connection pool"""
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                password=self.password,
                max_connections=self.max_connections,
                decode_responses=True,
                encoding="utf-8"
            )
            # Test connection
            await self.redis.ping()
            logger.info("Redis cache connected successfully")
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis = None

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis cache disconnected")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except RedisError as e:
            logger.error(f"Redis GET error: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in cache with TTL"""
        if not self.redis:
            return False

        try:
            ttl = ttl or self.default_ttl
            serialized = json.dumps(value, default=str)
            await self.redis.setex(key, ttl, serialized)
            return True
        except (RedisError, TypeError, ValueError) as e:
            logger.error(f"Redis SET error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis:
            return False

        try:
            await self.redis.delete(key)
            return True
        except RedisError as e:
            logger.error(f"Redis DELETE error: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.redis:
            return False

        try:
            return await self.redis.exists(key) > 0
        except RedisError as e:
            logger.error(f"Redis EXISTS error: {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter"""
        if not self.redis:
            return None

        try:
            return await self.redis.incrby(key, amount)
        except RedisError as e:
            logger.error(f"Redis INCRBY error: {e}")
            return None

    async def get_many(self, keys: list[str]) -> Dict[str, Any]:
        """Get multiple values at once"""
        if not self.redis or not keys:
            return {}

        try:
            values = await self.redis.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value
            return result
        except RedisError as e:
            logger.error(f"Redis MGET error: {e}")
            return {}

    async def set_many(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Set multiple key-value pairs"""
        if not self.redis or not mapping:
            return False

        try:
            ttl = ttl or self.default_ttl
            pipe = self.redis.pipeline()

            for key, value in mapping.items():
                serialized = json.dumps(value, default=str)
                pipe.setex(key, ttl, serialized)

            await pipe.execute()
            return True
        except (RedisError, TypeError, ValueError) as e:
            logger.error(f"Redis MSET error: {e}")
            return False

    # Specialized cache methods for x402

    async def cache_payment_verification(
        self,
        tx_hash: str,
        chain: str,
        verification_result: Dict,
        ttl: int = 3600
    ) -> bool:
        """Cache payment verification result"""
        key = f"x402:verification:{chain}:{tx_hash}"
        return await self.set(key, verification_result, ttl)

    async def get_cached_verification(
        self,
        tx_hash: str,
        chain: str
    ) -> Optional[Dict]:
        """Get cached payment verification result"""
        key = f"x402:verification:{chain}:{tx_hash}"
        return await self.get(key)

    async def cache_payment_token(
        self,
        token: str,
        payment_id: int,
        ttl: int = 3600
    ) -> bool:
        """Cache payment token mapping"""
        key = f"x402:token:{token}"
        return await self.set(key, {"payment_id": payment_id}, ttl)

    async def get_payment_from_token(self, token: str) -> Optional[int]:
        """Get payment ID from cached token"""
        key = f"x402:token:{token}"
        result = await self.get(key)
        return result.get("payment_id") if result else None

    async def cache_address_reputation(
        self,
        address: str,
        chain: str,
        reputation_score: float,
        ttl: int = 86400  # 24 hours
    ) -> bool:
        """Cache address reputation score"""
        key = f"x402:reputation:{chain}:{address.lower()}"
        return await self.set(key, {"score": reputation_score}, ttl)

    async def get_address_reputation(
        self,
        address: str,
        chain: str
    ) -> Optional[float]:
        """Get cached address reputation"""
        key = f"x402:reputation:{chain}:{address.lower()}"
        result = await self.get(key)
        return result.get("score") if result else None

    async def increment_request_count(
        self,
        endpoint: str,
        time_window: str = "hour"
    ) -> Optional[int]:
        """Increment request counter for rate limiting"""
        key = f"x402:requests:{time_window}:{endpoint}"
        count = await self.increment(key)

        # Set expiry on first increment
        if count == 1:
            ttl = 3600 if time_window == "hour" else 60
            if self.redis:
                await self.redis.expire(key, ttl)

        return count

    async def get_request_count(
        self,
        endpoint: str,
        time_window: str = "hour"
    ) -> int:
        """Get request count for endpoint"""
        key = f"x402:requests:{time_window}:{endpoint}"
        count = await self.get(key)
        return count or 0

    async def flush_namespace(self, namespace: str) -> int:
        """Delete all keys in a namespace"""
        if not self.redis:
            return 0

        try:
            pattern = f"{namespace}:*"
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += await self.redis.delete(*keys)
                if cursor == 0:
                    break

            logger.info(f"Flushed {deleted} keys from namespace '{namespace}'")
            return deleted
        except RedisError as e:
            logger.error(f"Redis FLUSH error: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.redis:
            return {"status": "disconnected"}

        try:
            info = await self.redis.info()
            return {
                "status": "connected",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except RedisError as e:
            logger.error(f"Redis INFO error: {e}")
            return {"status": "error", "error": str(e)}

    @staticmethod
    def _calculate_hit_rate(hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return 0.0
        return (hits / total) * 100


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


async def get_cache_manager() -> CacheManager:
    """Get or create global cache manager"""
    global _cache_manager

    if _cache_manager is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_password = os.getenv("REDIS_PASSWORD")
        max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
        default_ttl = int(os.getenv("CACHE_PAYMENT_TTL", "3600"))

        _cache_manager = CacheManager(
            redis_url=redis_url,
            password=redis_password,
            max_connections=max_connections,
            default_ttl=default_ttl
        )
        await _cache_manager.connect()

    return _cache_manager


async def close_cache():
    """Close global cache manager"""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.disconnect()
        _cache_manager = None
