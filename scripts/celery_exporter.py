#!/usr/bin/env python3
"""Minimal Celery Prometheus exporter (port 9808)."""
import logging
import time

import celery as celery_lib
import redis as redis_lib
from prometheus_client import Gauge, start_http_server

BROKER = "redis://:XH6w3Iv114cLQq1Qw38I@127.0.0.1:6379/0"
QUEUES = ["celery", "compliance", "reports", "fabric_events"]
PORT   = 9808
INTERVAL = 15

WORKERS_UP    = Gauge("celery_workers_up",    "Number of responsive Celery workers")
TASKS_ACTIVE  = Gauge("celery_tasks_active",  "Active tasks across all workers")
TASKS_RESERVED= Gauge("celery_tasks_reserved","Reserved (prefetched) tasks")
QUEUE_LENGTH  = Gauge("celery_queue_length",  "Messages in queue", ["queue"])

app = celery_lib.Celery(broker=BROKER)
r   = redis_lib.from_url(BROKER, socket_connect_timeout=2, socket_timeout=2)

def collect():
    try:
        i = app.control.inspect(timeout=3)
        active   = i.active()   or {}
        reserved = i.reserved() or {}
        WORKERS_UP.set(len(active))
        TASKS_ACTIVE.set(sum(len(v) for v in active.values()))
        TASKS_RESERVED.set(sum(len(v) for v in reserved.values()))
    except Exception as exc:
        logging.warning("celery inspect error: %s", exc)
        WORKERS_UP.set(0)

    for q in QUEUES:
        try:
            QUEUE_LENGTH.labels(queue=q).set(r.llen(q))
        except Exception:
            QUEUE_LENGTH.labels(queue=q).set(0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_http_server(PORT)
    logging.info("Celery exporter listening on :%d", PORT)
    while True:
        collect()
        time.sleep(INTERVAL)
