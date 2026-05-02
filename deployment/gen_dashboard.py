import json, requests

GRAFANA = "http://10.10.10.150:3000"
AUTH    = ("admin", "admin")
DS      = "ffgx1hbr25a0wc"

def ds_ref():
    return {"type": "prometheus", "uid": DS}

def t(expr, legend="", ref="A"):
    return {
        "datasource": ds_ref(),
        "expr": expr,
        "legendFormat": legend or "__auto",
        "refId": ref,
        "instant": False,
        "range": True,
    }

def row_panel(id, title, y):
    return {
        "id": id, "title": title, "type": "row",
        "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}
    }

def stat(id, title, targets, gridPos, unit="short", color_mode="background",
         graph_mode="area", thresholds=None, mappings=None, decimals=None,
         fixed_color=None):
    defaults = {
        "unit": unit,
        "color": {"mode": "thresholds"} if not fixed_color else {"mode": "fixed", "fixedColor": fixed_color},
        "thresholds": thresholds or {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
        "custom": {}
    }
    if mappings:
        defaults["mappings"] = mappings
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "id": id, "title": title, "type": "stat",
        "datasource": ds_ref(),
        "targets": targets,
        "gridPos": gridPos,
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": color_mode,
            "graphMode": graph_mode,
            "justifyMode": "center",
            "orientation": "auto",
            "textMode": "auto"
        },
        "fieldConfig": {"defaults": defaults, "overrides": []}
    }

def timeseries(id, title, targets, gridPos, unit="short", fill=10,
               grad="opacity", legend_calcs=None, overrides=None, line_width=2):
    return {
        "id": id, "title": title, "type": "timeseries",
        "datasource": ds_ref(),
        "targets": targets,
        "gridPos": gridPos,
        "options": {
            "tooltip": {"mode": "multi"},
            "legend": {
                "displayMode": "table" if legend_calcs else "list",
                "placement": "bottom",
                "calcs": legend_calcs or []
            }
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "lineWidth": line_width,
                    "fillOpacity": fill,
                    "gradientMode": grad,
                    "spanNulls": True
                }
            },
            "overrides": overrides or []
        }
    }

def bargauge(id, title, targets, gridPos, unit="short", orientation="horizontal", display_mode="gradient"):
    return {
        "id": id, "title": title, "type": "bargauge",
        "datasource": ds_ref(),
        "targets": targets,
        "gridPos": gridPos,
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": orientation,
            "displayMode": display_mode,
            "valueMode": "color",
            "minVizHeight": 10,
            "minVizWidth": 0,
            "text": {}
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "palette-classic"},
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}
            },
            "overrides": []
        }
    }

panels = []
pid = 1

# ─── Row 1: Service Health ─────────────────────────────────────────────────────
y = 0
panels.append(row_panel(pid, "Service Health", y)); pid += 1
y += 1

panels.append({
    "id": pid, "title": "Service Availability",
    "type": "state-timeline",
    "datasource": ds_ref(),
    "targets": [
        t('up{job="node-exporter"}', "System", "A"),
        t('up{job="rwa-api"}', "RWA API", "B"),
        t('up{job="postgres"}', "PostgreSQL", "C"),
        t('up{job="redis"}', "Redis", "D"),
        t('up{job="prometheus"}', "Prometheus", "E"),
    ],
    "gridPos": {"x": 0, "y": y, "w": 24, "h": 6},
    "options": {
        "mergeValues": True,
        "showValue": "never",
        "alignValue": "center",
        "rowHeight": 0.85,
        "legend": {"displayMode": "list", "placement": "bottom"},
        "tooltip": {"mode": "single"}
    },
    "fieldConfig": {
        "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "red", "value": None},
                {"color": "green", "value": 1}
            ]},
            "mappings": [{"type": "value", "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1}
            }}],
            "custom": {"lineWidth": 0, "fillOpacity": 80}
        },
        "overrides": []
    }
})
pid += 1
y += 6

# ─── Row 2: System Resources ───────────────────────────────────────────────────
panels.append(row_panel(pid, "System Resources", y)); pid += 1
y += 1

GREEN_YELLOW_RED = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 70},
    {"color": "red", "value": 90}
]}

panels.append(stat(pid, "CPU Usage",
    [t('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)', "CPU %")],
    {"x": 0, "y": y, "w": 4, "h": 4},
    unit="percent", thresholds=GREEN_YELLOW_RED))
pid += 1

panels.append(stat(pid, "Memory Usage",
    [t('(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100', "RAM %")],
    {"x": 4, "y": y, "w": 4, "h": 4},
    unit="percent",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 75},
        {"color": "red", "value": 90}
    ]}))
pid += 1

panels.append(stat(pid, "Disk Usage",
    [t('100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)', "Disk %")],
    {"x": 8, "y": y, "w": 4, "h": 4},
    unit="percent",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 70},
        {"color": "red", "value": 85}
    ]}))
pid += 1

panels.append(stat(pid, "Load Average (1m)",
    [t('node_load1', "Load")],
    {"x": 12, "y": y, "w": 4, "h": 4},
    unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 2},
        {"color": "red", "value": 4}
    ]}))
pid += 1

panels.append(stat(pid, "Network In",
    [t('sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "In")],
    {"x": 16, "y": y, "w": 4, "h": 4},
    unit="Bps", color_mode="value", fixed_color="blue",
    thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]}))
pid += 1

panels.append(stat(pid, "Network Out",
    [t('sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Out")],
    {"x": 20, "y": y, "w": 4, "h": 4},
    unit="Bps", color_mode="value", fixed_color="orange",
    thresholds={"mode": "absolute", "steps": [{"color": "orange", "value": None}]}))
pid += 1
y += 4

panels.append(timeseries(pid, "CPU Mode Breakdown",
    [
        t('avg(rate(node_cpu_seconds_total{mode="user"}[2m])) * 100', "User", "A"),
        t('avg(rate(node_cpu_seconds_total{mode="system"}[2m])) * 100', "System", "B"),
        t('avg(rate(node_cpu_seconds_total{mode="iowait"}[2m])) * 100', "I/O Wait", "C"),
    ],
    {"x": 0, "y": y, "w": 12, "h": 8},
    unit="percent", fill=12, grad="opacity",
    legend_calcs=["mean", "max"]))
pid += 1

panels.append(timeseries(pid, "Memory Breakdown",
    [
        t('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes', "Used", "A"),
        t('node_memory_Buffers_bytes + node_memory_Cached_bytes', "Cache and Buffers", "B"),
        t('node_memory_MemAvailable_bytes', "Available", "C"),
    ],
    {"x": 12, "y": y, "w": 12, "h": 8},
    unit="bytes", fill=15, grad="opacity",
    legend_calcs=["mean", "last"]))
pid += 1
y += 8

panels.append(timeseries(pid, "Disk I/O",
    [
        t('rate(node_disk_read_bytes_total[2m])', "Read", "A"),
        t('rate(node_disk_written_bytes_total[2m])', "Write", "B"),
    ],
    {"x": 0, "y": y, "w": 12, "h": 7},
    unit="Bps", fill=8, grad="opacity",
    overrides=[
        {"matcher": {"id": "byName", "options": "Write"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}
        ]}
    ]))
pid += 1

panels.append(timeseries(pid, "Network Throughput",
    [
        t('sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Receive", "A"),
        t('sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Transmit", "B"),
    ],
    {"x": 12, "y": y, "w": 12, "h": 7},
    unit="Bps", fill=8, grad="opacity"))
pid += 1
y += 7

# ─── Row 3: API Performance ────────────────────────────────────────────────────
panels.append(row_panel(pid, "API Performance", y)); pid += 1
y += 1

panels.append(stat(pid, "Request Rate",
    [t('sum(rate(http_requests_total[2m]))', "req/s")],
    {"x": 0, "y": y, "w": 4, "h": 4},
    unit="reqps", color_mode="value", fixed_color="blue",
    thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]}))
pid += 1

panels.append(stat(pid, "Error Rate",
    [t('sum(rate(http_requests_total{status=~"5.."}[2m])) / sum(rate(http_requests_total[2m])) * 100', "Error %")],
    {"x": 4, "y": y, "w": 4, "h": 4},
    unit="percent",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 1},
        {"color": "red", "value": 5}
    ]}))
pid += 1

panels.append(stat(pid, "Latency p50",
    [t('histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p50")],
    {"x": 8, "y": y, "w": 4, "h": 4},
    unit="s",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 0.5},
        {"color": "red", "value": 1}
    ]}))
pid += 1

panels.append(stat(pid, "Latency p95",
    [t('histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p95")],
    {"x": 12, "y": y, "w": 4, "h": 4},
    unit="s",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 1},
        {"color": "red", "value": 2}
    ]}))
pid += 1

panels.append(stat(pid, "Latency p99",
    [t('histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p99")],
    {"x": 16, "y": y, "w": 4, "h": 4},
    unit="s",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 2},
        {"color": "red", "value": 5}
    ]}))
pid += 1

panels.append(stat(pid, "Total Requests (1h)",
    [t('sum(increase(http_requests_total[1h]))', "1h total")],
    {"x": 20, "y": y, "w": 4, "h": 4},
    unit="short", color_mode="value", fixed_color="purple",
    thresholds={"mode": "absolute", "steps": [{"color": "purple", "value": None}]}))
pid += 1
y += 4

panels.append(timeseries(pid, "Request Rate by Endpoint",
    [t('sum by(handler) (rate(http_requests_total[2m]))', "{{handler}}", "A")],
    {"x": 0, "y": y, "w": 12, "h": 8},
    unit="reqps", fill=5, grad="none",
    legend_calcs=["mean", "max"]))
pid += 1

panels.append({
    "id": pid, "title": "Request Latency Distribution",
    "type": "heatmap",
    "datasource": ds_ref(),
    "targets": [t('sum(rate(http_request_duration_seconds_bucket[2m])) by (le)', "{{le}}", "A")],
    "gridPos": {"x": 12, "y": y, "w": 12, "h": 8},
    "options": {
        "calculate": False,
        "yAxis": {"unit": "s"},
        "color": {"scheme": "Oranges", "mode": "scheme", "exponent": 0.5},
        "tooltip": {"show": True, "yHistogram": False},
        "legend": {"show": True}
    },
    "fieldConfig": {
        "defaults": {"custom": {"scaleDistribution": {"type": "log", "log": 2}}},
        "overrides": []
    }
})
pid += 1
y += 8

panels.append(timeseries(pid, "Latency Percentiles Over Time",
    [
        t('histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p50", "A"),
        t('histogram_quantile(0.90, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p90", "B"),
        t('histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p99", "C"),
    ],
    {"x": 0, "y": y, "w": 12, "h": 7},
    unit="s", fill=10, grad="opacity",
    overrides=[
        {"matcher": {"id": "byName", "options": "p50"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "p90"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
        {"matcher": {"id": "byName", "options": "p99"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ]))
pid += 1

panels.append(bargauge(pid, "Requests by HTTP Status",
    [t('sum by(status) (rate(http_requests_total[5m]))', "{{status}}", "A")],
    {"x": 12, "y": y, "w": 12, "h": 7},
    unit="reqps", orientation="horizontal", display_mode="gradient"))
pid += 1
y += 7

# ─── Row 4: PostgreSQL ─────────────────────────────────────────────────────────
panels.append(row_panel(pid, "PostgreSQL", y)); pid += 1
y += 1

PG_UP_MAP = [{"type": "value", "options": {
    "0": {"text": "DOWN", "color": "red", "index": 0},
    "1": {"text": "UP", "color": "green", "index": 1}
}}]
PG_UP_THRESH = {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}

panels.append(stat(pid, "Status",
    [t('pg_up', "PG")],
    {"x": 0, "y": y, "w": 3, "h": 4},
    graph_mode="none", mappings=PG_UP_MAP,
    thresholds=PG_UP_THRESH))
pid += 1

panels.append(stat(pid, "Active Connections",
    [t('pg_stat_activity_count{state="active"}', "Active")],
    {"x": 3, "y": y, "w": 3, "h": 4},
    unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 50},
        {"color": "red", "value": 100}
    ]}))
pid += 1

panels.append(stat(pid, "Database Size",
    [t('sum(pg_database_size_bytes)', "Size")],
    {"x": 6, "y": y, "w": 3, "h": 4},
    unit="bytes", color_mode="value", fixed_color="blue",
    thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]}))
pid += 1

panels.append(stat(pid, "Cache Hit Ratio",
    [t('sum(pg_stat_database_blks_hit) / (sum(pg_stat_database_blks_hit) + sum(pg_stat_database_blks_read) + 1) * 100', "Hit %")],
    {"x": 9, "y": y, "w": 3, "h": 4},
    unit="percent",
    thresholds={"mode": "absolute", "steps": [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 80},
        {"color": "green", "value": 95}
    ]}))
pid += 1

panels.append(timeseries(pid, "Transaction Rate",
    [
        t('sum(rate(pg_stat_database_xact_commit[2m]))', "Commits", "A"),
        t('sum(rate(pg_stat_database_xact_rollback[2m]))', "Rollbacks", "B"),
    ],
    {"x": 12, "y": y, "w": 12, "h": 8},
    unit="ops", fill=10, grad="opacity",
    legend_calcs=["mean", "max"],
    overrides=[
        {"matcher": {"id": "byName", "options": "Rollbacks"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}
        ]}
    ]))
pid += 1
y += 4

panels.append(timeseries(pid, "Connection States",
    [
        t('pg_stat_activity_count{state="active"}', "Active", "A"),
        t('pg_stat_activity_count{state="idle"}', "Idle", "B"),
        t('pg_stat_activity_count{state="idle in transaction"}', "Idle in Transaction", "C"),
    ],
    {"x": 0, "y": y, "w": 12, "h": 7},
    unit="short", fill=8, grad="opacity"))
pid += 1

panels.append(timeseries(pid, "Row Operations",
    [
        t('sum(rate(pg_stat_database_tup_fetched[2m]))', "Fetched", "A"),
        t('sum(rate(pg_stat_database_tup_inserted[2m]))', "Inserted", "B"),
        t('sum(rate(pg_stat_database_tup_updated[2m]))', "Updated", "C"),
        t('sum(rate(pg_stat_database_tup_deleted[2m]))', "Deleted", "D"),
    ],
    {"x": 12, "y": y, "w": 12, "h": 7},
    unit="ops", fill=5, grad="none",
    legend_calcs=["mean"],
    overrides=[
        {"matcher": {"id": "byName", "options": "Deleted"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}
        ]}
    ]))
pid += 1
y += 7

# ─── Row 5: Redis ──────────────────────────────────────────────────────────────
panels.append(row_panel(pid, "Redis", y)); pid += 1
y += 1

REDIS_UP_MAP = [{"type": "value", "options": {
    "0": {"text": "DOWN", "color": "red", "index": 0},
    "1": {"text": "UP", "color": "green", "index": 1}
}}]
REDIS_UP_THRESH = {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}

panels.append(stat(pid, "Status",
    [t('redis_up', "Redis")],
    {"x": 0, "y": y, "w": 3, "h": 4},
    graph_mode="none", mappings=REDIS_UP_MAP,
    thresholds=REDIS_UP_THRESH))
pid += 1

panels.append(stat(pid, "Memory Used",
    [t('redis_memory_used_bytes', "Memory")],
    {"x": 3, "y": y, "w": 3, "h": 4},
    unit="bytes", color_mode="value", fixed_color="orange",
    thresholds={"mode": "absolute", "steps": [{"color": "orange", "value": None}]}))
pid += 1

panels.append(stat(pid, "Connected Clients",
    [t('redis_connected_clients', "Clients")],
    {"x": 6, "y": y, "w": 3, "h": 4},
    unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 100},
        {"color": "red", "value": 500}
    ]}))
pid += 1

panels.append(stat(pid, "Cache Hit Rate",
    [t('redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total + 1) * 100', "Hit %")],
    {"x": 9, "y": y, "w": 3, "h": 4},
    unit="percent",
    thresholds={"mode": "absolute", "steps": [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 70},
        {"color": "green", "value": 90}
    ]}))
pid += 1

panels.append(timeseries(pid, "Commands Per Second",
    [t('rate(redis_commands_total[2m])', "{{cmd}}", "A")],
    {"x": 12, "y": y, "w": 12, "h": 8},
    unit="ops", fill=5, grad="none",
    legend_calcs=["mean", "max"]))
pid += 1
y += 4

panels.append(timeseries(pid, "Memory Over Time",
    [
        t('redis_memory_used_bytes', "Used", "A"),
        t('redis_memory_peak_bytes', "Peak", "B"),
    ],
    {"x": 0, "y": y, "w": 12, "h": 7},
    unit="bytes", fill=12, grad="opacity",
    overrides=[
        {"matcher": {"id": "byName", "options": "Peak"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}},
            {"id": "custom.lineStyle", "value": {"dash": [8, 8], "fill": "dash"}},
            {"id": "custom.fillOpacity", "value": 0}
        ]}
    ]))
pid += 1

panels.append(timeseries(pid, "Cache Hits vs Misses",
    [
        t('rate(redis_keyspace_hits_total[2m])', "Hits", "A"),
        t('rate(redis_keyspace_misses_total[2m])', "Misses", "B"),
    ],
    {"x": 12, "y": y, "w": 12, "h": 7},
    unit="ops", fill=10, grad="opacity",
    overrides=[
        {"matcher": {"id": "byName", "options": "Hits"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}
        ]},
        {"matcher": {"id": "byName", "options": "Misses"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}
        ]}
    ]))
pid += 1
y += 7

# ─── Row 6: RWA Business Metrics ──────────────────────────────────────────────
panels.append(row_panel(pid, "RWA Business Metrics", y)); pid += 1
y += 1

panels.append(stat(pid, "Total Transactions",
    [t('sum(rwa_transactions_total)', "Transactions")],
    {"x": 0, "y": y, "w": 4, "h": 4},
    unit="short", color_mode="value", fixed_color="purple",
    thresholds={"mode": "absolute", "steps": [{"color": "purple", "value": None}]}))
pid += 1

panels.append(stat(pid, "Average AML Score",
    [t('avg(rwa_aml_score_avg)', "AML Score")],
    {"x": 4, "y": y, "w": 4, "h": 4},
    unit="percentunit", decimals=2,
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 0.5},
        {"color": "red", "value": 0.8}
    ]}))
pid += 1

panels.append(stat(pid, "KYC Expiring Soon",
    [t('sum(rwa_kyc_expiring_count)', "KYC")],
    {"x": 8, "y": y, "w": 4, "h": 4},
    unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 5},
        {"color": "red", "value": 20}
    ]}))
pid += 1

panels.append(stat(pid, "Compliance Blocks",
    [t('sum(rwa_compliance_blocks_total)', "Blocks")],
    {"x": 12, "y": y, "w": 4, "h": 4},
    unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 10},
        {"color": "red", "value": 50}
    ]}))
pid += 1

panels.append(stat(pid, "Celery Tasks Total",
    [t('sum(rwa_celery_tasks_total)', "Tasks")],
    {"x": 16, "y": y, "w": 4, "h": 4},
    unit="short", color_mode="value", fixed_color="blue",
    thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]}))
pid += 1

panels.append(stat(pid, "Circuit Breaker",
    [t('max(rwa_circuit_breaker_state)', "State")],
    {"x": 20, "y": y, "w": 4, "h": 4},
    graph_mode="none",
    mappings=[{"type": "value", "options": {
        "0": {"text": "CLOSED", "color": "green", "index": 0},
        "1": {"text": "OPEN", "color": "red", "index": 1},
        "2": {"text": "HALF-OPEN", "color": "yellow", "index": 2}
    }}],
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "red", "value": 1}
    ]}))
pid += 1
y += 4

panels.append(bargauge(pid, "Assets by Status",
    [t('rwa_assets_by_status', "{{status}}", "A")],
    {"x": 0, "y": y, "w": 8, "h": 8},
    unit="short", orientation="horizontal", display_mode="gradient"))
pid += 1

panels.append(timeseries(pid, "Transaction Rate Over Time",
    [t('rate(rwa_transactions_total[2m])', "{{type}}", "A")],
    {"x": 8, "y": y, "w": 16, "h": 8},
    unit="ops", fill=15, grad="opacity",
    legend_calcs=["mean", "max"]))
pid += 1
y += 8

panels.append(timeseries(pid, "Compliance Block Rate",
    [t('rate(rwa_compliance_blocks_total[5m])', "{{reason}}", "A")],
    {"x": 0, "y": y, "w": 12, "h": 7},
    unit="ops", fill=10, grad="opacity"))
pid += 1

panels.append(timeseries(pid, "AML Score Trend",
    [t('avg(rwa_aml_score_avg)', "AML Score", "A")],
    {"x": 12, "y": y, "w": 12, "h": 7},
    unit="percentunit", fill=20, grad="opacity",
    overrides=[
        {"matcher": {"id": "byName", "options": "AML Score"}, "properties": [
            {"id": "custom.thresholdsStyle", "value": {"mode": "area"}},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                {"color": "green", "value": None},
                {"color": "yellow", "value": 0.5},
                {"color": "red", "value": 0.8}
            ]}}
        ]}
    ]))
pid += 1
y += 7

# ─── Row 7: Blockchain and Infrastructure ─────────────────────────────────────
panels.append(row_panel(pid, "Blockchain and Infrastructure", y)); pid += 1
y += 1

panels.append(stat(pid, "Chaincode Duration p50",
    [t('histogram_quantile(0.50, sum(rate(rwa_chaincode_duration_seconds_bucket[2m])) by (le))', "p50")],
    {"x": 0, "y": y, "w": 4, "h": 4},
    unit="s",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 0.5},
        {"color": "red", "value": 1}
    ]}))
pid += 1

panels.append(stat(pid, "Chaincode Duration p95",
    [t('histogram_quantile(0.95, sum(rate(rwa_chaincode_duration_seconds_bucket[2m])) by (le))', "p95")],
    {"x": 4, "y": y, "w": 4, "h": 4},
    unit="s",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 1},
        {"color": "red", "value": 3}
    ]}))
pid += 1

panels.append(stat(pid, "Celery Task Rate",
    [t('sum(rate(rwa_celery_tasks_total[5m]))', "tasks/s")],
    {"x": 8, "y": y, "w": 4, "h": 4},
    unit="ops", color_mode="value", fixed_color="blue",
    thresholds={"mode": "absolute", "steps": [{"color": "blue", "value": None}]}))
pid += 1

panels.append(stat(pid, "TSDB Head Series",
    [t('prometheus_tsdb_head_series', "Series")],
    {"x": 12, "y": y, "w": 4, "h": 4},
    unit="short", color_mode="value", fixed_color="gray",
    thresholds={"mode": "absolute", "steps": [{"color": "gray", "value": None}]}))
pid += 1

panels.append(stat(pid, "Samples Appended Rate",
    [t('rate(prometheus_tsdb_head_samples_appended_total[2m])', "samples/s")],
    {"x": 16, "y": y, "w": 4, "h": 4},
    unit="short", color_mode="value", fixed_color="gray",
    thresholds={"mode": "absolute", "steps": [{"color": "gray", "value": None}]}))
pid += 1

panels.append(stat(pid, "Active Scrape Targets",
    [t('sum(up)', "Up")],
    {"x": 20, "y": y, "w": 4, "h": 4},
    unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 3},
        {"color": "green", "value": 5}
    ]}))
pid += 1
y += 4

panels.append(timeseries(pid, "Chaincode Duration Percentiles",
    [
        t('histogram_quantile(0.50, sum(rate(rwa_chaincode_duration_seconds_bucket[2m])) by (le))', "p50", "A"),
        t('histogram_quantile(0.95, sum(rate(rwa_chaincode_duration_seconds_bucket[2m])) by (le))', "p95", "B"),
        t('histogram_quantile(0.99, sum(rate(rwa_chaincode_duration_seconds_bucket[2m])) by (le))', "p99", "C"),
    ],
    {"x": 0, "y": y, "w": 12, "h": 7},
    unit="s", fill=10, grad="opacity",
    overrides=[
        {"matcher": {"id": "byName", "options": "p50"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "p95"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
        {"matcher": {"id": "byName", "options": "p99"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ]))
pid += 1

panels.append(timeseries(pid, "Celery Tasks Over Time",
    [t('rate(rwa_celery_tasks_total[2m])', "{{task}}", "A")],
    {"x": 12, "y": y, "w": 12, "h": 7},
    unit="ops", fill=8, grad="none",
    legend_calcs=["mean", "max"]))
pid += 1

# ─── Build & Deploy ────────────────────────────────────────────────────────────
dash = {
    "uid": "rwa-ops-v2",
    "title": "RWA Platform",
    "tags": ["rwa", "production"],
    "timezone": "browser",
    "refresh": "30s",
    "schemaVersion": 38,
    "version": 1,
    "panels": panels,
    "time": {"from": "now-3h", "to": "now"},
    "timepicker": {},
    "graphTooltip": 1
}

# Delete old dashboards
for uid in ["rwa-ops-professional", "rwa-monitoring"]:
    dr = requests.delete(f"{GRAFANA}/api/dashboards/uid/{uid}", auth=AUTH, timeout=10)
    print(f"Delete {uid}: HTTP {dr.status_code}")

# Save JSON artifact
with open("deployment/monitoring/grafana_dashboard.json", "w") as f:
    json.dump(dash, f, indent=2)
print(f"Saved JSON ({len(panels)} panels)")

# Deploy
r = requests.post(
    f"{GRAFANA}/api/dashboards/db",
    json={"dashboard": dash, "overwrite": True, "folderId": 0},
    headers={"Content-Type": "application/json"},
    auth=AUTH, timeout=15
)
print(f"Deploy HTTP {r.status_code}: {r.json()}")
