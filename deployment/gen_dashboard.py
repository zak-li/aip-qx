"""
RWA Platform — Grafana dashboard generator.
Builds only panels backed by currently-active scrape targets:
  UP  : node-exporter, postgres, prometheus, redis, rwa-api
  DOWN: fabric-peers, couchdb, celery  (excluded — no data)
"""

import json, requests, sys

# ── Config ────────────────────────────────────────────────────────────────────
GRAFANA  = "http://10.10.10.150:3000"
USER, PW = "admin", "admin"
DS       = "ffgx1hbr25a0wc"   # Prometheus datasource UID

# ── Palette ───────────────────────────────────────────────────────────────────
GREEN  = "#73BF69"
YELLOW = "#FADE2A"
ORANGE = "#FF780A"
RED    = "#F2495C"
BLUE   = "#5794F2"
CYAN   = "#19D3C5"
PURPLE = "#B877D9"
TEAL   = "#00B8A9"
LIME   = "#96D98D"

_pid = 1

def pid():
    global _pid; v = _pid; _pid += 1; return v

def ds_ref():
    return {"type": "prometheus", "uid": DS}

def tgt(expr, legend="", instant=False, ref="A"):
    t = {"datasource": ds_ref(), "expr": expr,
         "legendFormat": legend, "refId": ref}
    if instant: t["instant"] = True
    return t

def tgts(*pairs):
    refs = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return [{"datasource": ds_ref(), "expr": e, "legendFormat": l, "refId": refs[i]}
            for i, (e, l) in enumerate(pairs)]

def gp(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}

# ── Panel factories ────────────────────────────────────────────────────────────

def row_panel(title, y):
    return {"id": pid(), "type": "row", "title": title,
            "collapsed": False, "gridPos": gp(0, y, 24, 1), "panels": []}


def stat_spark(title, expr, unit="short", thresholds=None, x=0, y=0, w=6, h=5,
               legend="", decimals=1):
    """Stat with sparkline area — inspired by 'Color value' screenshot."""
    th = thresholds or [
        {"color": BLUE, "value": None}, {"color": YELLOW, "value": 70}, {"color": RED, "value": 90}]
    return {
        "id": pid(), "type": "stat", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": [tgt(expr, legend)],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": "background", "graphMode": "area",
            "justifyMode": "auto", "textMode": "valueAndName",
            "orientation": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit, "decimals": decimals,
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": th},
            }, "overrides": []
        }
    }


def state_timeline(title, target_list, x=0, y=0, w=24, h=7, vm=None):
    """Coloured band timeline — inspired by screenshot 1."""
    default_vm = [{"type": "value", "options": {
        "0": {"text": "DOWN", "color": RED,   "index": 0},
        "1": {"text": "UP",   "color": GREEN, "index": 1},
    }}]
    return {
        "id": pid(), "type": "state-timeline", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": target_list,
        "options": {
            "mergeValues": True, "showValue": "always",
            "alignValue": "center", "rowHeight": 0.85,
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "single"},
        },
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": RED, "value": None}, {"color": GREEN, "value": 1}]},
                "mappings": vm or default_vm,
                "custom": {"lineWidth": 0, "fillOpacity": 85},
            }, "overrides": []
        }
    }


def status_history(title, target_list, unit="short", x=0, y=0, w=24, h=8, thresholds=None):
    """Heatmap grid — inspired by screenshot 3."""
    th = thresholds or [
        {"color": GREEN, "value": None}, {"color": YELLOW, "value": 60},
        {"color": ORANGE, "value": 80},  {"color": RED,    "value": 95}]
    return {
        "id": pid(), "type": "status-history", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": target_list,
        "options": {
            "mergeValues": False, "showValue": "always",
            "fillOpacity": 90, "rowHeight": 0.9, "colWidth": 0.9,
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "single"},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit, "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": th},
                "custom": {"lineWidth": 2, "fillOpacity": 85},
            }, "overrides": []
        }
    }


def timeseries(title, target_list, unit="short", x=0, y=0, w=12, h=8,
               fill=15, gradient="scheme", stack=False, thresholds=None):
    th = thresholds or [
        {"color": GREEN, "value": None}, {"color": YELLOW, "value": 70}, {"color": RED, "value": 90}]
    return {
        "id": pid(), "type": "timeseries", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": target_list,
        "options": {
            "tooltip": {"mode": "multi", "sort": "desc"},
            "legend": {"displayMode": "table", "placement": "bottom",
                       "calcs": ["mean", "max", "lastNotNull"]},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit, "color": {"mode": "palette-classic"},
                "thresholds": {"mode": "absolute", "steps": th},
                "custom": {
                    "lineWidth": 2, "fillOpacity": fill,
                    "gradientMode": gradient, "showPoints": "never",
                    "stacking": {"mode": "normal" if stack else "none"},
                },
            }, "overrides": []
        }
    }


def bargauge(title, target_list, unit="short", x=0, y=0, w=12, h=6,
             orientation="horizontal", thresholds=None):
    th = thresholds or [
        {"color": GREEN, "value": None}, {"color": YELLOW, "value": 60}, {"color": RED, "value": 85}]
    return {
        "id": pid(), "type": "bargauge", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": target_list,
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": orientation, "displayMode": "gradient",
            "valueMode": "color", "showUnfilled": True,
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit, "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": th},
            }, "overrides": []
        }
    }


def gauge_panel(title, expr, unit="percent", x=0, y=0, w=4, h=7,
                min_val=0, max_val=100, thresholds=None):
    th = thresholds or [
        {"color": GREEN, "value": None}, {"color": YELLOW, "value": 60}, {"color": RED, "value": 85}]
    return {
        "id": pid(), "type": "gauge", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": [tgt(expr, instant=True)],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": False, "showThresholdMarkers": True,
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit, "min": min_val, "max": max_val,
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": th},
            }, "overrides": []
        }
    }


def piechart(title, target_list, x=0, y=0, w=8, h=8, pie_type="donut"):
    return {
        "id": pid(), "type": "piechart", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": target_list,
        "options": {
            "pieType": pie_type,
            "legend": {"displayMode": "table", "placement": "right",
                       "calcs": ["value", "percent"]},
            "tooltip": {"mode": "multi"},
        },
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}}, "overrides": []
        }
    }


def heatmap(title, expr, x=0, y=0, w=12, h=8, unit="s"):
    return {
        "id": pid(), "type": "heatmap", "title": title,
        "gridPos": gp(x, y, w, h), "datasource": ds_ref(),
        "targets": [tgt(expr, "{{le}}")],
        "options": {
            "calculate": False,
            "color": {"scheme": "Turbo", "steps": 128, "mode": "scheme"},
            "cellGap": 1, "tooltip": {"show": True, "yHistogram": True},
            "legend": {"show": True},
            "yAxis": {"unit": unit, "decimals": 2},
        },
        "fieldConfig": {"defaults": {}, "overrides": []}
    }


# ── Dashboard build ────────────────────────────────────────────────────────────

def build():
    panels = []
    y = 0

    # ── ROW 1 : Service Health  ───────────────────────────────────────────────
    panels.append(row_panel("🔴  Service Health", y)); y += 1

    panels.append(state_timeline(
        "Service Availability",
        tgts(
            ('up{job="rwa-api"}',       "API"),
            ('up{job="redis"}',         "Redis"),
            ('up{job="postgres"}',      "PostgreSQL"),
            ('up{job="node-exporter"}', "Node Exporter"),
            ('up{job="prometheus"}',    "Prometheus"),
        ),
        x=0, y=y, w=24, h=7
    ))
    y += 7

    # ── ROW 2 : KPI Stats  ───────────────────────────────────────────────────
    panels.append(row_panel("📊  Key Performance Indicators", y)); y += 1

    kpis = [
        ("API Req/s",
         'sum(rate(http_requests_total{job="rwa-api"}[2m]))',
         "reqps",
         [{"color": CYAN, "value": None}, {"color": ORANGE, "value": 50}, {"color": RED, "value": 100}]),
        ("API Error Rate",
         'sum(rate(http_requests_total{job="rwa-api",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="rwa-api"}[5m])) * 100',
         "percent",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 1}, {"color": RED, "value": 5}]),
        ("API p99 Latency",
         'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="rwa-api"}[5m])) by (le))',
         "s",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 0.5}, {"color": RED, "value": 2}]),
        ("Redis Ops/s",
         'rate(redis_commands_processed_total[2m])',
         "ops",
         [{"color": TEAL, "value": None}, {"color": YELLOW, "value": 1000}, {"color": RED, "value": 5000}]),
        ("Redis Memory %",
         'redis_memory_used_bytes / redis_memory_max_bytes * 100',
         "percent",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 60}, {"color": RED, "value": 85}]),
        ("Redis Clients",
         'redis_connected_clients',
         "short",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 50}, {"color": RED, "value": 100}]),
        ("PG Connections",
         'sum(pg_stat_activity_count)',
         "short",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 50}, {"color": RED, "value": 90}]),
        ("PG DB Size",
         'sum(pg_database_size_bytes)',
         "bytes",
         [{"color": BLUE, "value": None}, {"color": YELLOW, "value": 5e9}, {"color": RED, "value": 10e9}]),
        ("CPU Usage",
         '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
         "percent",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 60}, {"color": RED, "value": 85}]),
        ("RAM Usage",
         '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
         "percent",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 70}, {"color": RED, "value": 90}]),
        ("Disk /",
         '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)',
         "percent",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 70}, {"color": RED, "value": 85}]),
        ("KYC Expiring",
         'rwa_kyc_expiring_count',
         "short",
         [{"color": GREEN, "value": None}, {"color": YELLOW, "value": 5}, {"color": RED, "value": 20}]),
    ]

    cols = 4
    for i, (title, expr, unit, th) in enumerate(kpis):
        panels.append(stat_spark(
            title, expr, unit=unit, thresholds=th,
            x=(i % cols) * 6, y=y + (i // cols) * 5, w=6, h=5
        ))
    y += (len(kpis) // cols + (1 if len(kpis) % cols else 0)) * 5

    # ── ROW 3 : System Resources  ────────────────────────────────────────────
    panels.append(row_panel("🖥️  System Resources", y)); y += 1

    panels.append(status_history(
        "CPU Usage per Core — Status History",
        tgts(('100 - (rate(node_cpu_seconds_total{mode="idle"}[5m]) * 100)', "CPU {{cpu}}")),
        unit="percent",
        thresholds=[
            {"color": GREEN,  "value": None}, {"color": LIME,   "value": 20},
            {"color": YELLOW, "value": 50},   {"color": ORANGE, "value": 75},
            {"color": RED,    "value": 90},
        ],
        x=0, y=y, w=24, h=8
    ))
    y += 8

    panels.append(timeseries(
        "CPU — All Modes",
        tgts(
            ('rate(node_cpu_seconds_total{mode="user"}[2m]) * 100',   "User"),
            ('rate(node_cpu_seconds_total{mode="system"}[2m]) * 100', "System"),
            ('rate(node_cpu_seconds_total{mode="iowait"}[2m]) * 100', "IOWait"),
            ('rate(node_cpu_seconds_total{mode="steal"}[2m]) * 100',  "Steal"),
        ),
        unit="percent", x=0, y=y, w=12, h=8, fill=20, gradient="opacity", stack=True
    ))
    panels.append(timeseries(
        "Memory Breakdown",
        tgts(
            ('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes', "Used"),
            ('node_memory_Cached_bytes',  "Cached"),
            ('node_memory_Buffers_bytes', "Buffers"),
            ('node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes', "Swap"),
        ),
        unit="bytes", x=12, y=y, w=12, h=8, fill=20, gradient="scheme", stack=True
    ))
    y += 8

    panels.append(gauge_panel(
        "CPU", '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)',
        x=0, y=y, w=4, h=7))
    panels.append(gauge_panel(
        "RAM", '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
        x=4, y=y, w=4, h=7,
        thresholds=[{"color": GREEN, "value": None}, {"color": YELLOW, "value": 70}, {"color": RED, "value": 90}]))
    panels.append(gauge_panel(
        "Disk /",
        '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)',
        x=8, y=y, w=4, h=7))
    panels.append(timeseries(
        "Disk I/O",
        tgts(
            ('rate(node_disk_read_bytes_total{device=~"sda|vda"}[2m])',    "Read"),
            ('rate(node_disk_written_bytes_total{device=~"sda|vda"}[2m])', "Write"),
        ),
        unit="Bps", x=12, y=y, w=6, h=7, fill=15, gradient="scheme"
    ))
    panels.append(timeseries(
        "Network Traffic",
        tgts(
            ('rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*"}[2m])',  "RX"),
            ('rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*"}[2m])', "TX"),
        ),
        unit="Bps", x=18, y=y, w=6, h=7, fill=15, gradient="scheme"
    ))
    y += 7

    # ── ROW 4 : API Performance  ──────────────────────────────────────────────
    panels.append(row_panel("🌐  API Performance", y)); y += 1

    panels.append(timeseries(
        "Request Rate by HTTP Status",
        tgts(
            ('sum(rate(http_requests_total{job="rwa-api",status=~"2.."}[2m]))', "2xx ✓"),
            ('sum(rate(http_requests_total{job="rwa-api",status=~"4.."}[2m]))', "4xx"),
            ('sum(rate(http_requests_total{job="rwa-api",status=~"5.."}[2m]))', "5xx ✗"),
        ),
        unit="reqps", x=0, y=y, w=12, h=8, fill=20, gradient="scheme"
    ))
    panels.append(heatmap(
        "Request Duration Heatmap",
        'sum(rate(http_request_duration_seconds_bucket{job="rwa-api"}[5m])) by (le)',
        x=12, y=y, w=12, h=8, unit="s"
    ))
    y += 8

    panels.append(bargauge(
        "Top Handlers by Req/s",
        tgts(('topk(10, sum by (handler) (rate(http_requests_total{job="rwa-api"}[5m])))', "{{handler}}")),
        unit="reqps", x=0, y=y, w=12, h=8, orientation="horizontal",
        thresholds=[{"color": CYAN, "value": None}, {"color": BLUE, "value": 5}, {"color": PURPLE, "value": 20}]
    ))
    panels.append(timeseries(
        "Latency Percentiles",
        tgts(
            ('histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{job="rwa-api"}[5m])) by (le))', "p50"),
            ('histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="rwa-api"}[5m])) by (le))', "p95"),
            ('histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="rwa-api"}[5m])) by (le))', "p99"),
        ),
        unit="s", x=12, y=y, w=12, h=8, fill=10, gradient="opacity",
        thresholds=[{"color": GREEN, "value": None}, {"color": YELLOW, "value": 0.5}, {"color": RED, "value": 2}]
    ))
    y += 8

    # ── ROW 5 : Redis  ───────────────────────────────────────────────────────
    panels.append(row_panel("🔴  Redis", y)); y += 1

    panels.append(status_history(
        "Redis Commands — Activity History",
        tgts(
            ('rate(redis_commands_total{cmd="get"}[5m])',     "GET"),
            ('rate(redis_commands_total{cmd="set"}[5m])',     "SET"),
            ('rate(redis_commands_total{cmd="hget"}[5m])',    "HGET"),
            ('rate(redis_commands_total{cmd="hset"}[5m])',    "HSET"),
            ('rate(redis_commands_total{cmd="publish"}[5m])', "PUBLISH"),
            ('rate(redis_commands_total{cmd="lpush"}[5m])',   "LPUSH"),
        ),
        unit="ops",
        thresholds=[
            {"color": "#111827", "value": None}, {"color": TEAL,   "value": 0.01},
            {"color": CYAN,      "value": 1},    {"color": BLUE,   "value": 10},
            {"color": PURPLE,    "value": 50},
        ],
        x=0, y=y, w=24, h=7
    ))
    y += 7

    panels.append(timeseries(
        "Redis Memory",
        tgts(
            ('redis_memory_used_bytes',      "Used"),
            ('redis_memory_used_peak_bytes', "Peak"),
            ('redis_memory_max_bytes',       "Max"),
        ),
        unit="bytes", x=0, y=y, w=12, h=7, fill=15, gradient="scheme"
    ))
    panels.append(timeseries(
        "Hits vs Misses",
        tgts(
            ('rate(redis_keyspace_hits_total[2m])',   "Hits"),
            ('rate(redis_keyspace_misses_total[2m])', "Misses"),
        ),
        unit="ops", x=12, y=y, w=8, h=7, fill=20, gradient="scheme"
    ))
    panels.append(stat_spark(
        "Cache Hit Rate",
        'rate(redis_keyspace_hits_total[5m]) / clamp_min(rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]), 0.001) * 100',
        unit="percent",
        thresholds=[{"color": RED, "value": None}, {"color": YELLOW, "value": 70}, {"color": GREEN, "value": 90}],
        x=20, y=y, w=4, h=7
    ))
    y += 7

    # ── ROW 6 : PostgreSQL  ──────────────────────────────────────────────────
    panels.append(row_panel("🐘  PostgreSQL", y)); y += 1

    panels.append(status_history(
        "Active Connections per Database — Status History",
        tgts(('pg_stat_activity_count{datname!~"template.*|"}', "{{datname}}")),
        unit="short",
        thresholds=[
            {"color": GREEN, "value": None}, {"color": YELLOW, "value": 10},
            {"color": ORANGE, "value": 30},  {"color": RED,    "value": 50}],
        x=0, y=y, w=24, h=7
    ))
    y += 7

    panels.append(timeseries(
        "Transactions/s",
        tgts(
            ('rate(pg_stat_database_xact_commit{datname!~"template.*|"}[2m])',   "Commits {{datname}}"),
            ('rate(pg_stat_database_xact_rollback{datname!~"template.*|"}[2m])', "Rollbacks {{datname}}"),
        ),
        unit="ops", x=0, y=y, w=12, h=7, fill=15, gradient="scheme"
    ))
    panels.append(timeseries(
        "Cache Hit Ratio",
        tgts(
            ('rate(pg_stat_database_blks_hit{datname!~"template.*|"}[5m]) / clamp_min(rate(pg_stat_database_blks_hit{datname!~"template.*|"}[5m]) + rate(pg_stat_database_blks_read{datname!~"template.*|"}[5m]), 0.001) * 100',
             "{{datname}}"),
        ),
        unit="percent", x=12, y=y, w=8, h=7, fill=15, gradient="scheme",
        thresholds=[{"color": RED, "value": None}, {"color": YELLOW, "value": 80}, {"color": GREEN, "value": 95}]
    ))
    panels.append(bargauge(
        "Database Sizes",
        tgts(('pg_database_size_bytes{datname!~"template.*|"}', "{{datname}}")),
        unit="bytes", x=20, y=y, w=4, h=7, orientation="vertical",
        thresholds=[{"color": BLUE, "value": None}, {"color": CYAN, "value": 1e8}, {"color": PURPLE, "value": 1e9}]
    ))
    y += 7

    # ── ROW 7 : RWA Business Metrics  ────────────────────────────────────────
    panels.append(row_panel("💼  RWA Business Metrics", y)); y += 1

    panels.append(piechart(
        "Assets by Status",
        tgts(('rwa_assets_by_status', "{{status}}")),
        x=0, y=y, w=7, h=8, pie_type="donut"
    ))
    panels.append(piechart(
        "AML Risk Distribution",
        tgts(('rwa_aml_score_avg', "{{risk_category}}")),
        x=7, y=y, w=7, h=8, pie_type="donut"
    ))
    panels.append(timeseries(
        "Compliance Blocks/s",
        tgts(('rate(rwa_compliance_blocks_total[5m])', "{{blocked_by}}")),
        unit="ops", x=14, y=y, w=7, h=8, fill=20, gradient="scheme",
        thresholds=[{"color": GREEN, "value": None}, {"color": RED, "value": 0.01}]
    ))
    panels.append(stat_spark(
        "KYC Expiring (30d)",
        "rwa_kyc_expiring_count", unit="short",
        thresholds=[{"color": GREEN, "value": None}, {"color": YELLOW, "value": 5}, {"color": RED, "value": 20}],
        x=21, y=y, w=3, h=4, decimals=0
    ))
    panels.append(stat_spark(
        "Circuit Breaker",
        "max(rwa_circuit_breaker_state)", unit="short",
        thresholds=[{"color": GREEN, "value": None}, {"color": RED, "value": 1}],
        x=21, y=y + 4, w=3, h=4, decimals=0
    ))
    y += 8

    panels.append(status_history(
        "Celery Tasks — Status History",
        tgts(
            ('rate(rwa_celery_tasks_total{status="success"}[5m])', "{{task_name}} ✓"),
            ('rate(rwa_celery_tasks_total{status="failure"}[5m])', "{{task_name}} ✗"),
        ),
        unit="ops",
        thresholds=[
            {"color": "#111827", "value": None}, {"color": GREEN,  "value": 0.001},
            {"color": YELLOW,    "value": 0.1},  {"color": RED,    "value": 1}],
        x=0, y=y, w=24, h=6
    ))
    y += 6

    # ── Assemble dashboard ─────────────────────────────────────────────────────
    return {
        "uid": "rwa-ops-professional",
        "title": "RWA Platform — Operations Center",
        "tags": ["rwa", "production", "ops"],
        "timezone": "browser",
        "refresh": "30s",
        "schemaVersion": 39,
        "version": 5,
        "time": {"from": "now-3h", "to": "now"},
        "timepicker": {},
        "panels": panels,
        "templating": {"list": []},
        "annotations": {"list": []},
        "editable": True,
        "graphTooltip": 1,
        "links": [],
        "liveNow": False,
    }


def deploy(dash):
    r = requests.post(
        f"{GRAFANA}/api/dashboards/db",
        json={"dashboard": dash, "overwrite": True, "folderId": 0},
        headers={"Content-Type": "application/json"},
        auth=(USER, PW), timeout=15
    )
    return r.status_code, r.json()


if __name__ == "__main__":
    dash = build()
    out = "deployment/monitoring/grafana_dashboard.json"
    with open(out, "w") as f:
        json.dump(dash, f, indent=2)
    print(f"Saved  {out}  ({len(dash['panels'])} panels)")

    if "--no-deploy" not in sys.argv:
        code, resp = deploy(dash)
        print(f"Deploy HTTP {code}: {resp}")
