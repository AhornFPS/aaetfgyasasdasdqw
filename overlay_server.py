import os
import sys
import json
import time
import threading
import asyncio
from collections import deque
from urllib.parse import unquote, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

import websockets
from overlay_events import normalize_overlay_event
try:
    from dior_utils import get_user_data_dir
    LOG_DIR = get_user_data_dir()
except ImportError:
    LOG_DIR = os.getcwd()

HTTP_PORT = 31337
WS_PORT = 31338

def server_log(msg):
    log_path = os.path.join(LOG_DIR, "overlay_server.log")
    timestamp = threading.current_thread().name
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except:
        pass
    print(msg)

def perf_log_path():
    return os.path.join(LOG_DIR, "overlay_perf.log")


def trace_log_path():
    return os.path.join(LOG_DIR, "overlay_trace.jsonl")


def _project_root():
    # PyInstaller puts files in sys._MEIPASS.
    # In one-dir mode with PyInstaller 6+, this is usually the '_internal' folder.
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    
    # Fallback to script directory
    return os.path.dirname(os.path.abspath(__file__))


def _overlay_web_dir():
    root = _project_root()
    # Check both direct and _internal subfolder just in case
    paths = [
        os.path.join(root, 'web_overlay'),
        os.path.join(root, '_internal', 'web_overlay')
    ]
    for p in paths:
        if os.path.isdir(p):
            return p
    return paths[0]


def _assets_dir():
    root = _project_root()
    paths = [
        os.path.join(root, 'assets'),
        os.path.join(root, '_internal', 'assets')
    ]
    for p in paths:
        if os.path.isdir(p):
            return p
    return paths[0]


class AssetHTTPHandler(BaseHTTPRequestHandler):
    def _send_file(self, full_path, content_type='text/html; charset=utf-8'):
        try:
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                server_log(f"HTTP ERROR: File not found: {full_path}")
                self.send_error(404, f'File not found: {os.path.basename(full_path)}')
                return

            with open(full_path, 'rb') as f:
                data = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            # Fix CORS for OBS
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            server_log(f"HTTP CRASH in _send_file ({full_path}): {e}")

    def _serve_overlay_config(self):
        try:
            ws_port = getattr(self.server, 'ws_port', WS_PORT)
            perf_debug = bool(getattr(self.server, 'perf_debug', False))
            event_pipeline_v2 = bool(getattr(self.server, 'event_pipeline_v2', True))
            js_scheduler_v2 = bool(getattr(self.server, 'js_scheduler_v2', True))
            payload = (
                "window.OVERLAY_CONFIG = { "
                f"wsPort: {int(ws_port)}, "
                f"perfDebug: {'true' if perf_debug else 'false'}, "
                f"eventPipelineV2: {'true' if event_pipeline_v2 else 'false'}, "
                f"jsSchedulerV2: {'true' if js_scheduler_v2 else 'false'} "
                "};\n"
            )
            data = payload.encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            server_log(f"HTTP CRASH in _serve_overlay_config: {e}")

    def _serve_asset(self, req_path):
        filename = unquote(req_path.replace('/assets/', '', 1)).lstrip('/\\')
        filename = os.path.normpath(filename)
        if filename.startswith('..'):
            self.send_error(403, 'Forbidden')
            return
        
        base_dir = _assets_dir()
        candidates = [
            os.path.join(base_dir, filename),
            os.path.join(base_dir, 'Images', filename),
            os.path.join(base_dir, 'Sounds', filename),
            os.path.join(base_dir, 'Crosshair', filename),
        ]

        for candidate in candidates:
            if os.path.isfile(candidate):
                ext = os.path.splitext(candidate)[1].lower()
                ctype = 'application/octet-stream'
                if ext in ('.png', '.jpg', '.jpeg'): ctype = 'image/png' if ext == '.png' else 'image/jpeg'
                elif ext == '.gif': ctype = 'image/gif'
                elif ext in ('.mp3', '.wav', '.ogg'): ctype = 'audio/mpeg' if ext == '.mp3' else f'audio/{ext[1:]}'
                elif ext == '.ttf': ctype = 'font/ttf'
                elif ext == '.otf': ctype = 'font/otf'
                elif ext == '.woff': ctype = 'font/woff'
                elif ext == '.woff2': ctype = 'font/woff2'
                
                return self._send_file(candidate, ctype)

        self.send_error(404, f'Asset not found: {filename}')

    def _serve_web_file(self, req_path):
        web_dir = _overlay_web_dir()
        rel = req_path.replace('/web/', '', 1).lstrip('/\\')
        rel = os.path.normpath(rel)
        if rel.startswith('..'):
            self.send_error(403, 'Forbidden')
            return

        full_path = os.path.join(web_dir, rel)
        ext = os.path.splitext(full_path)[1].lower()
        ctype_map = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
        }
        self._send_file(full_path, ctype_map.get(ext, 'application/octet-stream'))

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            req_path = parsed.path or "/"
            query = parse_qs(parsed.query or "")

            if req_path in ('/', '/index.html'):
                return self._send_file(os.path.join(_overlay_web_dir(), 'index.html'), 'text/html; charset=utf-8')

            if req_path == '/overlay-config.js':
                return self._serve_overlay_config()

            if req_path == '/dev/overlay-visibility':
                mode = str((query.get("mode", ["auto"])[0] or "auto")).strip().lower()
                if mode not in {"auto", "hide", "show"}:
                    mode = "auto"
                overlay_server = getattr(self.server, "overlay_server", None)
                if overlay_server:
                    overlay_server.set_dev_overlay_visibility_mode(mode)
                payload = json.dumps({"ok": True, "mode": mode}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)
                return

            if req_path.startswith('/web/'):
                return self._serve_web_file(req_path)

            if req_path.startswith('/assets/'):
                return self._serve_asset(req_path)

            if req_path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            self.send_error(404, f'Path not found: {req_path}')
        except Exception as e:
            server_log(f"HTTP CRASH in do_GET ({self.path}): {e}")

    def log_message(self, format, *args):
        # Override to suppress default console logging
        pass


class OverlayServer:
    def __init__(self, http_port=HTTP_PORT, ws_port=WS_PORT):
        self.http_port = http_port
        self.ws_port = ws_port
        self.ws_clients = set()
        self.ws_loop = None
        self.httpd = None

        self.http_thread = None
        self.ws_thread = None
        self.is_running = False

        self._state_lock = threading.Lock()
        self._state_cache = {}
        self._pending_state_by_type = {}
        self._pending_transient = deque()
        self._max_transient_pending = 2048
        self._dedupe_window_ms = 120
        self._recent_dedupe = {}
        self._flush_task = None
        self._flush_scheduled = False
        self._next_flush_at = 0.0
        self._msg_seq = 0
        self.perf_debug = False
        self.target_fps = 120
        self._flush_interval_s = 1.0 / 120.0
        self.ws_batching_v2 = False
        self.trace_export = False
        self.event_pipeline_v2 = True
        self.js_scheduler_v2 = True
        self._last_metrics_emit_ms = 0
        self._metrics = {
            "events_in_total": 0,
            "events_out_total": 0,
            "flush_count": 0,
            "last_flush_size": 0,
            "max_pending_state": 0,
            "max_pending_transient": 0,
            "coalesce_replaced": 0,
            "dropped_total": 0,
            "dropped_transient_overflow": 0,
            "deduped_total": 0,
            "dropped_cosmetic_total": 0,
            "dropped_normal_total": 0,
            "events_in_state": 0,
            "events_in_critical": 0,
            "events_in_normal": 0,
            "events_in_cosmetic": 0,
            "events_out_state": 0,
            "events_out_critical": 0,
            "events_out_normal": 0,
            "events_out_cosmetic": 0,
            "batch_flush_count": 0,
            "legacy_flush_count": 0,
            "last_batch_size": 0,
            "last_emit_payload_ms": 0,
        }
        self._dev_overlay_visibility_mode = "auto"  # auto | hide | show

    def set_perf_debug(self, enabled):
        self.perf_debug = bool(enabled)
        if self.httpd:
            self.httpd.perf_debug = self.perf_debug
        # Apply immediately to connected overlay clients.
        self.broadcast("perf_debug_mode", {"enabled": self.perf_debug})

    def set_target_fps(self, fps):
        try:
            fps_i = int(fps)
        except Exception:
            fps_i = 120
        fps_i = max(15, min(240, fps_i))
        self.target_fps = fps_i
        self._flush_interval_s = 1.0 / float(fps_i)
        # Apply immediately to connected overlay clients.
        self.broadcast("perf_target_fps", {"fps": fps_i})

    def set_event_pipeline_tuning(self, dedupe_window_ms=None, max_transient_pending=None):
        if dedupe_window_ms is not None:
            try:
                dedupe_i = int(dedupe_window_ms)
            except Exception:
                dedupe_i = self._dedupe_window_ms
            self._dedupe_window_ms = max(0, min(5000, dedupe_i))

        if max_transient_pending is not None:
            try:
                cap_i = int(max_transient_pending)
            except Exception:
                cap_i = self._max_transient_pending
            self._max_transient_pending = max(64, min(20000, cap_i))

        self.broadcast("perf_pipeline_tuning", {
            "dedupe_window_ms": int(self._dedupe_window_ms),
            "max_transient_pending": int(self._max_transient_pending),
            "max_cosmetic_pending": int(self._max_cosmetic_pending()),
        })

    def set_ws_batching_v2(self, enabled):
        self.ws_batching_v2 = bool(enabled)
        self.broadcast("perf_ws_batching_mode", {"enabled": self.ws_batching_v2})

    def set_trace_export(self, enabled):
        self.trace_export = bool(enabled)

    def set_event_pipeline_v2(self, enabled):
        self.event_pipeline_v2 = bool(enabled)
        if self.httpd:
            self.httpd.event_pipeline_v2 = self.event_pipeline_v2
        self.broadcast("perf_event_pipeline_mode", {"enabled": self.event_pipeline_v2})

    def set_js_scheduler_v2(self, enabled):
        self.js_scheduler_v2 = bool(enabled)
        if self.httpd:
            self.httpd.js_scheduler_v2 = self.js_scheduler_v2
        self.broadcast("perf_js_scheduler_mode", {"enabled": self.js_scheduler_v2})

    def set_dev_overlay_visibility_mode(self, mode):
        mode_s = str(mode or "auto").strip().lower()
        if mode_s not in {"auto", "hide", "show"}:
            mode_s = "auto"
        self._dev_overlay_visibility_mode = mode_s

    def start(self):
        if self.is_running:
            return

        # Ensure ports are different
        if self.http_port == self.ws_port:
            self.ws_port += 1

        self.is_running = True
        self.stop_requested = threading.Event()
        
        # Use events to wait for ports to be bound
        self.http_ready = threading.Event()
        self.ws_ready = threading.Event()

        self.http_thread = threading.Thread(target=self._run_http, name="HTTP-Server", daemon=True)
        self.http_thread.start()

        self.ws_thread = threading.Thread(target=self._run_ws, name="WS-Server", daemon=True)
        self.ws_thread.start()
        
        # Wait a bit for threads to start and bind ports
        self.http_ready.wait(timeout=2.0)
        self.ws_ready.wait(timeout=2.0)
        
        return self.http_port, self.ws_port

    def stop(self):
        self.is_running = False
        if hasattr(self, 'stop_requested'):
            self.stop_requested.set()

        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None

        if self.ws_loop:
            try:
                # Thread-safe way to wake up the loop if it's waiting
                self.ws_loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass
        with self._state_lock:
            self._pending_state_by_type.clear()
            self._pending_transient.clear()
            self._recent_dedupe.clear()
        self._flush_scheduled = False
        self._next_flush_at = 0.0
        self._flush_task = None

    def _run_http(self):
        HTTPServer.allow_reuse_address = True
        max_attempts = 10
        for i in range(max_attempts):
            try:
                current_port = self.http_port + i
                self.httpd = HTTPServer(('127.0.0.1', current_port), AssetHTTPHandler)
                self.http_port = current_port
                self.httpd.ws_port = self.ws_port
                self.httpd.overlay_server = self
                self.httpd.perf_debug = self.perf_debug
                self.httpd.event_pipeline_v2 = self.event_pipeline_v2
                self.httpd.js_scheduler_v2 = self.js_scheduler_v2
                print(f'WEB: Overlay ready at http://localhost:{self.http_port}')
                self.http_ready.set()
                self.httpd.serve_forever()
                return
            except OSError:
                if i < max_attempts - 1:
                    continue
                print(f'ERROR: All HTTP ports from {self.http_port} to {self.http_port + i} are busy.')
            except Exception as e:
                print(f'HTTP Server Error: {e}')
                break
        self.http_ready.set() # Release even on failure

    def _run_ws(self):
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)

        async def ws_main():
            max_attempts = 10
            found = False
            for i in range(max_attempts):
                try:
                    port = self.ws_port + i
                    # Prevent overlap with HTTP which might have shifted
                    if port == self.http_port:
                        continue
                        
                    async with websockets.serve(self._ws_handler, '127.0.0.1', port):
                        self.ws_port = port
                        found = True
                        print(f'WS: WebSocket listening on port {self.ws_port}')
                        self.ws_ready.set()
                        
                        # Wait until stop is requested
                        while not self.stop_requested.is_set():
                            await asyncio.sleep(0.5)
                        return # Exit the 'async with' context to close the server
                except OSError:
                    if i < max_attempts - 1: continue
                except Exception as e:
                    print(f"WS Port Error: {e}")
                    break
            
            if not found:
                print(f"WS Error: Could not find free port for WebSocket server.")
            self.ws_ready.set()

        try:
            self.ws_loop.run_until_complete(ws_main())
        except Exception as e:
            print(f'WS Loop Error: {e}')
        finally:
            # Cleanly shut down the loop
            try:
                # Cancel all pending tasks
                tasks = asyncio.all_tasks(self.ws_loop)
                for task in tasks:
                    task.cancel()
                
                # Run the loop until all tasks are cancelled
                if tasks:
                    self.ws_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                
                self.ws_loop.run_until_complete(self.ws_loop.shutdown_asyncgens())
                self.ws_loop.close()
            except Exception:
                pass
            self.ws_loop = None
            self.ws_ready.set()

    async def _ws_handler(self, websocket):
        # Path filtering to prevent connection to/from other applications
        # Newer websockets versions store the path in websocket.request.path
        try:
            path = getattr(websocket, 'path', None)
            if path is None and hasattr(websocket, 'request'):
                path = websocket.request.path
        except Exception:
            path = None

        if path != "/better_planetside":
            server_log(f"WS CONNECTION REJECTED: Invalid path {path}")
            await websocket.close(1008, "Invalid Path")
            return

        self.ws_clients.add(websocket)
        try:
            with self._state_lock:
                replay = list(self._state_cache.values())
            if self.ws_batching_v2 and replay:
                await websocket.send(json.dumps({
                    "kind": "batch",
                    "tick_ts_ms": int(time.time() * 1000),
                    "events": replay,
                }))
            else:
                for payload in replay:
                    await websocket.send(json.dumps(payload))
            await websocket.wait_closed()
        finally:
            self.ws_clients.discard(websocket)

    def broadcast(self, category, data):
        now_ms = int(time.time() * 1000)
        payload_data = data if isinstance(data, dict) else {"value": data}
        payload_data = dict(payload_data)

        # Dev override for legacy overlay visibility while keeping pipeline active.
        if str(category or "").strip().lower() == "overlay_visibility":
            target = str(payload_data.get("target", "") or "").strip().lower()
            # Dev legacy visibility override must not affect Tauri-targeted
            # visibility events, otherwise Tauri can be forced hidden forever.
            if target == "tauri":
                target = "tauri"
            else:
                target = "legacy"
            mode = str(self._dev_overlay_visibility_mode or "auto")
            if target == "legacy":
                if mode == "hide":
                    payload_data["visible"] = False
                elif mode == "show":
                    payload_data["visible"] = True

        payload_data.setdefault("ts_source_ms", now_ms)
        payload_data["ts_server_rx_ms"] = now_ms

        if not self.event_pipeline_v2:
            wire_msg = {
                'category': str(category or "unknown"),
                'data': payload_data,
            }
            try:
                evt = normalize_overlay_event(category, payload_data, seq=0)
                lane = evt["category"]
            except Exception:
                lane = "normal"
            if self.trace_export:
                self._append_trace_log(
                    lane=lane,
                    wire_category=wire_msg.get("category"),
                    payload_data=payload_data,
                    meta={"mode": "legacy"},
                )
            with self._state_lock:
                self._metrics["events_in_total"] += 1
                self._increment_lane_metric("in", lane)
                self._metrics["events_out_total"] += 1
                self._increment_lane_metric("out", lane)
                self._metrics["flush_count"] += 1
                self._metrics["legacy_flush_count"] += 1
                self._metrics["last_flush_size"] = 1
                self._metrics["last_batch_size"] = 1
                if lane == "state":
                    self._state_cache[str(category or "unknown")] = wire_msg
                should_emit_metrics = (
                    self.perf_debug and (int(time.time() * 1000) - self._last_metrics_emit_ms) >= 1000
                )
                if should_emit_metrics:
                    self._last_metrics_emit_ms = int(time.time() * 1000)
                    metrics_data = self._build_metrics_payload()
                    metrics_payload = json.dumps({
                        "category": "perf_stats",
                        "data": metrics_data
                    })
                    self._append_perf_log(metrics_data)
                else:
                    metrics_payload = None

            if not self.is_running or not self.ws_loop or not self.ws_clients:
                return

            try:
                asyncio.run_coroutine_threadsafe(
                    self._ws_broadcast(json.dumps(wire_msg)),
                    self.ws_loop
                )
                if metrics_payload:
                    asyncio.run_coroutine_threadsafe(
                        self._ws_broadcast(metrics_payload),
                        self.ws_loop
                    )
            except Exception:
                pass
            return

        with self._state_lock:
            self._metrics["events_in_total"] += 1
            self._msg_seq += 1
            seq = self._msg_seq
            evt = normalize_overlay_event(category, payload_data, seq=seq)
            lane = evt["category"]
            self._increment_lane_metric("in", lane)

            wire_msg = {
                'category': evt["type"],
                'data': payload_data,
                'meta': {
                    'seq': seq,
                    'v2': {
                        'id': evt["id"],
                        'category': evt["category"],
                        'priority': evt["priority"],
                        'coalesce_key': evt["coalesce_key"],
                        'dedupe_key': evt["dedupe_key"],
                    }
                }
            }
            if self.trace_export:
                self._append_trace_log(
                    lane=lane,
                    wire_category=wire_msg.get("category"),
                    payload_data=payload_data,
                    meta=wire_msg.get("meta"),
                )

            is_state = (lane == "state")
            if is_state:
                # Replay cache is only for persistent state.
                self._state_cache[evt["type"]] = wire_msg
                replaced = evt["type"] in self._pending_state_by_type
                if replaced:
                    self._metrics["coalesce_replaced"] += 1
                self._pending_state_by_type[evt["type"]] = (wire_msg, lane)
                pending_state_len = len(self._pending_state_by_type)
                if pending_state_len > self._metrics["max_pending_state"]:
                    self._metrics["max_pending_state"] = pending_state_len
            else:
                dedupe_key = str(evt.get("dedupe_key") or "")
                if self._should_dedupe_transient(lane, dedupe_key, now_ms):
                    self._metrics["deduped_total"] += 1
                    self._metrics["dropped_total"] += 1
                    return

                # Hard limit cosmetic queue share so hitmarker bursts can never starve normal events.
                if lane == "cosmetic":
                    if self._pending_cosmetic_count() >= self._max_cosmetic_pending():
                        self._metrics["dropped_total"] += 1
                        self._metrics["dropped_transient_overflow"] += 1
                        self._metrics["dropped_cosmetic_total"] += 1
                        return

                # Transient events are queued FIFO and batched on next flush tick.
                if len(self._pending_transient) >= self._max_transient_pending:
                    if not self._make_transient_room_for_lane(lane):
                        self._metrics["dropped_total"] += 1
                        self._metrics["dropped_transient_overflow"] += 1
                        if lane == "cosmetic":
                            self._metrics["dropped_cosmetic_total"] += 1
                        elif lane == "normal":
                            self._metrics["dropped_normal_total"] += 1
                        return
                self._pending_transient.append((wire_msg, lane, dedupe_key))
                pending_transient_len = len(self._pending_transient)
                if pending_transient_len > self._metrics["max_pending_transient"]:
                    self._metrics["max_pending_transient"] = pending_transient_len

        if not self.is_running or not self.ws_loop or not self.ws_clients:
            return

        try:
            self.ws_loop.call_soon_threadsafe(self._schedule_flush)
        except Exception:
            pass

    def _schedule_flush(self):
        if self._flush_scheduled:
            return
        if self._flush_task and not self._flush_task.done():
            return
        now = self.ws_loop.time() if self.ws_loop else 0.0
        delay = max(0.0, self._next_flush_at - now)
        self._flush_scheduled = True
        self.ws_loop.call_later(delay, self._run_scheduled_flush)

    def _run_scheduled_flush(self):
        self._flush_scheduled = False
        if self._flush_task and not self._flush_task.done():
            self._schedule_flush()
            return
        self._flush_task = asyncio.create_task(self._flush_pending_broadcasts())

    async def _flush_pending_broadcasts(self):
        with self._state_lock:
            if not self._pending_state_by_type and not self._pending_transient:
                return
            pending_items = list(self._pending_state_by_type.values())
            self._pending_state_by_type.clear()
            if self._pending_transient:
                pending_items.extend(self._pending_transient)
                self._pending_transient.clear()
            pending_messages = [item[0] for item in pending_items]
            for item in pending_items:
                lane = item[1] if len(item) >= 2 else "normal"
                self._increment_lane_metric("out", lane)
            self._metrics["flush_count"] += 1
            self._metrics["last_flush_size"] = len(pending_messages)
            self._metrics["events_out_total"] += len(pending_messages)
            should_emit_metrics = (
                self.perf_debug and (int(time.time() * 1000) - self._last_metrics_emit_ms) >= 1000
            )
            if should_emit_metrics:
                self._last_metrics_emit_ms = int(time.time() * 1000)
                metrics_data = self._build_metrics_payload()
                metrics_payload = json.dumps({
                    "category": "perf_stats",
                    "data": metrics_data
                })
                self._append_perf_log(metrics_data)
            else:
                metrics_payload = None

        if self.ws_batching_v2:
            self._metrics["batch_flush_count"] += 1
            self._metrics["last_batch_size"] = len(pending_messages)
            await self._ws_broadcast(json.dumps({
                "kind": "batch",
                "tick_ts_ms": int(time.time() * 1000),
                "events": pending_messages,
            }))
        else:
            self._metrics["legacy_flush_count"] += 1
            self._metrics["last_batch_size"] = 1
            for payload in pending_messages:
                await self._ws_broadcast(json.dumps(payload))
        if metrics_payload:
            await self._ws_broadcast(metrics_payload)

        # Pace next flush by configured target FPS.
        self._next_flush_at = (self.ws_loop.time() if self.ws_loop else 0.0) + self._flush_interval_s

        with self._state_lock:
            has_more = bool(self._pending_state_by_type or self._pending_transient)
        if has_more and self.ws_loop and self.is_running:
            self._schedule_flush()

    async def _ws_broadcast(self, message):
        if self.ws_clients:
            websockets.broadcast(self.ws_clients, message)

    def _build_metrics_payload(self):
        now_ms = int(time.time() * 1000)
        return {
            "ts_server_metrics_ms": now_ms,
            "perf_debug": bool(self.perf_debug),
            "target_fps": int(self.target_fps),
            "events_in_total": int(self._metrics["events_in_total"]),
            "events_out_total": int(self._metrics["events_out_total"]),
            "flush_count": int(self._metrics["flush_count"]),
            "last_flush_size": int(self._metrics["last_flush_size"]),
            "max_pending_state": int(self._metrics["max_pending_state"]),
            "max_pending_transient": int(self._metrics["max_pending_transient"]),
            "coalesce_replaced": int(self._metrics["coalesce_replaced"]),
            "dropped_total": int(self._metrics["dropped_total"]),
            "dropped_transient_overflow": int(self._metrics["dropped_transient_overflow"]),
            "deduped_total": int(self._metrics["deduped_total"]),
            "dropped_cosmetic_total": int(self._metrics["dropped_cosmetic_total"]),
            "dropped_normal_total": int(self._metrics["dropped_normal_total"]),
            "dedupe_window_ms": int(self._dedupe_window_ms),
            "max_transient_pending_cfg": int(self._max_transient_pending),
            "max_cosmetic_pending_cfg": int(self._max_cosmetic_pending()),
            "events_in_state": int(self._metrics["events_in_state"]),
            "events_in_critical": int(self._metrics["events_in_critical"]),
            "events_in_normal": int(self._metrics["events_in_normal"]),
            "events_in_cosmetic": int(self._metrics["events_in_cosmetic"]),
            "events_out_state": int(self._metrics["events_out_state"]),
            "events_out_critical": int(self._metrics["events_out_critical"]),
            "events_out_normal": int(self._metrics["events_out_normal"]),
            "events_out_cosmetic": int(self._metrics["events_out_cosmetic"]),
            "ws_batching_v2": bool(self.ws_batching_v2),
            "batch_flush_count": int(self._metrics["batch_flush_count"]),
            "legacy_flush_count": int(self._metrics["legacy_flush_count"]),
            "last_batch_size": int(self._metrics["last_batch_size"]),
            "event_pipeline_v2": bool(self.event_pipeline_v2),
            "js_scheduler_v2": bool(self.js_scheduler_v2),
        }

    def _append_perf_log(self, metrics):
        try:
            row = dict(metrics or {})
            row["ts_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(perf_log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        except Exception:
            pass

    def _append_trace_log(self, lane, wire_category, payload_data, meta=None):
        try:
            now_ms = int(time.time() * 1000)
            row = {
                "ts_server_trace_ms": now_ms,
                "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "lane": str(lane or "normal"),
                "category": str(wire_category or "unknown"),
                "data": dict(payload_data or {}),
            }
            if meta:
                row["meta"] = dict(meta)
            with open(trace_log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        except Exception:
            pass

    def _increment_lane_metric(self, direction, lane):
        lane_key = str(lane or "normal").strip().lower()
        if lane_key not in {"state", "critical", "normal", "cosmetic"}:
            lane_key = "normal"
        key = f"events_{direction}_{lane_key}"
        self._metrics[key] = int(self._metrics.get(key, 0)) + 1

    def _should_dedupe_transient(self, lane, dedupe_key, now_ms):
        lane_key = str(lane or "normal").strip().lower()
        # Never dedupe critical lane.
        if lane_key == "critical":
            return False
        if self._dedupe_window_ms <= 0:
            return False
        if not dedupe_key:
            return False

        lookup = f"{lane_key}:{dedupe_key}"
        last_seen = int(self._recent_dedupe.get(lookup, 0) or 0)
        self._recent_dedupe[lookup] = int(now_ms)
        # Best-effort cleanup
        self._cleanup_recent_dedupe(now_ms)
        return (now_ms - last_seen) <= int(self._dedupe_window_ms) if last_seen > 0 else False

    def _cleanup_recent_dedupe(self, now_ms):
        if len(self._recent_dedupe) < 2048:
            return
        cutoff = int(now_ms) - max(5000, int(self._dedupe_window_ms) * 8)
        stale = [k for k, v in self._recent_dedupe.items() if int(v) < cutoff]
        for k in stale[:2048]:
            self._recent_dedupe.pop(k, None)

    def _pending_cosmetic_count(self):
        return sum(1 for item in self._pending_transient if len(item) >= 2 and str(item[1]) == "cosmetic")

    def _max_cosmetic_pending(self):
        # Keep cosmetics bounded to avoid blocking normal/critical transients.
        cap = int(self._max_transient_pending)
        return max(16, min(256, cap // 6))

    def _make_transient_room_for_lane(self, incoming_lane):
        # Drop policy priority:
        # 1. oldest cosmetic
        # 2. oldest normal (only if incoming critical)
        # 3. no room
        if not self._pending_transient:
            return True

        # Remove oldest cosmetic first.
        for idx, item in enumerate(self._pending_transient):
            if len(item) >= 2 and str(item[1]) == "cosmetic":
                self._pending_transient.rotate(-idx)
                self._pending_transient.popleft()
                self._pending_transient.rotate(idx)
                self._metrics["dropped_total"] += 1
                self._metrics["dropped_transient_overflow"] += 1
                self._metrics["dropped_cosmetic_total"] += 1
                return True

        # For incoming critical, allow displacing oldest normal.
        if str(incoming_lane) == "critical":
            for idx, item in enumerate(self._pending_transient):
                if len(item) >= 2 and str(item[1]) == "normal":
                    self._pending_transient.rotate(-idx)
                    self._pending_transient.popleft()
                    self._pending_transient.rotate(idx)
                    self._metrics["dropped_total"] += 1
                    self._metrics["dropped_transient_overflow"] += 1
                    self._metrics["dropped_normal_total"] += 1
                    return True

        return False
