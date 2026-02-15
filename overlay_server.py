import os
import sys
import json
import threading
import asyncio
from urllib.parse import unquote
from http.server import SimpleHTTPRequestHandler, HTTPServer

import websockets

HTTP_PORT = 8000
WS_PORT = 6789


def _project_root():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _overlay_web_dir():
    return os.path.join(_project_root(), 'web_overlay')


def _assets_dir():
    return os.path.join(_project_root(), 'assets')


class AssetHTTPHandler(SimpleHTTPRequestHandler):
    def _send_file(self, full_path, content_type='text/plain; charset=utf-8'):
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            self.send_error(404, 'File not found')
            return

        with open(full_path, 'rb') as f:
            data = f.read()

        self.send_response(200)
        self.send_header('Content-type', content_type)
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def _serve_overlay_config(self):
        ws_port = getattr(self.server, 'ws_port', WS_PORT)
        payload = f'window.OVERLAY_CONFIG = {{ wsPort: {int(ws_port)} }};\n'
        data = payload.encode('utf-8')

        self.send_response(200)
        self.send_header('Content-type', 'application/javascript; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

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
                self.directory = os.path.dirname(candidate)
                self.path = '/' + os.path.basename(candidate)
                return super().do_GET()

        self.send_error(404, 'Asset not found')

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

        self.send_error(404, 'File not found')


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

    def start(self):
        if self.is_running:
            return

        self.is_running = True

        self.http_thread = threading.Thread(target=self._run_http, daemon=True)
        self.http_thread.start()

        self.ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        self.ws_thread.start()

    def stop(self):
        self.is_running = False

        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
            try:
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None

        if self.ws_loop:
            try:
                self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
            except Exception:
                pass
            self.ws_loop = None

    def _run_http(self):
        HTTPServer.allow_reuse_address = True
        try:
            self.httpd = HTTPServer(('0.0.0.0', self.http_port), AssetHTTPHandler)
            self.httpd.ws_port = self.ws_port
            print(f'WEB: Overlay ready at http://localhost:{self.http_port}')
            self.httpd.serve_forever()
        except OSError:
            print(f'WARNUNG: Port {self.http_port} ist belegt.')
        except Exception as e:
            print(f'HTTP Server Error: {e}')

    def _run_ws(self):
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)

        async def start_ws():
            try:
                async with websockets.serve(self._ws_handler, '0.0.0.0', self.ws_port):
                    await asyncio.Future()
            except Exception as e:
                print(f'WS Server Error: {e}')

        print(f'WS: WebSocket listening on port {self.ws_port}')
        try:
            self.ws_loop.run_until_complete(start_ws())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f'WS Loop Error: {e}')

    async def _ws_handler(self, websocket):
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

        if not self.is_running or not self.ws_loop or not self.ws_clients:
            return

        asyncio.run_coroutine_threadsafe(self._ws_broadcast(payload), self.ws_loop)

    async def _ws_broadcast(self, message):
        if self.ws_clients:
            websockets.broadcast(self.ws_clients, message)
