import os
import sys
import json
import threading
import asyncio
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, HTTPServer

import websockets
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
            payload = f'window.OVERLAY_CONFIG = {{ wsPort: {int(ws_port)} }};\n'
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
            if self.path in ('/', '/index.html'):
                return self._send_file(os.path.join(_overlay_web_dir(), 'index.html'), 'text/html; charset=utf-8')

            if self.path == '/overlay-config.js':
                return self._serve_overlay_config()

            if self.path.startswith('/web/'):
                return self._serve_web_file(self.path)

            if self.path.startswith('/assets/'):
                return self._serve_asset(self.path)

            if self.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            self.send_error(404, f'Path not found: {self.path}')
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
        self._pending_by_category = {}
        self._flush_task = None

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
            self._pending_by_category.clear()
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
            for payload in replay:
                await websocket.send(payload)
            await websocket.wait_closed()
        finally:
            self.ws_clients.discard(websocket)

    def broadcast(self, category, data):
        payload = json.dumps({'category': category, 'data': data})

        with self._state_lock:
            self._state_cache[category] = payload
            # Coalesce by category: keep only newest payload per category.
            self._pending_by_category[category] = payload

        if not self.is_running or not self.ws_loop or not self.ws_clients:
            return

        try:
            self.ws_loop.call_soon_threadsafe(self._schedule_flush)
        except Exception:
            pass

    def _schedule_flush(self):
        if self._flush_task and not self._flush_task.done():
            return
        self._flush_task = asyncio.create_task(self._flush_pending_broadcasts())

    async def _flush_pending_broadcasts(self):
        while True:
            with self._state_lock:
                if not self._pending_by_category:
                    break
                pending_payloads = list(self._pending_by_category.values())
                self._pending_by_category.clear()

            for payload in pending_payloads:
                await self._ws_broadcast(payload)

    async def _ws_broadcast(self, message):
        if self.ws_clients:
            websockets.broadcast(self.ws_clients, message)
