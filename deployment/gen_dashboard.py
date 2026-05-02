#!/usr/bin/env python3
"""Generate the modernised RWA Operations Center Grafana dashboard."""
import json

DS  = "ffgx1hbr25a0wc"   # Prometheus datasource UID on 10.10.10.150
OUT = "deployment/monitoring/grafana_dashboard.json"

# ─── Colour palette ───────────────────────────────────────────────────────────
C = {
    "blue":       "#5794F2",
    "light_blue": "#8AB8FF",
    "cyan":       "#19D3C5",
    "teal":       "#00B8A9",
    "green":      "#73BF69",
    "lime":       "#B5CE28",
    "yellow":     "#FADE2A",
    "orange":     "#FF780A",
    "red":        "#F2495C",
    "dark_red":   "#C4162A",
    "purple":     "#B877D9",
    "violet":     "#9B51E0",
    "pink":       "#FF64B0",
    "sky":        "#2D9CDB",
    "gold":       "#F2994A",
    "white":      "#D9D9D9",
    "semi_dark":  "#1F1F1F",
}

# ─── Primitive helpers ────────────────────────────────────────────────────────
def gp(h, w, x, y):
    return {"h": h, "w": w, "x": x, "y": y}

def src(expr, legend="", ref="A"):
    return {
        "datasource": {"type": "prometheus", "uid": DS},
        "expr": expr,
        "legendFormat": legend,
        "refId": ref,
    }

def row_panel(pid, title, y):
    return {
        "collapsed": False,
        "gridPos": gp(1, 24, 0, y),
        "id": pid,
        "title": title,
        "type": "row",
    }

# ─── Field-config builders ────────────────────────────────────────────────────
def ts_defaults(unit="short", axis_label="", fill=18, gradient="scheme",
                line_width=2, min_val=None, stacked=False, decimals=None):
    d = {
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle":         "line",
            "lineInterpolation": "smooth",
            "lineWidth":         line_width,
            "fillOpacity":       fill,
            "gradientMode":      gradient,
            "showPoints":        "never",
            "spanNulls":         True,
            "stacking":          {"group": "A", "mode": "normal" if stacked else "none"},
            "axisBorderShow":    False,
            "axisLabel":         axis_label,
            "axisPlacement":     "auto",
            "hideFrom":          {"legend": False, "tooltip": False, "viz": False},
            "scaleDistribution": {"type": "linear"},
            "thresholdsStyle":   {"mode": "off"},
            "pointSize":         5,
        },
        "mappings":   [],
        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
        "unit":       unit,
    }
    if min_val is not None:
        d["min"] = min_val
    if decimals is not None:
        d["decimals"] = decimals
    return d

def ts_options(calcs=None, sort="desc"):
    return {
        "legend": {
            "calcs":       calcs or ["lastNotNull", "mean", "max"],
            "displayMode": "table",
            "placement":   "bottom",
            "showLegend":  True,
        },
        "tooltip": {"mode": "multi", "sort": sort},
    }

def stat_field(unit, thresholds, decimals=1, min_val=None, max_val=None):
    d = {
        "defaults": {
            "color":      {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": thresholds},
            "unit":       unit,
            "decimals":   decimals,
            "mappings":   [],
        },
        "overrides": [],
    }
    if min_val is not None:
        d["defaults"]["min"] = min_val
    if max_val is not None:
        d["defaults"]["max"] = max_val
    return d

def stat_options(color_mode="background", graph_mode="area", text_mode="value_and_name"):
    return {
        "colorMode":     color_mode,
        "graphMode":     graph_mode,
        "justifyMode":   "center",
        "orientation":   "auto",
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "textMode":      text_mode,
        "wideLayout":    True,
    }

def bargauge_options(orientation="horizontal"):
    return {
        "displayMode":  "gradient",
        "fillOpacity":  80,
        "gradientMode": "scheme",
        "legend":       {"displayMode": "list", "placement": "bottom", "showLegend": False},
        "minVizHeight": 16,
        "minVizWidth":  8,
        "namePlacement":"auto",
        "orientation":  orientation,
        "reduceOptions":{"calcs": ["lastNotNull"], "fields": "", "values": False},
        "showUnfilled": True,
        "sizing":       "auto",
        "tooltip":      {"mode": "single", "sort": "none"},
        "valueMode":    "color",
    }

# ─── Panel builders ───────────────────────────────────────────────────────────
def make_stat(pid, title, targets, unit, thresholds, gridpos,
              color_mode="background", graph_mode="area",
              decimals=1, text_mode="value_and_name",
              min_val=None, max_val=None):
    fc = stat_field(unit, thresholds, decimals, min_val, max_val)
    return {
        "datasource":  {"type": "prometheus", "uid": DS},
        "fieldConfig": fc,
        "gridPos":     gridpos,
        "id":          pid,
        "options":     stat_options(color_mode, graph_mode, text_mode),
        "targets":     targets,
        "title":       title,
        "type":        "stat",
    }

def make_ts(pid, title, targets, gridpos, field_defaults, overrides=None,
            calcs=None, sort="desc"):
    return {
        "datasource":  {"type": "prometheus", "uid": DS},
        "fieldConfig": {"defaults": field_defaults, "overrides": overrides or []},
        "gridPos":     gridpos,
        "id":          pid,
        "options":     ts_options(calcs, sort),
        "targets":     targets,
        "title":       title,
        "type":        "timeseries",
    }

def make_bargauge(pid, title, targets, gridpos, field_defaults, overrides=None,
                  orientation="horizontal", show_legend=False):
    opts = bargauge_options(orientation)
    opts["legend"]["showLegend"] = show_legend
    return {
        "datasource":  {"type": "prometheus", "uid": DS},
        "fieldConfig": {"defaults": field_defaults, "overrides": overrides or []},
        "gridPos":     gridpos,
        "id":          pid,
        "options":     opts,
        "targets":     targets,
        "title":       title,
        "type":        "bargauge",
    }

def make_donut(pid, title, targets, gridpos, overrides=None, label_display=None,
               legend_placement="right"):
    return {
        "datasource":  {"type": "prometheus", "uid": DS},
        "fieldConfig": {
            "defaults": {
                "color":   {"mode": "palette-classic"},
                "custom":  {"hideFrom": {"legend": False, "tooltip": False, "viz": False}},
                "mappings":[], "unit": "short",
            },
            "overrides": overrides or [],
        },
        "gridPos": gridpos,
        "id":      pid,
        "options": {
            "displayLabels": label_display or ["percent"],
            "legend": {
                "displayMode": "table",
                "placement":   legend_placement,
                "showLegend":  True,
                "values":      ["value", "percent"],
            },
            "pieType": "donut",
            "tooltip": {"mode": "single", "sort": "none"},
        },
        "targets": targets,
        "title":   title,
        "type":    "piechart",
    }

def make_state_timeline(pid, title, targets, gridpos, value_map, thresholds):
    return {
        "datasource":  {"type": "prometheus", "uid": DS},
        "fieldConfig": {
            "defaults": {
                "color":   {"mode": "thresholds"},
                "custom":  {
                    "fillOpacity":  80,
                    "hideFrom":     {"legend": False, "tooltip": False, "viz": False},
                    "insertNulls":  False,
                    "lineWidth":    0,
                    "spanNulls":    False,
                },
                "mappings":   [{"options": value_map, "type": "value"}],
                "thresholds": {"mode": "absolute", "steps": thresholds},
            },
            "overrides": [],
        },
        "gridPos": gridpos,
        "id":      pid,
        "options": {
            "alignValue":  "center",
            "legend":      {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "mergeValues": True,
            "rowHeight":   0.9,
            "showValue":   "auto",
            "tooltip":     {"mode": "single", "sort": "none"},
        },
        "targets": targets,
        "title":   title,
        "type":    "state-timeline",
    }

# ═════════════════════════════════════════════════════════════════════════════
# BUILD PANELS
# ═════════════════════════════════════════════════════════════════════════════
panels = []

# ────────────────────────────────────────────────────────────────────────────
# ROW 1 — Platform Overview   y=0
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(1, "Platform Overview", 0))

panels.append(make_stat(
    2, "API Request Rate",
    [src('sum(rate(http_requests_total[$interval]))', "req/s")],
    "reqps",
    [{"color": C["blue"], "value": None}, {"color": C["cyan"], "value": 10},
     {"color": C["green"], "value": 100}],
    gp(6, 4, 0, 1), decimals=2,
))

panels.append(make_stat(
    3, "Active Assets",
    [src('rwa_assets_by_status{status="ACTIF"}', "assets")],
    "short",
    [{"color": C["blue"], "value": None}, {"color": C["cyan"], "value": 5},
     {"color": C["green"], "value": 20}],
    gp(6, 4, 4, 1), decimals=0,
))

panels.append(make_stat(
    4, "API Latency p95",
    [src('histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket[$interval]))) * 1000',
         "p95 ms")],
    "ms",
    [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 150},
     {"color": C["orange"], "value": 300}, {"color": C["red"], "value": 600}],
    gp(6, 4, 8, 1), decimals=0,
))

panels.append(make_stat(
    5, "Error Rate (5xx)",
    [src('sum(rate(http_requests_total{status="5xx"}[$interval])) / sum(rate(http_requests_total[$interval])) * 100',
         "%")],
    "percent",
    [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 1},
     {"color": C["orange"], "value": 2},  {"color": C["red"], "value": 5}],
    gp(6, 4, 12, 1), decimals=2,
))

panels.append(make_stat(
    6, "KYC Expiring (30 d)",
    [src('rwa_kyc_expiring_count', "users")],
    "short",
    [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 5},
     {"color": C["orange"], "value": 10},  {"color": C["red"], "value": 20}],
    gp(6, 4, 16, 1), decimals=0,
))

panels.append(make_stat(
    7, "Max AML Score",
    [src('max(rwa_aml_score_avg)', "score")],
    "percentunit",
    [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 0.3},
     {"color": C["orange"], "value": 0.6}, {"color": C["red"], "value": 0.8}],
    gp(6, 4, 20, 1), decimals=3,
))

# ────────────────────────────────────────────────────────────────────────────
# ROW 2 — API Traffic Analytics   y=7
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(8, "API Traffic Analytics", 7))

panels.append(make_ts(
    9, "Throughput by HTTP Method (req/s)",
    [src('sum by(method) (rate(http_requests_total[$interval]))', "{{method}}")],
    gp(9, 15, 0, 8),
    ts_defaults(unit="reqps", axis_label="req/s", fill=22, gradient="scheme", min_val=0),
    overrides=[
        {"matcher": {"id": "byName", "options": "GET"},
         "properties": [{"id": "color", "value": {"fixedColor": C["blue"],   "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "POST"},
         "properties": [{"id": "color", "value": {"fixedColor": C["green"],  "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "PUT"},
         "properties": [{"id": "color", "value": {"fixedColor": C["orange"], "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "DELETE"},
         "properties": [{"id": "color", "value": {"fixedColor": C["red"],    "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "PATCH"},
         "properties": [{"id": "color", "value": {"fixedColor": C["purple"], "mode": "fixed"}}]},
    ],
    calcs=["lastNotNull", "mean", "max"],
))

panels.append(make_donut(
    10, "Request Volume by HTTP Status Class",
    [src('sum by(status) (increase(http_requests_total[$interval]))', "{{status}}")],
    gp(9, 9, 15, 8),
    overrides=[
        {"matcher": {"id": "byName", "options": "2xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["green"],  "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "3xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["cyan"],   "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "4xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["orange"], "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "5xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["red"],    "mode": "fixed"}}]},
    ],
    label_display=["percent"],
))

# ────────────────────────────────────────────────────────────────────────────
# ROW 3 — API Latency Analysis   y=17
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(11, "API Latency Analysis", 17))

# p50 / p95 / p99 timeseries
_lat_fd = ts_defaults(unit="ms", axis_label="latency (ms)", fill=10, gradient="opacity", min_val=0)
panels.append(make_ts(
    12, "API Response Time — p50 / p95 / p99",
    [
        src('histogram_quantile(0.50, sum by(le) (rate(http_request_duration_seconds_bucket[$interval]))) * 1000',
            "p50", "A"),
        src('histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket[$interval]))) * 1000',
            "p95", "B"),
        src('histogram_quantile(0.99, sum by(le) (rate(http_request_duration_seconds_bucket[$interval]))) * 1000',
            "p99", "C"),
    ],
    gp(9, 12, 0, 18),
    _lat_fd,
    overrides=[
        {"matcher": {"id": "byName", "options": "p50"},
         "properties": [
             {"id": "color", "value": {"fixedColor": C["green"],  "mode": "fixed"}},
             {"id": "custom.lineWidth", "value": 1},
         ]},
        {"matcher": {"id": "byName", "options": "p95"},
         "properties": [
             {"id": "color", "value": {"fixedColor": C["orange"], "mode": "fixed"}},
             {"id": "custom.lineWidth", "value": 2},
         ]},
        {"matcher": {"id": "byName", "options": "p99"},
         "properties": [
             {"id": "color", "value": {"fixedColor": C["red"],    "mode": "fixed"}},
             {"id": "custom.lineWidth", "value": 2},
             {"id": "custom.fillOpacity", "value": 4},
         ]},
    ],
    calcs=["lastNotNull", "mean", "max"],
))

# Heatmap — Turbo
panels.append({
    "datasource": {"type": "prometheus", "uid": DS},
    "fieldConfig": {
        "defaults": {
            "custom": {
                "hideFrom": {"legend": False, "tooltip": False, "viz": False},
                "scaleDistribution": {"log": 2, "type": "log"},
            },
        },
        "overrides": [],
    },
    "gridPos": gp(9, 7, 12, 18),
    "id": 13,
    "options": {
        "calculate": False,
        "cellGap": 1,
        "color": {
            "exponent": 0.5,
            "fill":     C["cyan"],
            "mode":     "scheme",
            "reverse":  False,
            "scale":    "exponential",
            "scheme":   "Turbo",
            "steps":    128,
        },
        "exemplars": {"color": "rgba(255,0,255,0.7)"},
        "filterValues": {"le": 1e-9},
        "legend":   {"show": True},
        "rowsFrame":{"layout": "auto"},
        "tooltip":  {"mode": "single", "showColorScale": True, "yHistogram": False},
        "yAxis":    {
            "axisPlacement": "left",
            "decimals": 0,
            "label":    "bucket (s)",
            "reverse":  False,
            "unit":     "s",
        },
    },
    "targets": [src('sum by(le) (increase(http_request_duration_seconds_bucket[$interval]))', "{{le}}")],
    "title": "Latency Distribution Heatmap (Turbo)",
    "type": "heatmap",
})

# Gauge — p95 latency
panels.append({
    "datasource": {"type": "prometheus", "uid": DS},
    "fieldConfig": {
        "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [
                {"color": C["green"],  "value": None},
                {"color": C["yellow"], "value": 100},
                {"color": C["orange"], "value": 300},
                {"color": C["red"],    "value": 600},
            ]},
            "unit": "ms", "decimals": 0, "min": 0, "max": 1000, "mappings": [],
        },
        "overrides": [],
    },
    "gridPos": gp(9, 5, 19, 18),
    "id": 14,
    "options": {
        "minVizHeight":       75,
        "minVizWidth":        75,
        "orientation":        "auto",
        "reduceOptions":      {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "showThresholdLabels": False,
        "showThresholdMarkers": True,
        "sizing": "auto",
        "text": {},
    },
    "targets": [src('histogram_quantile(0.95, sum by(le) (rate(http_request_duration_seconds_bucket[$interval]))) * 1000',
                    "p95 latency")],
    "title": "p95 Latency Gauge (ms)",
    "type": "gauge",
})

# ────────────────────────────────────────────────────────────────────────────
# ROW 4 — Compliance, AML & Regulatory Risk   y=27
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(15, "Compliance, AML & Regulatory Risk", 27))

panels.append(make_bargauge(
    16, "AML Score by Risk Category",
    [src('rwa_aml_score_avg', "{{risk_category}}")],
    gp(9, 7, 0, 28),
    {
        "color":      {"mode": "continuous-GrYlRd"},
        "thresholds": {"mode": "absolute", "steps": [
            {"color": C["green"],  "value": None},
            {"color": C["yellow"], "value": 0.3},
            {"color": C["orange"], "value": 0.6},
            {"color": C["red"],    "value": 0.8},
        ]},
        "unit": "percentunit", "decimals": 3, "min": 0, "max": 1, "mappings": [],
    },
))

panels.append(make_donut(
    17, "Asset Status Distribution",
    [src('rwa_assets_by_status', "{{status}}")],
    gp(9, 8, 7, 28),
    overrides=[
        {"matcher": {"id": "byName", "options": "ACTIF"},
         "properties": [{"id": "color", "value": {"fixedColor": C["green"],  "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "GELE"},
         "properties": [{"id": "color", "value": {"fixedColor": C["sky"],    "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "REMBOURSE"},
         "properties": [{"id": "color", "value": {"fixedColor": C["cyan"],   "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "EN_ATTENTE"},
         "properties": [{"id": "color", "value": {"fixedColor": C["yellow"], "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "REJETE"},
         "properties": [{"id": "color", "value": {"fixedColor": C["red"],    "mode": "fixed"}}]},
    ],
    label_display=["name", "percent"],
))

# Compliance blocks — stacked timeseries
_cb_fd = ts_defaults(unit="short", axis_label="blocks/min", fill=25, gradient="scheme",
                     min_val=0, stacked=True)
panels.append(make_ts(
    18, "Compliance Blocks by Reason (per min, stacked)",
    [src('sum by(blocked_by) (rate(rwa_compliance_blocks_total[$interval])) * 60', "{{blocked_by}}")],
    gp(9, 9, 15, 28),
    _cb_fd,
    calcs=["lastNotNull", "sum"],
))

# ────────────────────────────────────────────────────────────────────────────
# ROW 5 — Circuit Breakers & Error Analysis   y=37
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(19, "Circuit Breakers & Error Analysis", 37))

panels.append(make_state_timeline(
    20, "Circuit Breaker State (CLOSED = Healthy)",
    [src('rwa_circuit_breaker_state', "{{component}}")],
    gp(7, 15, 0, 38),
    value_map={
        "0": {"color": C["red"],   "index": 0, "text": "OPEN"},
        "1": {"color": C["green"], "index": 1, "text": "CLOSED"},
    },
    thresholds=[{"color": C["red"], "value": None}, {"color": C["green"], "value": 1}],
))

_err_fd = ts_defaults(unit="reqps", axis_label="errors/s", fill=20, gradient="opacity", min_val=0)
panels.append(make_ts(
    21, "Server Errors by Endpoint (5xx/s)",
    [src('sum by(handler) (rate(http_requests_total{status="5xx"}[$interval]))', "{{handler}}")],
    gp(7, 5, 15, 38),
    _err_fd,
    calcs=["lastNotNull", "max"],
))

panels.append(make_bargauge(
    22, "Request Totals by Status (24 h)",
    [src('sum by(status) (increase(http_requests_total[24h]))', "{{status}}")],
    gp(7, 4, 20, 38),
    {
        "color":      {"mode": "palette-classic"},
        "thresholds": {"mode": "absolute", "steps": [{"color": C["blue"], "value": None}]},
        "unit": "short", "decimals": 0, "mappings": [],
    },
    overrides=[
        {"matcher": {"id": "byName", "options": "2xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["green"],  "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "4xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["orange"], "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "5xx"},
         "properties": [{"id": "color", "value": {"fixedColor": C["red"],    "mode": "fixed"}}]},
    ],
))

# ────────────────────────────────────────────────────────────────────────────
# ROW 6 — Async Task Queue   y=45
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(23, "Async Task Queue", 45))

panels.append(make_ts(
    24, "Task Execution Rate by Name & Status (per min)",
    [src('sum by(task_name, status) (rate(rwa_celery_tasks_total[$interval])) * 60',
         "{{task_name}} · {{status}}")],
    gp(8, 14, 0, 46),
    ts_defaults(unit="short", axis_label="tasks/min", fill=15, gradient="scheme", min_val=0),
    calcs=["lastNotNull", "mean", "sum"],
))

panels.append(make_bargauge(
    25, "24 h Task Totals",
    [src('sum by(task_name, status) (increase(rwa_celery_tasks_total[24h]))',
         "{{task_name}} · {{status}}")],
    gp(8, 10, 14, 46),
    {
        "color":      {"mode": "palette-classic"},
        "thresholds": {"mode": "absolute", "steps": [{"color": C["blue"], "value": None}]},
        "unit": "short", "decimals": 0, "mappings": [],
    },
    show_legend=True,
))

# ────────────────────────────────────────────────────────────────────────────
# ROW 7 — Infrastructure Availability   y=54
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(26, "Infrastructure Availability", 54))

panels.append(make_state_timeline(
    27, "Service Health Timeline",
    [
        src('up{job="rwa-api"}',          "API",          "A"),
        src('up{job="postgres"}',          "PostgreSQL",   "B"),
        src('up{job="redis"}',             "Redis",        "C"),
        src('up{job="celery"}',            "Celery",       "D"),
        src('up{job="fabric-peer-bnp"}',   "Fabric BNP",   "E"),
        src('up{job="fabric-peer-amf"}',   "Fabric AMF",   "F"),
        src('up{job="couchdb-bnp"}',       "CouchDB BNP",  "G"),
        src('up{job="couchdb-amf"}',       "CouchDB AMF",  "H"),
    ],
    gp(5, 24, 0, 55),
    value_map={
        "0": {"color": C["red"],   "index": 0, "text": "DOWN"},
        "1": {"color": C["green"], "index": 1, "text": "UP"},
    },
    thresholds=[{"color": C["red"], "value": None}, {"color": C["green"], "value": 1}],
))

panels.append(make_bargauge(
    28, "Service Uptime (last 1 h)",
    [
        src('avg_over_time(up{job="rwa-api"}[1h])',          "API",        "A"),
        src('avg_over_time(up{job="postgres"}[1h])',          "PostgreSQL", "B"),
        src('avg_over_time(up{job="redis"}[1h])',             "Redis",      "C"),
        src('avg_over_time(up{job="celery"}[1h])',            "Celery",     "D"),
        src('avg_over_time(up{job="fabric-peer-bnp"}[1h])',   "Fabric BNP", "E"),
        src('avg_over_time(up{job="fabric-peer-amf"}[1h])',   "Fabric AMF", "F"),
    ],
    gp(4, 16, 0, 60),
    {
        "color":      {"mode": "continuous-GrYlRd"},
        "thresholds": {"mode": "absolute", "steps": [
            {"color": C["red"],    "value": None},
            {"color": C["orange"], "value": 0.80},
            {"color": C["yellow"], "value": 0.95},
            {"color": C["green"],  "value": 0.99},
        ]},
        "unit": "percentunit", "decimals": 2, "min": 0, "max": 1, "mappings": [],
    },
))

panels.append(make_stat(
    29, "Overall Uptime",
    [src('avg(up{job=~"rwa-api|postgres|redis|celery|fabric-peer-bnp|fabric-peer-amf|couchdb-bnp|couchdb-amf"})',
         "uptime")],
    "percentunit",
    [{"color": C["red"],    "value": None},  {"color": C["orange"], "value": 0.80},
     {"color": C["yellow"], "value": 0.95},  {"color": C["green"],  "value": 0.99}],
    gp(4, 4, 16, 60),
    decimals=3, color_mode="background", graph_mode="none", text_mode="value_and_name",
))

panels.append(make_stat(
    30, "Services Degraded",
    [src('count(up{job=~"rwa-api|postgres|redis|celery|fabric-peer-bnp|fabric-peer-amf|couchdb-bnp|couchdb-amf"} == 0) or vector(0)',
         "services")],
    "short",
    [{"color": C["green"],  "value": None}, {"color": C["yellow"], "value": 1},
     {"color": C["orange"], "value": 2},    {"color": C["red"],    "value": 3}],
    gp(4, 4, 20, 60),
    decimals=0, color_mode="background", graph_mode="none", text_mode="value_and_name",
))

# ────────────────────────────────────────────────────────────────────────────
# ROW 8 — Blockchain & Data Layer   y=64
# ────────────────────────────────────────────────────────────────────────────
panels.append(row_panel(31, "Blockchain & Data Layer", 64))

_bh_fd = ts_defaults(unit="short", axis_label="block height", fill=20, gradient="opacity",
                     min_val=0, decimals=0)
panels.append(make_ts(
    32, "Fabric Blockchain Height by Peer",
    [
        src('ledger_blockchain_height{job="fabric-peer-bnp"}', "BNP Peer", "A"),
        src('ledger_blockchain_height{job="fabric-peer-amf"}', "AMF Peer", "B"),
    ],
    gp(8, 8, 0, 65),
    _bh_fd,
    overrides=[
        {"matcher": {"id": "byName", "options": "BNP Peer"},
         "properties": [{"id": "color", "value": {"fixedColor": C["sky"],    "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "AMF Peer"},
         "properties": [{"id": "color", "value": {"fixedColor": C["purple"], "mode": "fixed"}}]},
    ],
    calcs=["lastNotNull", "max"],
))

panels.append(make_ts(
    33, "PostgreSQL Query Throughput (tuples/s)",
    [
        src('rate(pg_stat_database_tup_fetched{datname=~"rwadb.*"}[$interval])',  "fetched",  "A"),
        src('rate(pg_stat_database_tup_inserted{datname=~"rwadb.*"}[$interval])', "inserted", "B"),
        src('rate(pg_stat_database_tup_updated{datname=~"rwadb.*"}[$interval])',  "updated",  "C"),
        src('rate(pg_stat_database_tup_deleted{datname=~"rwadb.*"}[$interval])',  "deleted",  "D"),
    ],
    gp(8, 8, 8, 65),
    ts_defaults(unit="reqps", axis_label="tuples/s", fill=15, gradient="scheme", min_val=0),
    overrides=[
        {"matcher": {"id": "byName", "options": "fetched"},
         "properties": [{"id": "color", "value": {"fixedColor": C["blue"],   "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "inserted"},
         "properties": [{"id": "color", "value": {"fixedColor": C["green"],  "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "updated"},
         "properties": [{"id": "color", "value": {"fixedColor": C["orange"], "mode": "fixed"}}]},
        {"matcher": {"id": "byName", "options": "deleted"},
         "properties": [{"id": "color", "value": {"fixedColor": C["red"],    "mode": "fixed"}}]},
    ],
    calcs=["lastNotNull", "mean"],
))

# Redis + PG stat panels  (2 columns × 2 rows on the right side)
for pid, title, expr, unit, dec, thresholds, gridpos in [
    (34, "Redis Memory Usage",
     "redis_memory_used_bytes / redis_memory_max_bytes", "percentunit", 2,
     [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 0.7},
      {"color": C["red"],   "value": 0.9}],
     gp(4, 4, 16, 65)),
    (35, "Redis Cache Hit Rate",
     "redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total)",
     "percentunit", 2,
     [{"color": C["red"],    "value": None}, {"color": C["yellow"], "value": 0.7},
      {"color": C["green"],  "value": 0.9}],
     gp(4, 4, 20, 65)),
    (36, "Redis Connected Clients",
     "redis_connected_clients", "short", 0,
     [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 20},
      {"color": C["red"],   "value": 80}],
     gp(4, 4, 16, 69)),
    (37, "PostgreSQL Connections",
     'sum(pg_stat_database_numbackends{datname=~"rwadb.*"})', "short", 0,
     [{"color": C["green"], "value": None}, {"color": C["yellow"], "value": 50},
      {"color": C["red"],   "value": 90}],
     gp(4, 4, 20, 69)),
]:
    panels.append(make_stat(
        pid, title, [src(expr, title)],
        unit, thresholds, gridpos,
        decimals=dec, color_mode="background", graph_mode="area",
    ))

# ─── Assemble dashboard ───────────────────────────────────────────────────────
dashboard = {
    "__inputs": [{
        "name": "DS_PROMETHEUS", "label": "Prometheus", "description": "",
        "type": "datasource", "pluginId": "prometheus", "pluginName": "Prometheus",
    }],
    "__elements": {},
    "__requires": [
        {"type": "grafana",    "id": "grafana",        "name": "Grafana",       "version": "10.0.0"},
        {"type": "datasource", "id": "prometheus",     "name": "Prometheus",    "version": "1.0.0"},
        {"type": "panel",      "id": "timeseries",     "name": "Time series",   "version": ""},
        {"type": "panel",      "id": "stat",           "name": "Stat",          "version": ""},
        {"type": "panel",      "id": "gauge",          "name": "Gauge",         "version": ""},
        {"type": "panel",      "id": "piechart",       "name": "Pie chart",     "version": ""},
        {"type": "panel",      "id": "bargauge",       "name": "Bar gauge",     "version": ""},
        {"type": "panel",      "id": "state-timeline", "name": "State timeline","version": ""},
        {"type": "panel",      "id": "heatmap",        "name": "Heatmap",       "version": ""},
    ],
    "annotations": {"list": [{
        "builtIn": 1,
        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
        "enable": True, "hide": True,
        "iconColor": "rgba(0,211,255,1)",
        "name": "Annotations & Alerts",
        "type": "dashboard",
    }]},
    "description": "RWA Platform — Operations Center: API performance, compliance risk, asset distribution, and infrastructure health.",
    "editable":    True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id":      None,
    "links":   [],
    "panels":  panels,
    "refresh": "30s",
    "schemaVersion": 38,
    "tags":  ["rwa", "blockchain", "operations", "fintech", "compliance"],
    "templating": {"list": [{
        "current":    {"selected": False, "text": "1m", "value": "1m"},
        "hide":       0,
        "includeAll": False,
        "label":      "Interval",
        "multi":      False,
        "name":       "interval",
        "options": [
            {"selected": False, "text": "30s", "value": "30s"},
            {"selected": True,  "text": "1m",  "value": "1m"},
            {"selected": False, "text": "5m",  "value": "5m"},
            {"selected": False, "text": "15m", "value": "15m"},
            {"selected": False, "text": "1h",  "value": "1h"},
        ],
        "query":        "30s,1m,5m,15m,1h",
        "queryValue":   "",
        "skipUrlSync":  False,
        "type":         "custom",
    }]},
    "time":      {"from": "now-1h", "to": "now"},
    "timepicker": {},
    "timezone":  "Europe/Paris",
    "title":     "RWA Platform — Operations Center",
    "uid":       "rwa-ops-professional",
    "version":   4,
    "weekStart": "",
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(dashboard, f, indent=2, ensure_ascii=False)

print(f"Done — {len(panels)} panels, version {dashboard['version']}")
