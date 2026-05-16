from prometheus_client import Counter, Gauge, Histogram
from functools import partial

exchange_fetch_duration = Histogram(
    "exchange_fetch_duration_seconds",
    "Time spent fetching data from each exchange",
    ["exchange", "status"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

exchange_fetch_failures = Counter(
    "exchange_fetch_failures_total",
    "Total fetch failures per exchange",
    ["exchange"],
)

ws_active_connections = Gauge(
    "ws_active_connections",
    "Current number of active WebSocket connections",
)

db_writer_queue_size = Gauge(
    "db_writer_queue_size",
    "Current depth of the database writer queue",
)

collector_circuit_open = Gauge(
    "collector_circuit_open",
    "Whether the collector circuit breaker is open (1=open, 0=closed)",
    ["exchange"],
)
