import json, requests

GRAFANA = "http://10.10.10.150:3000"
AUTH    = ("admin", "admin")
DS      = "ffgx1hbr25a0wc"

def ds():
    return {"type": "prometheus", "uid": DS}

def q(expr, legend="", ref="A"):
    return {
        "datasource": ds(),
        "expr": expr,
        "legendFormat": legend or "__auto",
        "refId": ref,
        "instant": False,
        "range": True,
    }

# ════════════════════════════════════════════════════════════════════════════
# Panel factories
# ════════════════════════════════════════════════════════════════════════════

def stat_panel(pid, title, expr, x, y, w, h, *, unit="short", thresholds=None,
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
        "datasource": ds(),
        "targets": [q(expr, title, "A")] if isinstance(expr, str) else expr,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": color_mode,
            "graphMode": graph_mode,
            "justifyMode": "center",
            "orientation": "auto",
            "textMode": text_mode,
            "wideLayout": True,
            "showPercentChange": False,
            "percentChangeColorMode": "standard"
        },
        "fieldConfig": {"defaults": field, "overrides": []}
    }

def gauge_panel(pid, title, expr, x, y, w, h, *, unit="percent",
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
        "datasource": ds(),
        "targets": [q(expr, title, "A")],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": False,
            "showThresholdMarkers": True,
            "orientation": "auto",
            "minVizHeight": 75, "minVizWidth": 75,
            "sizing": "auto"
        },
        "fieldConfig": {"defaults": field, "overrides": []}
    }

def timeseries(pid, title, targets, x, y, w, h, *, unit="short", fill=18,
               line_width=2, overrides=None, legend_mode="list",
               show_legend=True, stacking=False, smooth=True):
    return {
        "id": pid, "title": title, "type": "timeseries",
        "datasource": ds(),
        "targets": targets,
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
                    "lineWidth": line_width,
                    "fillOpacity": fill,
                    "gradientMode": "opacity",
                    "spanNulls": True,
                    "showPoints": "never",
                    "pointSize": 5,
                    "stacking": {"mode": "normal" if stacking else "none", "group": "A"},
                    "axisLabel": "",
                    "axisPlacement": "auto",
                    "scaleDistribution": {"type": "linear"},
                    "thresholdsStyle": {"mode": "off"},
                    "barAlignment": 0,
                    "axisCenteredZero": False,
                    "lineStyle": {"fill": "solid"}
                }
            },
            "overrides": overrides or []
        }
    }

def heatmap_panel(pid, title, expr, x, y, w, h, *, scheme="Spectral",
                  reverse=True, unit="s"):
    return {
        "id": pid, "title": title, "type": "heatmap",
        "datasource": ds(),
        "targets": [q(expr, "{{le}}", "A")],
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "calculate": False,
            "yAxis": {"unit": unit, "decimals": 2, "axisPlacement": "left"},
            "color": {"scheme": scheme, "mode": "scheme", "exponent": 0.5,
                      "reverse": reverse, "steps": 64, "fill": "dark-orange"},
            "tooltip": {"show": True, "yHistogram": False, "mode": "single"},
            "legend": {"show": True},
            "rowsFrame": {"layout": "auto", "value": "Count"},
            "cellGap": 1,
            "filterValues": {"le": 1e-9},
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
        "datasource": ds(),
        "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "mergeValues": True, "showValue": "never",
            "alignValue": "center", "rowHeight": 0.85,
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "single"},
            "perPage": 20
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

def status_history(pid, title, targets, x, y, w, h, *, mappings=None, thresholds=None):
    return {
        "id": pid, "title": title, "type": "status-history",
        "datasource": ds(),
        "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "showValue": "never",
            "rowHeight": 0.85,
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi"},
            "colWidth": 0.9
        },
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "continuous-GrYlRd"},
                "thresholds": thresholds or {"mode": "absolute", "steps": [
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 50},
                    {"color": "red", "value": 80}
                ]},
                "mappings": mappings or [],
                "custom": {"lineWidth": 1, "fillOpacity": 70}
            },
            "overrides": []
        }
    }

def piechart(pid, title, targets, x, y, w, h, *, donut=True, unit="short",
             show_legend=True):
    return {
        "id": pid, "title": title, "type": "piechart",
        "datasource": ds(),
        "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "pieType": "donut" if donut else "pie",
            "tooltip": {"mode": "single"},
            "legend": {
                "displayMode": "table" if show_legend else "hidden",
                "placement": "right",
                "values": ["value", "percent"],
                "showLegend": show_legend
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

def bargauge(pid, title, targets, x, y, w, h, *, unit="short",
             orientation="horizontal", display_mode="gradient"):
    return {
        "id": pid, "title": title, "type": "bargauge",
        "datasource": ds(),
        "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": orientation,
            "displayMode": display_mode,
            "valueMode": "color",
            "minVizHeight": 10, "minVizWidth": 0,
            "showUnfilled": True,
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

def row(pid, title, y, collapsed=False):
    return {
        "id": pid, "title": title, "type": "row",
        "collapsed": collapsed,
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
UP_DOWN_THRESH = {"mode": "absolute", "steps": [
    {"color": "red", "value": None},
    {"color": "green", "value": 1}
]}
PCT_NORMAL = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 70},
    {"color": "red", "value": 90}
]}
PCT_INVERTED = {"mode": "absolute", "steps": [
    {"color": "red", "value": None},
    {"color": "yellow", "value": 80},
    {"color": "green", "value": 95}
]}
LATENCY_THRESH = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 0.5},
    {"color": "red", "value": 1.5}
]}
ERROR_THRESH = {"mode": "absolute", "steps": [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 1},
    {"color": "red", "value": 5}
]}

panels = []
pid = 1

# ════════════════════════════════════════════════════════════════════════════
# SECTION 1: PLATFORM OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
y = 0
panels.append(row(pid, "Platform Overview", y)); pid += 1
y += 1

panels.append(stat_panel(pid, "Services Up",
    'sum(up)', 0, y, 4, 5, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 3},
        {"color": "green", "value": 5}
    ]})); pid += 1

panels.append(stat_panel(pid, "Request Rate",
    'sum(rate(http_requests_total[2m]))', 4, y, 4, 5,
    unit="reqps", color_mode="value", fixed="blue", decimals=2)); pid += 1

panels.append(stat_panel(pid, "Latency p95",
    'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))',
    8, y, 4, 5, unit="s", thresholds=LATENCY_THRESH, decimals=3)); pid += 1

panels.append(stat_panel(pid, "Error Rate",
    'sum(rate(http_requests_total{status=~"4xx|5xx"}[5m])) / clamp_min(sum(rate(http_requests_total[5m])), 0.001) * 100',
    12, y, 4, 5, unit="percent", thresholds=ERROR_THRESH, decimals=2)); pid += 1

panels.append(stat_panel(pid, "Compliance Blocks",
    'sum(rwa_compliance_blocks_total)', 16, y, 4, 5, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 10},
        {"color": "red", "value": 50}
    ]})); pid += 1

panels.append(stat_panel(pid, "Circuit Breaker",
    'max(rwa_circuit_breaker_state)', 20, y, 4, 5,
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
y += 5

# ════════════════════════════════════════════════════════════════════════════
# SECTION 2: SERVICE TOPOLOGY
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Service Topology", y)); pid += 1
y += 1

panels.append(state_timeline(pid, "Service Availability",
    [
        q('up{job="node-exporter"}', "System", "A"),
        q('up{job="rwa-api"}', "RWA API", "B"),
        q('up{job="postgres"}', "PostgreSQL", "C"),
        q('up{job="redis"}', "Redis", "D"),
        q('up{job="prometheus"}', "Prometheus", "E"),
        q('up{job="fabric-peer-bnp"}', "Fabric BNP", "F"),
        q('up{job="fabric-peer-amf"}', "Fabric AMF", "G"),
        q('up{job="couchdb-bnp"}', "CouchDB BNP", "H"),
        q('up{job="couchdb-amf"}', "CouchDB AMF", "I"),
        q('up{job="celery"}', "Celery", "J"),
    ],
    0, y, 16, 8)); pid += 1

panels.append(piechart(pid, "Targets Up vs Down",
    [
        q('count(up == 1)', "Up", "A"),
        q('count(up == 0)', "Down", "B"),
    ],
    16, y, 8, 8, donut=True)); pid += 1
y += 8

# ════════════════════════════════════════════════════════════════════════════
# SECTION 3: API GATEWAY
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "API Gateway", y)); pid += 1
y += 1

panels.append(timeseries(pid, "Request Rate by Status Class",
    [q('sum by(status) (rate(http_requests_total[2m]))', "{{status}}", "A")],
    0, y, 16, 8, unit="reqps", fill=20, line_width=2,
    legend_mode="table", stacking=True,
    overrides=[
        {"matcher": {"id": "byName", "options": "2xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "3xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}]},
        {"matcher": {"id": "byName", "options": "4xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "yellow"}}]},
        {"matcher": {"id": "byName", "options": "5xx"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1

panels.append(piechart(pid, "Status Code Distribution",
    [q('sum by(status) (increase(http_requests_total[15m]))', "{{status}}", "A")],
    16, y, 8, 8, donut=True)); pid += 1
y += 8

panels.append(heatmap_panel(pid, "Request Latency Distribution",
    'sum(rate(http_request_duration_seconds_bucket[2m])) by (le)',
    0, y, 16, 8, scheme="Spectral", reverse=True, unit="s")); pid += 1

panels.append(timeseries(pid, "Latency Percentiles",
    [
        q('histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p50", "A"),
        q('histogram_quantile(0.90, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p90", "B"),
        q('histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))', "p99", "C"),
    ],
    16, y, 8, 8, unit="s", fill=15, line_width=2,
    legend_mode="list",
    overrides=[
        {"matcher": {"id": "byName", "options": "p50"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "p90"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
        {"matcher": {"id": "byName", "options": "p99"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1
y += 8

panels.append(bargauge(pid, "Top Endpoints by Traffic",
    [q('topk(10, sum by(handler) (rate(http_requests_total[5m])))', "{{handler}}", "A")],
    0, y, 12, 7, unit="reqps")); pid += 1

panels.append(timeseries(pid, "Request Size",
    [q('sum(rate(http_request_size_bytes_sum[2m])) / clamp_min(sum(rate(http_request_size_bytes_count[2m])), 0.001)', "Avg In", "A"),
     q('sum(rate(http_response_size_bytes_sum[2m])) / clamp_min(sum(rate(http_response_size_bytes_count[2m])), 0.001)', "Avg Out", "B")],
    12, y, 12, 7, unit="bytes", fill=15)); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# SECTION 4: BLOCKCHAIN BUSINESS & COMPLIANCE
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Blockchain Business and Compliance", y)); pid += 1
y += 1

# KPI strip
panels.append(stat_panel(pid, "Total Assets",
    'sum(rwa_assets_by_status)', 0, y, 5, 5,
    unit="short", color_mode="value", fixed="purple")); pid += 1

panels.append(gauge_panel(pid, "Average AML Score",
    'avg(rwa_aml_score_avg)', 5, y, 5, 5,
    unit="percentunit", max_v=1, decimals=2,
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 0.5},
        {"color": "red", "value": 0.8}
    ]})); pid += 1

panels.append(stat_panel(pid, "KYC Expiring",
    'sum(rwa_kyc_expiring_count)', 10, y, 5, 5, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 5},
        {"color": "red", "value": 20}
    ]})); pid += 1

panels.append(stat_panel(pid, "Celery Task Rate",
    'sum(rate(rwa_celery_tasks_total[5m]))', 15, y, 4, 5,
    unit="ops", color_mode="value", fixed="blue", decimals=2)); pid += 1

panels.append(stat_panel(pid, "Task Failure Rate",
    'sum(rate(rwa_celery_tasks_total{status="failure"}[5m])) / clamp_min(sum(rate(rwa_celery_tasks_total[5m])), 0.001) * 100',
    19, y, 5, 5, unit="percent", thresholds=ERROR_THRESH, decimals=2)); pid += 1
y += 5

# Distribution row
panels.append(piechart(pid, "Assets by Status",
    [q('rwa_assets_by_status', "{{status}}", "A")],
    0, y, 8, 8, donut=True)); pid += 1

panels.append(piechart(pid, "Compliance Blocks by Reason",
    [q('rwa_compliance_blocks_total', "{{blocked_by}}", "A")],
    8, y, 8, 8, donut=True)); pid += 1

panels.append(piechart(pid, "Celery Tasks by Type",
    [q('sum by(task_name) (rwa_celery_tasks_total)', "{{task_name}}", "A")],
    16, y, 8, 8, donut=True)); pid += 1
y += 8

# Trend row
panels.append(timeseries(pid, "AML Score Trend",
    [q('avg(rwa_aml_score_avg)', "AML Score", "A")],
    0, y, 8, 7, unit="percentunit", fill=30, line_width=3, show_legend=False,
    overrides=[
        {"matcher": {"id": "byName", "options": "AML Score"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "purple"}},
            {"id": "min", "value": 0},
            {"id": "max", "value": 1}
        ]}
    ])); pid += 1

panels.append(timeseries(pid, "Compliance Block Rate",
    [q('rate(rwa_compliance_blocks_total[5m])', "{{blocked_by}}", "A")],
    8, y, 8, 7, unit="ops", fill=20, line_width=2,
    legend_mode="list")); pid += 1

panels.append(timeseries(pid, "Celery Task Rate by Status",
    [q('sum by(status) (rate(rwa_celery_tasks_total[2m]))', "{{status}}", "A")],
    16, y, 8, 7, unit="ops", fill=20, line_width=2, stacking=True,
    legend_mode="list",
    overrides=[
        {"matcher": {"id": "byName", "options": "success"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "failure"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# SECTION 5: POSTGRESQL
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "PostgreSQL", y)); pid += 1
y += 1

panels.append(stat_panel(pid, "Status",
    'pg_up', 0, y, 4, 4, graph_mode="none",
    mappings=UP_DOWN_MAP, thresholds=UP_DOWN_THRESH)); pid += 1

panels.append(stat_panel(pid, "Active Connections",
    'sum(pg_stat_activity_count{state="active"})', 4, y, 4, 4,
    unit="short", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 50},
        {"color": "red", "value": 100}
    ]})); pid += 1

panels.append(stat_panel(pid, "Database Size",
    'pg_database_size_bytes{datname="rwadb"}', 8, y, 4, 4,
    unit="bytes", color_mode="value", fixed="blue")); pid += 1

panels.append(gauge_panel(pid, "Cache Hit Ratio",
    'sum(pg_stat_database_blks_hit) / clamp_min(sum(pg_stat_database_blks_hit) + sum(pg_stat_database_blks_read), 1) * 100',
    12, y, 4, 4, unit="percent", thresholds=PCT_INVERTED, decimals=2)); pid += 1

panels.append(stat_panel(pid, "Total Locks",
    'sum(pg_locks_count)', 16, y, 4, 4, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 50},
        {"color": "red", "value": 200}
    ]})); pid += 1

panels.append(stat_panel(pid, "Replication Lag",
    'max(pg_replication_lag_seconds)', 20, y, 4, 4,
    unit="s", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 5},
        {"color": "red", "value": 30}
    ]}, decimals=2)); pid += 1
y += 4

panels.append(timeseries(pid, "Transaction Rate per Database",
    [
        q('sum by(datname) (rate(pg_stat_database_xact_commit{datname=~"rwadb|rwadb_test|postgres"}[2m]))', "{{datname}} commits", "A"),
        q('sum by(datname) (rate(pg_stat_database_xact_rollback{datname=~"rwadb|rwadb_test|postgres"}[2m]))', "{{datname}} rollbacks", "B"),
    ],
    0, y, 12, 8, unit="ops", fill=15, line_width=2,
    legend_mode="table",
    overrides=[
        {"matcher": {"id": "byRegexp", "options": ".*rollbacks.*"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}
        ]}
    ])); pid += 1

panels.append(timeseries(pid, "Connections by State",
    [q('sum by(state) (pg_stat_activity_count)', "{{state}}", "A")],
    12, y, 12, 8, unit="short", fill=20, line_width=2, stacking=True,
    legend_mode="list")); pid += 1
y += 8

panels.append(timeseries(pid, "Tuple Operations",
    [
        q('sum(rate(pg_stat_database_tup_fetched{datname="rwadb"}[2m]))', "Fetched", "A"),
        q('sum(rate(pg_stat_database_tup_returned{datname="rwadb"}[2m]))', "Returned", "B"),
        q('sum(rate(pg_stat_database_tup_inserted{datname="rwadb"}[2m]))', "Inserted", "C"),
        q('sum(rate(pg_stat_database_tup_updated{datname="rwadb"}[2m]))', "Updated", "D"),
        q('sum(rate(pg_stat_database_tup_deleted{datname="rwadb"}[2m]))', "Deleted", "E"),
    ],
    0, y, 12, 7, unit="ops", fill=10, line_width=2,
    legend_mode="table",
    overrides=[
        {"matcher": {"id": "byName", "options": "Deleted"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}
        ]}
    ])); pid += 1

panels.append(bargauge(pid, "Locks by Mode",
    [q('sum by(mode) (pg_locks_count) > 0', "{{mode}}", "A")],
    12, y, 12, 7, unit="short")); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# SECTION 6: REDIS
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Redis", y)); pid += 1
y += 1

panels.append(stat_panel(pid, "Status",
    'redis_up', 0, y, 4, 4, graph_mode="none",
    mappings=UP_DOWN_MAP, thresholds=UP_DOWN_THRESH)); pid += 1

panels.append(stat_panel(pid, "Memory Used",
    'redis_memory_used_bytes', 4, y, 4, 4,
    unit="bytes", color_mode="value", fixed="orange")); pid += 1

panels.append(stat_panel(pid, "Connected Clients",
    'redis_connected_clients', 8, y, 4, 4, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 100},
        {"color": "red", "value": 500}
    ]})); pid += 1

panels.append(gauge_panel(pid, "Cache Hit Rate",
    'redis_keyspace_hits_total / clamp_min(redis_keyspace_hits_total + redis_keyspace_misses_total, 1) * 100',
    12, y, 4, 4, unit="percent", thresholds=PCT_INVERTED, decimals=2)); pid += 1

panels.append(stat_panel(pid, "Commands per Second",
    'rate(redis_commands_processed_total[2m])', 16, y, 4, 4,
    unit="ops", color_mode="value", fixed="blue", decimals=1)); pid += 1

panels.append(stat_panel(pid, "Blocked Clients",
    'redis_blocked_clients', 20, y, 4, 4, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 1},
        {"color": "red", "value": 5}
    ]})); pid += 1
y += 4

panels.append(timeseries(pid, "Memory Composition",
    [
        q('redis_memory_used_bytes', "Used", "A"),
        q('redis_memory_used_rss_bytes', "RSS", "B"),
        q('redis_memory_used_dataset_bytes', "Dataset", "C"),
    ],
    0, y, 12, 8, unit="bytes", fill=15, line_width=2,
    legend_mode="table")); pid += 1

panels.append(timeseries(pid, "Cache Hits vs Misses",
    [
        q('rate(redis_keyspace_hits_total[2m])', "Hits", "A"),
        q('rate(redis_keyspace_misses_total[2m])', "Misses", "B"),
    ],
    12, y, 12, 8, unit="ops", fill=20, line_width=2,
    legend_mode="list",
    overrides=[
        {"matcher": {"id": "byName", "options": "Hits"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
        {"matcher": {"id": "byName", "options": "Misses"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
    ])); pid += 1
y += 8

panels.append(bargauge(pid, "Top Commands by Time Spent",
    [q('topk(10, rate(redis_commands_duration_seconds_total[5m]))', "{{cmd}}", "A")],
    0, y, 12, 7, unit="percentunit")); pid += 1

panels.append(timeseries(pid, "Network I/O",
    [
        q('rate(redis_net_input_bytes_total[2m])', "Input", "A"),
        q('rate(redis_net_output_bytes_total[2m])', "Output", "B"),
    ],
    12, y, 12, 7, unit="Bps", fill=15, line_width=2,
    legend_mode="list",
    overrides=[
        {"matcher": {"id": "byName", "options": "Output"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}
        ]}
    ])); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# SECTION 7: SYSTEM RESOURCES
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "System Resources", y)); pid += 1
y += 1

panels.append(gauge_panel(pid, "CPU",
    '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
    0, y, 4, 5, unit="percent", thresholds=PCT_NORMAL, decimals=1)); pid += 1

panels.append(gauge_panel(pid, "Memory",
    '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
    4, y, 4, 5, unit="percent", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 75},
        {"color": "red", "value": 90}
    ]}, decimals=1)); pid += 1

panels.append(gauge_panel(pid, "Disk",
    '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)',
    8, y, 4, 5, unit="percent", thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 70},
        {"color": "red", "value": 85}
    ]}, decimals=1)); pid += 1

panels.append(stat_panel(pid, "Load 1m",
    'node_load1', 12, y, 4, 5, unit="short", decimals=2,
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 2},
        {"color": "red", "value": 4}
    ]})); pid += 1

panels.append(stat_panel(pid, "Open File Descriptors",
    'process_open_fds{job="rwa-api"}', 16, y, 4, 5, unit="short",
    color_mode="value", fixed="blue")); pid += 1

panels.append(stat_panel(pid, "Uptime",
    'node_time_seconds - node_boot_time_seconds', 20, y, 4, 5,
    unit="s", color_mode="value", fixed="green")); pid += 1
y += 5

panels.append(status_history(pid, "CPU Usage per Core",
    [q('100 - (rate(node_cpu_seconds_total{mode="idle"}[2m]) * 100)', "Core {{cpu}}", "A")],
    0, y, 24, 6,
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "yellow", "value": 50},
        {"color": "orange", "value": 75},
        {"color": "red", "value": 90}
    ]})); pid += 1
y += 6

panels.append(timeseries(pid, "CPU by Mode",
    [
        q('avg(rate(node_cpu_seconds_total{mode="user"}[2m])) * 100', "User", "A"),
        q('avg(rate(node_cpu_seconds_total{mode="system"}[2m])) * 100', "System", "B"),
        q('avg(rate(node_cpu_seconds_total{mode="iowait"}[2m])) * 100', "I/O Wait", "C"),
        q('avg(rate(node_cpu_seconds_total{mode="softirq"}[2m])) * 100', "Soft IRQ", "D"),
    ],
    0, y, 12, 8, unit="percent", fill=20, line_width=2, stacking=True,
    legend_mode="table")); pid += 1

panels.append(timeseries(pid, "Memory Breakdown",
    [
        q('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes - node_memory_Buffers_bytes - node_memory_Cached_bytes', "Used", "A"),
        q('node_memory_Buffers_bytes', "Buffers", "B"),
        q('node_memory_Cached_bytes', "Cached", "C"),
        q('node_memory_MemFree_bytes', "Free", "D"),
    ],
    12, y, 12, 8, unit="bytes", fill=25, line_width=1, stacking=True,
    legend_mode="table")); pid += 1
y += 8

panels.append(timeseries(pid, "Disk I/O",
    [
        q('sum(rate(node_disk_read_bytes_total[2m]))', "Read", "A"),
        q('sum(rate(node_disk_written_bytes_total[2m]))', "Write", "B"),
    ],
    0, y, 8, 7, unit="Bps", fill=15, line_width=2,
    legend_mode="list",
    overrides=[
        {"matcher": {"id": "byName", "options": "Write"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}}]},
    ])); pid += 1

panels.append(timeseries(pid, "Network Throughput",
    [
        q('sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Receive", "A"),
        q('sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|br.*|veth.*"}[2m]))', "Transmit", "B"),
    ],
    8, y, 8, 7, unit="Bps", fill=15, line_width=2,
    legend_mode="list")); pid += 1

panels.append(bargauge(pid, "Filesystem Usage",
    [q('100 - (node_filesystem_avail_bytes{fstype!~"tmpfs|devtmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|devtmpfs|overlay"} * 100)', "{{mountpoint}}", "A")],
    16, y, 8, 7, unit="percent")); pid += 1
y += 7

# ════════════════════════════════════════════════════════════════════════════
# SECTION 8: PROMETHEUS HEALTH
# ════════════════════════════════════════════════════════════════════════════
panels.append(row(pid, "Observability", y)); pid += 1
y += 1

panels.append(stat_panel(pid, "Active Targets",
    'sum(up)', 0, y, 4, 4, unit="short",
    thresholds={"mode": "absolute", "steps": [
        {"color": "red", "value": None},
        {"color": "yellow", "value": 3},
        {"color": "green", "value": 5}
    ]})); pid += 1

panels.append(stat_panel(pid, "TSDB Head Series",
    'prometheus_tsdb_head_series', 4, y, 4, 4, unit="short",
    color_mode="value", fixed="blue")); pid += 1

panels.append(stat_panel(pid, "Samples Ingested",
    'rate(prometheus_tsdb_head_samples_appended_total[2m])', 8, y, 4, 4,
    unit="ops", color_mode="value", fixed="green", decimals=1)); pid += 1

panels.append(stat_panel(pid, "TSDB Chunks",
    'prometheus_tsdb_head_chunks', 12, y, 4, 4, unit="short",
    color_mode="value", fixed="purple")); pid += 1

panels.append(stat_panel(pid, "Query Rate",
    'rate(prometheus_engine_query_duration_seconds_count[2m])', 16, y, 4, 4,
    unit="ops", color_mode="value", fixed="orange", decimals=2)); pid += 1

panels.append(stat_panel(pid, "Storage Size",
    'prometheus_tsdb_storage_blocks_bytes', 20, y, 4, 4,
    unit="bytes", color_mode="value", fixed="gray")); pid += 1
y += 4

panels.append(timeseries(pid, "Scrape Duration p95 by Job",
    [q('histogram_quantile(0.95, sum by(job, le) (rate(scrape_duration_seconds_bucket[5m]))) or sum by(job) (scrape_duration_seconds)', "{{job}}", "A")],
    0, y, 12, 7, unit="s", fill=15, line_width=2,
    legend_mode="table")); pid += 1

panels.append(timeseries(pid, "Samples per Scrape by Job",
    [q('sum by(job) (scrape_samples_scraped)', "{{job}}", "A")],
    12, y, 12, 7, unit="short", fill=15, line_width=2,
    legend_mode="table")); pid += 1
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
    "time": {"from": "now-3h", "to": "now"},
    "timepicker": {},
    "graphTooltip": 1,
    "fiscalYearStartMonth": 0,
    "liveNow": False,
    "weekStart": "",
    "annotations": {"list": []},
    "templating": {"list": []}
}

# Cleanup any prior dashboards
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
