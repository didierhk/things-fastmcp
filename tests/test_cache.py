import pytest
import time
from src.things_mcp.cache import ThingsCache


class TestThingsCache:
    def setup_method(self):
        self.cache = ThingsCache(default_ttl=60)

    def test_set_and_get(self):
        self.cache.set("get-inbox", "result", ttl=60)
        assert self.cache.get("get-inbox") == "result"

    def test_expired_entry_returns_none(self):
        self.cache.set("get-today", "result", ttl=1)
        time.sleep(1.1)
        assert self.cache.get("get-today") is None

    def test_invalidate_operation_removes_matching_entries(self):
        self.cache.set("get-inbox", "result1", ttl=60)
        self.cache.set("get-today", "result2", ttl=60)
        self.cache.invalidate("get-inbox")
        assert self.cache.get("get-inbox") is None
        assert self.cache.get("get-today") == "result2"

    def test_invalidate_all_clears_cache(self):
        self.cache.set("get-inbox", "result1", ttl=60)
        self.cache.set("get-today", "result2", ttl=60)
        self.cache.invalidate()
        assert self.cache.get("get-inbox") is None
        assert self.cache.get("get-today") is None

    def test_hit_rate_tracking(self):
        self.cache.set("op", "val", ttl=60)
        self.cache.get("op")   # hit
        self.cache.get("op")   # hit
        self.cache.get("missing")  # miss
        stats = self.cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
