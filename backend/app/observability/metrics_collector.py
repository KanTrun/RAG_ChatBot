"""In-memory metrics collector for latency tracking."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class LatencyStats:
    p50: float
    p95: float
    p99: float
    count: int
    avg: float


class MetricsCollector:
    """Rolling window latency metrics per operation."""

    def __init__(self, window_size: int = 1000):
        self._samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

    def record(self, operation: str, latency_ms: float):
        self._samples[operation].append(latency_ms)

    def get_stats(self, operation: str) -> LatencyStats | None:
        samples = self._samples.get(operation)
        if not samples:
            return None
        sorted_s = sorted(samples)
        n = len(sorted_s)
        return LatencyStats(
            p50=sorted_s[int(n * 0.50)],
            p95=sorted_s[int(n * 0.95)] if n >= 20 else sorted_s[-1],
            p99=sorted_s[int(n * 0.99)] if n >= 100 else sorted_s[-1],
            count=n,
            avg=sum(sorted_s) / n,
        )

    def all_stats(self) -> dict[str, LatencyStats]:
        return {
            op: stats
            for op in self._samples
            if (stats := self.get_stats(op)) is not None
        }


# Singleton
_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    return _collector
