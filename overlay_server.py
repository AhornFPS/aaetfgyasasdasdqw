import os
import sys
import json
import threading
import asyncio
import websockets
from http.server import SimpleHTTPRequestHandler, HTTPServer

# --- CONFIGURATION ---
HTTP_PORT = 8000
WS_PORT = 6789

# HTML TEMPLATE WITH AUTO-RECONNECT
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Dior Overlay</title>
    <style>
        body { margin: 0; padding: 0; overflow: hidden; font-family: 'Segoe UI', sans-serif; background: transparent; }

        /* Base Classes */
        .overlay-element {
            position: absolute;
            transform-origin: top left;
            transition: opacity 0.3s, transform 0.3s;
        }

        /* Status Indicator (Debug) */
        #status-dot {
            position: absolute; top: 10px; left: 10px;
            width: 10px; height: 10px; border-radius: 50%;
            background-color: red; z-index: 9999;
            opacity: 0.8;
        }

        /* Killfeed Container */
        #feed-layer {
            width: 600px; 
            display: flex; 
            flex-direction: column; 
            align-items: flex-end; 
        }

        .feed-item { animation: fadeIn 0.5s; margin-bottom: 2px; }
        @keyframes fadeIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
    </style>
</head>
<body>
    <div id="status-dot"></div>

    <img id="event-layer" class="overlay-element" src="" style="display:none; width: 200px;">

    <div id="feed-layer" class="overlay-element"></div>

    <div id="stats-layer" class="overlay-element"></div>

    <script>
        const WS_PORT = __WS_PORT__;
        let ws;
        let retryInterval = 3000; // Retry every 3 seconds

        function connect() {
            const dot = document.getElementById("status-dot");

            console.log("Attempting to connect to WebSocket...");
            ws = new WebSocket("ws://localhost:" + WS_PORT);

            ws.onopen = () => { 
                console.log("Connected!"); 
                dot.style.backgroundColor = "#00ff00"; // Grün
                // Hide after 1 second if everything is okay
                setTimeout(() => { dot.style.opacity = 0; }, 1000);
            };

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                const data = msg.data;

                if (msg.category === "event") {
                    showEvent(data);
                } else if (msg.category === "feed") {
                    updateFeed(data);
                } else if (msg.category === "stats") {
                    updateStats(data);
                }
            };

            ws.onclose = (e) => {
                console.log("Connection lost. Restarting in " + retryInterval + "ms", e.reason);
                dot.style.backgroundColor = "red";
                dot.style.opacity = 1;
                // Auto-Reconnect
                setTimeout(connect, retryInterval);
            };

            ws.onerror = (err) => {
                console.error("Socket Error:", err);
                ws.close(); // Forces onclose and thus the reconnect
            };
        }

        // Initialize
        connect();

        // --- VISUAL FUNCTIONS ---

        function applyPos(elem, data) {
            if (data.x !== undefined) elem.style.left = data.x + "px";
            if (data.y !== undefined) elem.style.top = data.y + "px";
            if (data.scale !== undefined) elem.style.transform = `scale(${data.scale})`;
        }

        function showEvent(data) {
            const img = document.getElementById("event-layer");
            img.src = "/assets/" + data.filename; 
            applyPos(img, data);
            img.style.display = "block";
            img.style.width = "auto"; 
            img.style.maxHeight = "300px"; 
            setTimeout(() => { img.style.display = "none"; }, data.duration);
        }

        function updateFeed(data) {
            const container = document.getElementById("feed-layer");
            applyPos(container, data);

            const div = document.createElement("div");
            div.className = "feed-item";
            div.innerHTML = data.html;

            const imgs = div.getElementsByTagName("img");
            for (let img of imgs) {
                let src = img.getAttribute("src");
                    let filename = src.split(/[\\\\/]/).pop(); 
                    img.src = "/assets/" + filename;
                }
            }

            container.prepend(div);
            if (container.children.length > 6) container.lastChild.remove();
            setTimeout(() => { if(div.parentNode) div.remove(); }, 10000);
        }

        function updateStats(data) {
            const container = document.getElementById("stats-layer");
            applyPos(container, data);

            let bgStyle = "";
            if (data.bg_filename) {
                bgStyle = `background-image: url('/assets/${data.bg_filename}'); background-size: 100% 100%; background-repeat: no-repeat; padding: 15px;`;
            }
            container.innerHTML = `<div style="${bgStyle} min-width: 300px;">${data.html}</div>`;
        }
    </script>
</body>
</html>
"""


class AssetHTTPHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # 1. Main page
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            # Der Port wird jetzt dynamisch vom Server-Objekt geholt
            ws_port = getattr(self.server, 'ws_port', 6789)
            html = HTML_TEMPLATE.replace("__WS_PORT__", str(ws_port))
            self.wfile.write(html.encode('utf-8'))
            return
        # 2. Assets (Bilder)
        if self.path.startswith('/assets/'):
            filename = self.path.replace('/assets/', '')
            # Determine path to the actual assets folder
            if hasattr(sys, '_MEIPASS'):
                base_dir = os.path.join(sys._MEIPASS, "assets")
            else:
                base_dir = os.path.join(os.getcwd(), "assets")

            self.directory = base_dir
            
            # Subfolder Support: Check if file exists in root, then try subfolders
            local_path = os.path.join(base_dir, filename)
            if not os.path.exists(local_path):
                # Try Images
                if os.path.exists(os.path.join(base_dir, "Images", filename)):
                    filename = "Images/" + filename
                # Try Sounds
                elif os.path.exists(os.path.join(base_dir, "Sounds", filename)):
                    filename = "Sounds/" + filename
            
            self.path = '/' + filename
            return super().do_GET()

        # 3. Ignore favicon (prevents 404 spam in console)
        if self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return

        self.send_error(404, "File not found")


class OverlayServer:
    def __init__(self, http_port=8000, ws_port=6789):
        self.http_port = http_port
        self.ws_port = ws_port
        self.ws_clients = set()
        self.ws_loop = None
        self.httpd = None
        
        self.http_thread = None
        self.ws_thread = None
        self.is_running = False

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
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        
        if self.ws_loop:
            self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
            self.ws_loop = None

    def _run_http(self):
        HTTPServer.allow_reuse_address = True
        try:
            self.httpd = HTTPServer(('0.0.0.0', self.http_port), AssetHTTPHandler)
            # WICHTIG: Port an das Server-Objekt binden, damit Handler ihn findet
            self.httpd.ws_port = self.ws_port
            print(f"WEB: Overlay ready at http://localhost:{self.http_port}")
            self.httpd.serve_forever()
        except OSError:
            print(f"WARNUNG: Port {self.http_port} ist belegt.")
        except Exception as e:
            print(f"HTTP Server Error: {e}")

    def _run_ws(self):
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)

        async def start_ws():
            try:
                async with websockets.serve(self._ws_handler, "0.0.0.0", self.ws_port):
                    await asyncio.Future()  # run forever
            except Exception as e:
                print(f"WS Server Error: {e}")

        print(f"WS: WebSocket listening on port {self.ws_port}")
        try:
            self.ws_loop.run_until_complete(start_ws())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"WS Loop Error: {e}")

    async def _ws_handler(self, websocket):
        self.ws_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self.ws_clients.remove(websocket)

    def broadcast(self, category, data):
        if not self.is_running or not self.ws_loop or not self.ws_clients:
            return

        payload = json.dumps({"category": category, "data": data})
        asyncio.run_coroutine_threadsafe(self._ws_broadcast(payload), self.ws_loop)

    async def _ws_broadcast(self, message):
        if self.ws_clients:
            websockets.broadcast(self.ws_clients, message)
