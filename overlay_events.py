import time
from uuid import uuid4


STATE_TYPES = {
    "stats",
    "streak",
    "crosshair",
    "feed_config",
    "scifi_mode",
    "overlay_visibility",
    "perf_debug_mode",
    "perf_target_fps",
    "perf_pipeline_tuning",
    "perf_ws_batching_mode",
    "perf_event_pipeline_mode",
    "perf_js_scheduler_mode",
}

CRITICAL_EVENT_NAMES = {
    "kill",
    "death",
    "headshot",
    "revive taken",
    "alert win",
    "alert end",
}


def _as_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return int(fallback)


def _normalize_type(raw_type):
    return str(raw_type or "").strip().lower() or "unknown"


def _classify_category(event_type, payload):
    if event_type in STATE_TYPES:
        return "state"

    if event_type == "hitmarker":
        # Hitmarkers are high-frequency feedback and must not block gameplay-critical events.
        return "cosmetic"

    if event_type == "event":
        ev_name = str((payload or {}).get("event_type", "")).strip().lower()
        if "hitmarker" in ev_name:
            return "cosmetic"
        if ev_name in CRITICAL_EVENT_NAMES:
            return "critical"
        return "normal"

    if event_type in {"feed", "events_clear", "feed_clear", "stats_clear"}:
        return "normal"

    if event_type in {"crosshair_recoil"}:
        return "cosmetic"

    return "normal"


def _priority_for(category):
    if category == "state":
        return 100
    if category == "critical":
        return 90
    if category == "normal":
        return 60
    return 30


def normalize_overlay_event(event_type, payload, seq=0):
    now_ms = int(time.time() * 1000)
    evt_type = _normalize_type(event_type)
    safe_payload = dict(payload) if isinstance(payload, dict) else {"value": payload}

    ts_source_ms = _as_int(safe_payload.get("ts_source_ms"), now_ms)
    ttl_ms = _as_int(safe_payload.get("ttl_ms"), 0)
    category = _classify_category(evt_type, safe_payload)
    priority = _priority_for(category)

    if category == "state":
        coalesce_key = evt_type
        dedupe_key = evt_type
    else:
        coalesce_key = str(safe_payload.get("coalesce_key") or "")
        dedupe_key = str(safe_payload.get("dedupe_key") or "")
        if not dedupe_key:
            # Conservative defaults: identical transients in quick succession can be deduped.
            if evt_type in {"hitmarker", "event"}:
                ev_name = str(safe_payload.get("event_type") or evt_type).strip().lower()
                filename = str(safe_payload.get("filename") or "")
                # Hitmarkers must be allowed to stack and should not be deduped.
                if "hitmarker" not in ev_name:
                    dedupe_key = f"{evt_type}:{ev_name}:{filename}"
            elif evt_type in {"feed"}:
                html = str(safe_payload.get("html") or "")
                dedupe_key = f"feed:{hash(html)}"

    event_id = str(safe_payload.get("id") or f"{now_ms}-{seq}-{uuid4().hex[:8]}")

    return {
        "id": event_id,
        "type": evt_type,
        "category": category,
        "priority": int(priority),
        "ts_source_ms": int(ts_source_ms),
        "ttl_ms": int(ttl_ms),
        "dedupe_key": dedupe_key,
        "coalesce_key": coalesce_key,
        "payload": safe_payload,
    }
