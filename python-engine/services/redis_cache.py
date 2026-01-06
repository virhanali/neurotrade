"""
Redis Cache Service (v1.0)
Persistent cache layer for OHLCV data and whale signals.
Falls back to in-memory cache if Redis is unavailable.
"""

import json
import logging
import time
from typing import Optional, Any, Dict

# Try to import redis, fall back gracefully
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    logging.warning("[CACHE] Redis not available, using in-memory cache only")


class RedisCache:
    """
    Redis-backed cache with automatic fallback to in-memory.
    Uses JSON serialization for complex objects.
    """
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self._memory_cache: Dict[str, tuple] = {}  # Fallback
        self._redis = None
        self._use_redis = False
        
        if HAS_REDIS:
            try:
                self._redis = redis.Redis(
                    host=host, 
                    port=port, 
                    db=db,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                    decode_responses=True
                )
                # Test connection
                self._redis.ping()
                self._use_redis = True
                logging.info(f"[CACHE] Connected to Redis at {host}:{port}")
            except Exception as e:
                logging.warning(f"[CACHE] Redis unavailable ({e}), using in-memory cache")
                self._use_redis = False
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if self._use_redis:
            try:
                data = self._redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logging.warning(f"[CACHE] Redis get error: {e}")
                # Fallback to memory
        
        # Memory cache fallback
        if key in self._memory_cache:
            value, expires_at = self._memory_cache[key]
            if time.time() < expires_at:
                return value
            else:
                del self._memory_cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = 60) -> bool:
        """Set value in cache with TTL (seconds)"""
        if self._use_redis:
            try:
                self._redis.setex(key, ttl, json.dumps(value))
                return True
            except Exception as e:
                logging.warning(f"[CACHE] Redis set error: {e}")
        
        # Memory cache fallback
        self._memory_cache[key] = (value, time.time() + ttl)
        return True
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if self._use_redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        
        if key in self._memory_cache:
            del self._memory_cache[key]
        return True
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern (e.g., 'ohlcv:*')"""
        count = 0
        if self._use_redis:
            try:
                keys = self._redis.keys(pattern)
                if keys:
                    count = self._redis.delete(*keys)
            except Exception as e:
                logging.warning(f"[CACHE] Redis clear error: {e}")
        
        # Also clear from memory cache
        keys_to_del = [k for k in self._memory_cache if k.startswith(pattern.replace('*', ''))]
        for k in keys_to_del:
            del self._memory_cache[k]
            count += 1
        
        return count
    
    def stats(self) -> Dict:
        """Get cache statistics"""
        stats = {
            "type": "redis" if self._use_redis else "memory",
            "connected": self._use_redis,
            "memory_keys": len(self._memory_cache)
        }
        
        if self._use_redis:
            try:
                info = self._redis.info("memory")
                stats["redis_memory"] = info.get("used_memory_human", "N/A")
                stats["redis_keys"] = self._redis.dbsize()
            except Exception:
                pass
        
        return stats


# Singleton instance
_cache_instance: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    """Get or create global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        # Try to get Redis config from environment
        import os
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        _cache_instance = RedisCache(host=host, port=port)
    return _cache_instance


# Convenience functions
def cache_get(key: str) -> Optional[Any]:
    return get_cache().get(key)


def cache_set(key: str, value: Any, ttl: int = 60) -> bool:
    return get_cache().set(key, value, ttl)


def cache_stats() -> Dict:
    return get_cache().stats()
