# Grafana dashboard generator — one-off script, panels are kept on single
# lines on purpose (compact layout maths). Ruff style rules waived locally.
# ruff: noqa: E701,E702,I001
import json
import os

import requests

GRAFANA = os.environ.get("GRAFANA_URL", "http://localhost:3000")
AUTH    = (os.environ.get("GRAFANA_USER", "admin"), os.environ.get("GRAFANA_PASSWORD", "admin"))
PROM    = os.environ.get("GRAFANA_PROM_UID", "ffgx1hbr25a0wc")
LOKI    = os.environ.get("GRAFANA_LOKI_UID", "loki")

def prom():
    return {"type": "prometheus", "uid": PROM}

def loki_ds():
    return {"type": "loki", "uid": LOKI}

def q(expr, legend="", ref="A"):
    return {
        "datasource": prom(), "expr": expr,
        "legendFormat": legend or "__auto",
        "refId": ref, "instant": False, "range": True,
    }

def ql(expr, ref="A"):
    return {
        "datasource": loki_ds(), "expr": expr,
        "refId": ref, "queryType": "range",
        "maxLines": 200,
    }

# ════════════════════════════════════════════════════════════════════════════
# Panel factories
# ════════════════════════════════════════════════════════════════════════════

def stat(pid, title, expr, x, y, w, h, *, unit="short", thresholds=None,
         mappings=None, fixed=None, decimals=None, color_mode="background",
         graph_mode="area", text_mode="auto"):
    field = {"unit": unit, "custom": {}}
    if fixed:
        field["color"] = {"mode": "fixed", "fixedColor": fixed}
        field["thresholds"] = {"mode": "absolute", "steps": [{"color": fixed, "value": None}]}
    else:
        field["color"] = {"mode": "thresholds"}
        field["thresholds"] = thresholds or {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}
    if mappings: field["mappings"] = mappings
    if decimals is not None: field["decimals"] = decimals
    return {
        "id": pid, "title": title, "type": "stat",
        "datasource": prom(),
        "targets": [q(expr, title, "A")],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": color_mode, "graphMode": graph_mode,
            "justifyMode": "center", "orientation": "auto",
            "textMode": text_mode, "wideLayout": True,
            "showPercentChange": False, "percentChangeColorMode": "standard"
        },
        "fieldConfig": {"defaults": field, "overrides": []}
    }

def gauge(pid, title, expr, x, y, w, h, *, unit="percent",
          thresholds=None, max_v=100, min_v=0, decimals=None):
    field = {
        "unit": unit, "min": min_v, "max": max_v,
        "color": {"mode": "thresholds"},
        "thresholds": thresholds or {"mode": "absolute", "steps": [
            {"color": "green", "value": None},
            {"color": "yellow", "value": 70},
            {"color": "red", "value": 90}
        ]},
        "custom": {"neutral": 0}
    }
    if decimals is not None: field["decimals"] = decimals
    return {
        "id": pid, "title": title, "type": "gauge",
        "datasource": prom(),
        "targets": [q(expr, title, "A")],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": False, "showThresholdMarkers": True,
            "orientation": "auto", "minVizHeight": 75, "minVizWidth": 75,
            "sizing": "auto"
        },
        "fieldConfig": {"defaults": field, "overrides": []}
    }

def timeseries(pid, title, targets, x, y, w, h, *, unit="short", fill=20,
               line_width=2, overrides=None, legend_mode="list",
               show_legend=True, stacking=False, smooth=True):
    return {
        "id": pid, "title": title, "type": "timeseries",
        "datasource": prom(), "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "tooltip": {"mode": "multi", "sort": "desc"},
            "legend": {
                "displayMode": legend_mode if show_legend else "hidden",
                "placement": "bottom",
                "calcs": ["mean", "max"] if legend_mode == "table" else [],
                "showLegend": show_legend
            }
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "smooth" if smooth else "linear",
                    "lineWidth": line_width, "fillOpacity": fill,
                    "gradientMode": "opacity", "spanNulls": True,
                    "showPoints": "never", "pointSize": 5,
                    "stacking": {"mode": "normal" if stacking else "none", "group": "A"},
                    "axisLabel": "", "axisPlacement": "auto",
                    "scaleDistribution": {"type": "linear"},
                    "thresholdsStyle": {"mode": "off"},
                    "barAlignment": 0, "axisCenteredZero": False,
                    "lineStyle": {"fill": "solid"}
                }
            },
            "overrides": overrides or []
        }
    }

def heatmap_panel(pid, title, expr, x, y, w, h):
    return {
        "id": pid, "title": title, "type": "heatmap",
        "datasource": prom(),
        "targets": [q(expr, "{{le}}", "A")],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "calculate": False,
            "yAxis": {"unit": "s", "decimals": 2},
            "color": {"scheme": "Spectral", "mode": "scheme",
                      "exponent": 0.5, "reverse": True, "steps": 64,
                      "fill": "dark-orange"},
            "tooltip": {"show": True, "yHistogram": False, "mode": "single"},
            "legend": {"show": True},
            "rowsFrame": {"layout": "auto", "value": "Count"},
            "cellGap": 1, "filterValues": {"le": 1e-9},
            "exemplars": {"color": "rgba(255,0,255,0.7)"}
        },
        "fieldConfig": {
            "defaults": {"custom": {
                "scaleDistribution": {"type": "log", "log": 2},
                "hideFrom": {"tooltip": False, "viz": False, "legend": False}
            }},
            "overrides": []
        }
    }

def state_timeline(pid, title, targets, x, y, w, h, *, mappings=None, thresholds=None):
    return {
        "id": pid, "title": title, "type": "state-timeline",
        "datasource": prom(), "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "mergeValues": True, "showValue": "never",
            "alignValue": "center", "rowHeight": 0.85,
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "single"}, "perPage": 20
        },
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "thresholds": thresholds or {"mode": "absolute", "steps": [
                    {"color": "red", "value": None},
                    {"color": "green", "value": 1}
                ]},
                "mappings": mappings or [{"type": "value", "options": {
                    "0": {"text": "DOWN", "color": "red", "index": 0},
                    "1": {"text": "UP", "color": "green", "index": 1}
                }}],
                "custom": {"lineWidth": 0, "fillOpacity": 80}
            },
            "overrides": []
        }
    }

def piechart(pid, title, targets, x, y, w, h, *, donut=True, unit="short"):
    return {
        "id": pid, "title": title, "type": "piechart",
        "datasource": prom(), "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "pieType": "donut" if donut else "pie",
            "tooltip": {"mode": "single"},
            "legend": {
                "displayMode": "table", "placement": "right",
                "values": ["value", "percent"], "showLegend": True
            },
            "displayLabels": ["percent"]
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "palette-classic"},
                "custom": {"hideFrom": {"tooltip": False, "viz": False, "legend": False}},
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}
            },
            "overrides": []
        }
    }

def logs_panel(pid, title, expr, x, y, w, h, *, wrap=True):
    return {
        "id": pid, "title": title, "type": "logs",
        "datasource": loki_ds(),
        "targets": [ql(expr, "A")],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "showTime": True, "showLabels": False, "showCommonLabels": False,
            "wrapLogMessage": wrap, "prettifyLogMessage": False,
            "enableLogDetails": True, "dedupStrategy": "none",
            "sortOrder": "Descending"
        },
        "fieldConfig": {"defaults": {}, "overrides": []}
    }

def logs_volume(pid, title, expr, x, y, w, h):
    return {
        "id": pid, "title": title, "type": "timeseries",
        "datasource": loki_ds(),
        "targets": [{"datasource": loki_ds(), "expr": expr, "refId": "A",
                     "queryType": "range", "legendFormat": "{{level}}"}],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "tooltip": {"mode": "multi", "sort": "desc"},
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True}
        },
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "custom": {
                    "drawStyle": "bars",
                    "lineWidth": 0, "fillOpacity": 80,
                    "gradientMode": "none", "spanNulls": False,
                    "showPoints": "never", "barAlignment": 0,
                    "stacking": {"mode": "normal", "group": "A"},
                    "axisLabel": "", "axisPlacement": "auto",
                    "scaleDistribution": {"type": "linear"},
                    "thresholdsStyle": {"mode": "off"}
                }
            },
            "overrides": [
                {"matcher": {"id": "byName", "options": "info"}, "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}]},
                {"matcher": {"id": "byName", "options": "warning"}, "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]},
                {"matcher": {"id": "byName", "options": "error"}, "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                {"matcher": {"id": "byName", "options": "critical"}, "properties": [
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "dark-red"}}]},
            ]
        }
    }

def row(pid, title, y):
    return {
        "id": pid, "title": title, "type": "row",
        "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": []
    }

# ════════════════════════════════════════════════════════════════════════════
# Threshold presets
# ════════════════════════════════════════════════════════════════════════════

UP_DOWN_MAP = [{"type": "value", "options": {
    "0": {"text": "DOWN", "color": "red", "index": 0},
    "1": {"text": "UP", "color": "green", "index": 1}
}}]
PCT = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 70},
    {"color": "red", "value": 90}
]}
PCT_INV = {"mode": "absolute", "steps": [
    {"color": "red", "value": None},
    {"color": "yellow", "value": 80},
    {"color": "green", "value": 95}
]}
LATENCY = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 0.5},
    {"color": "red", "value": 1.5}
]}
ERR = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 1},
    {"color": "red", "value": 5}
]}

panels = []
pid = 1

# ════════════════════════════════════════════════════════════════════════════
# 1. EXECUTIVE SUMMARY (always visible)
# ════════════════════════════════════════════════════════════════════════════
y = 0

panels.append(stat(pid, "Services Online",
    'sum(up)', 0, y, 4, 4, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 3},
        {"color": "green", "value": 5}
    ]})); pid += 1

panels.append(stat(pid, "API Requests",
    'sum(rate(http_requests_total[2m]))', 4, y, 4, 4,
    unit="reqps", color_mode="value", fixed="blue", decimals=1)); pid += 1

panels.append(stat(pid, "Latency p95",
    'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))',
    8, y, 4, 4, unit="s", thresholds=LATENCY, decimals=3)); pid += 1

panels.append(stat(pid, "Error Rate",
    'sum(rate(http_requests_total{status=~"4xx|5xx"}[5m])) / clamp_min(sum(rate(http_requests_total[5m])), 0.001) * 100',
    12, y, 4, 4, unit="percent", thresholds=ERR, decimals=2)); pid += 1

panels.append(stat(pid, "CPU Usage",
    '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
    16, y, 4, 4, unit="percent", thresholds=PCT, decimals=1)); pid += 1

panels.append(stat(pid, "Memory Usage",
    '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
    20, y, 4, 4, unit="percent", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 75},
        {"color": "red", "value": 90}
    ]}, decimals=1)); pid += 1
y += 4

# ════════════════════════════════════════════════════════════════════════════
# 2. SERVICE HEALTH
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Service Health", y)); pid += 1
y += 1

panels.append(state_timeline(pid, "Service Availability",
    [
        q('up{job="rwa-api"}', "RWA API", "A"),
        q('up{job="postgres"}', "PostgreSQL", "B"),
        q('up{job="redis"}', "Redis", "C"),
        q('up{job="node-exporter"}', "System", "D"),
        q('up{job="prometheus"}', "Prometheus", "E"),
        q('up{job="fabric-peer-bnp"}', "Fabric BANK01", "F"),
        q('up{job="fabric-peer-amf"}', "Fabric REG01", "G"),
        q('up{job="couchdb-bnp"}', "CouchDB BANK01", "H"),
        q('up{job="couchdb-amf"}', "CouchDB REG01", "I"),
        q('up{job="celery"}', "Celery", "J"),
    ],
    0, y, 24, 7)); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# 3. API GATEWAY
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "API Gateway", y)); pid += 1
y += 1

panels.append(timeseries(pid, "Request Rate by Status",
    [q('sum by(status) (rate(http_requests_total[2m]))', "{{status}}", "A")],
    0, y, 12, 8, unit="reqps", fill=25, stacking=True,
    legend_mode="table",
    overrides=[
        {"matcher": {"id": "byName", "options": "2xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "3xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}]},
        {"matcher": {"id": "byName", "options": "4xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]},
        {"matcher": {"id": "byName", "options": "5xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1

panels.append(heatmap_panel(pid, "Latency Distribution",
    'sum(rate(http_request_duration_seconds_bucket[2m])) by (le)',
    12, y, 12, 8)); pid += 1
y += 8

# ════════════════════════════════════════════════════════════════════════════
# 4. LIVE LOGS
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Live Logs", y)); pid += 1
y += 1

panels.append(logs_volume(pid, "Log Volume by Severity",
    'sum by(level) (count_over_time({job=~"rwa|systemd|docker"}[1m]))',
    0, y, 24, 5)); pid += 1
y += 5

panels.append(logs_panel(pid, "API Logs",
    '{job="rwa", service=~"uvicorn|grpc|celery"} | json | line_format "[{{.level}}] {{.logger}} {{.message}}"',
    0, y, 12, 12)); pid += 1

panels.append(logs_panel(pid, "Container Logs",
    '{job="docker"} != "level=debug" != "GET /metrics"',
    12, y, 12, 12)); pid += 1
y += 12

panels.append(logs_panel(pid, "System Errors",
    '{job="systemd"} |~ "(?i)error|fail|critical|panic"',
    0, y, 24, 8)); pid += 1
y += 8

# ════════════════════════════════════════════════════════════════════════════
# 5. INFRASTRUCTURE
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Infrastructure", y)); pid += 1
y += 1

panels.append(gauge(pid, "CPU",
    '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
    0, y, 4, 6, unit="percent", thresholds=PCT, decimals=1)); pid += 1

panels.append(gauge(pid, "Memory",
    '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
    4, y, 4, 6, unit="percent", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 75},
        {"color": "red", "value": 90}
    ]}, decimals=1)); pid += 1

panels.append(gauge(pid, "Disk",
    '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)',
    8, y, 4, 6, unit="percent", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 70},
        {"color": "red", "value": 85}
    ]}, decimals=1)); pid += 1

panels.append(gauge(pid, "PG Cache Hit",
    'sum(pg_stat_database_blks_hit) / clamp_min(sum(pg_stat_database_blks_hit) + sum(pg_stat_database_blks_read), 1) * 100',
    12, y, 4, 6, unit="percent", thresholds=PCT_INV, decimals=2)); pid += 1

panels.append(gauge(pid, "Redis Hit Rate",
    'redis_keyspace_hits_total / clamp_min(redis_keyspace_hits_total + redis_keyspace_misses_total, 1) * 100',
    16, y, 4, 6, unit="percent", thresholds=PCT_INV, decimals=2)); pid += 1

panels.append(gauge(pid, "AML Score",
    'avg(rwa_aml_score_avg)',
    20, y, 4, 6, unit="percentunit", max_v=1, decimals=2,
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 0.5},
        {"color": "red", "value": 0.8}
    ]})); pid += 1
y += 6

panels.append(timeseries(pid, "CPU and Memory",
    [
        q('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)', "CPU %", "A"),
        q('(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100', "Memory %", "B"),
    ],
    0, y, 8, 7, unit="percent", fill=25, line_width=2,
    legend_mode="table",
    overrides=[
        {"matcher": {"id": "byName", "options": "CPU %"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}]},
        {"matcher": {"id": "byName", "options": "Memory %"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "purple"}}]},
    ])); pid += 1

panels.append(timeseries(pid, "Disk and Network I/O",
    [
        q('sum(rate(node_disk_read_bytes_total[2m]))', "Disk Read", "A"),
        q('sum(rate(node_disk_written_bytes_total[2m]))', "Disk Write", "B"),
        q('sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Net In", "C"),
        q('sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Net Out", "D"),
    ],
    8, y, 8, 7, unit="Bps", fill=15, line_width=2,
    legend_mode="table",
    overrides=[
        {"matcher": {"id": "byName", "options": "Disk Write"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
        {"matcher": {"id": "byName", "options": "Net Out"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]},
    ])); pid += 1

panels.append(timeseries(pid, "PostgreSQL and Redis",
    [
        q('sum(rate(pg_stat_database_xact_commit{datname="rwadb"}[2m]))', "PG Commits/s", "A"),
        q('rate(redis_commands_processed_total[2m])', "Redis Cmds/s", "B"),
        q('sum(pg_stat_activity_count{state="active"})', "PG Active", "C"),
        q('redis_connected_clients', "Redis Clients", "D"),
    ],
    16, y, 8, 7, unit="short", fill=15, line_width=2,
    legend_mode="table",
    overrides=[
        {"matcher": {"id": "byName", "options": "PG Commits/s"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "Redis Cmds/s"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# 6. BLOCKCHAIN BUSINESS
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Blockchain Business", y)); pid += 1
y += 1

panels.append(stat(pid, "Total Assets",
    'sum(rwa_assets_by_status)', 0, y, 4, 5,
    unit="short", color_mode="value", fixed="purple")); pid += 1

panels.append(stat(pid, "KYC Expiring",
    'sum(rwa_kyc_expiring_count)', 4, y, 4, 5, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 5},
        {"color": "red", "value": 20}
    ]})); pid += 1

panels.append(stat(pid, "Compliance Blocks",
    'sum(rwa_compliance_blocks_total)', 8, y, 4, 5, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 10},
        {"color": "red", "value": 50}
    ]})); pid += 1

panels.append(stat(pid, "Circuit Breaker",
    'max(rwa_circuit_breaker_state)', 12, y, 4, 5,
    color_mode="background", graph_mode="none",
    mappings=[{"type": "value", "options": {
        "0": {"text": "CLOSED", "color": "green", "index": 0},
        "1": {"text": "OPEN", "color": "red", "index": 1},
        "2": {"text": "HALF-OPEN", "color": "yellow", "index": 2}
    }}],
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "red", "value": 1}
    ]})); pid += 1

panels.append(piechart(pid, "Assets by Status",
    [q('rwa_assets_by_status', "{{status}}", "A")],
    16, y, 8, 5)); pid += 1
y += 5

panels.append(piechart(pid, "Compliance Blocks by Reason",
    [q('rwa_compliance_blocks_total', "{{blocked_by}}", "A")],
    0, y, 8, 7)); pid += 1

panels.append(piechart(pid, "Celery Tasks by Type",
    [q('sum by(task_name) (rwa_celery_tasks_total)', "{{task_name}}", "A")],
    8, y, 8, 7)); pid += 1

panels.append(timeseries(pid, "Celery Task Rate",
    [q('sum by(status) (rate(rwa_celery_tasks_total[2m]))', "{{status}}", "A")],
    16, y, 8, 7, unit="ops", fill=25, stacking=True,
    legend_mode="list",
    overrides=[
        {"matcher": {"id": "byName", "options": "success"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "failure"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# Build dashboard
# ════════════════════════════════════════════════════════════════════════════
dash = {
    "uid": "rwa-platform",
    "title": "RWA Platform",
    "tags": ["rwa", "blockchain", "production"],
    "timezone": "browser",
    "refresh": "30s",
    "schemaVersion": 38,
    "version": 1,
    "panels": panels,
    "time": {"from": "now-1h", "to": "now"},
    "timepicker": {},
    "graphTooltip": 1,
    "fiscalYearStartMonth": 0,
    "liveNow": False,
    "weekStart": "",
    "annotations": {"list": []},
    "templating": {"list": []}
}

for uid in ["rwa-ops-v2", "rwa-ops-professional", "rwa-monitoring"]:
    dr = requests.delete(f"{GRAFANA}/api/dashboards/uid/{uid}", auth=AUTH, timeout=10)
    print(f"Delete {uid}: HTTP {dr.status_code}")

with open("deployment/monitoring/grafana_dashboard.json", "w") as f:
    json.dump(dash, f, indent=2)
print(f"Saved JSON ({len(panels)} panels)")

r = requests.post(
    f"{GRAFANA}/api/dashboards/db",
    json={"dashboard": dash, "overwrite": True, "folderId": 0},
    headers={"Content-Type": "application/json"},
    auth=AUTH, timeout=15
)
print(f"Deploy HTTP {r.status_code}: {r.json()}")
