(function () {
  class OverlaySocket {
    constructor(onMessage) {
      this.onMessage = onMessage;
      this.ws = null;
      this.retryDelayMs = 1000;
      this.maxRetryMs = 12000;
      this.retryTimer = null;
      this.connect();
    }

    wsUrl() {
      const cfg = window.OVERLAY_CONFIG || {};
      const port = Number(cfg.wsPort || 31338);
      return `ws://127.0.0.1:${port}/better_planetside`;
    }

    connect() {
      this.clearRetry();
      this.ws = new WebSocket(this.wsUrl());

      this.ws.onopen = () => {
        this.retryDelayMs = 1000;
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const rxMs = performance.now();
          if (payload && payload.kind === "batch" && Array.isArray(payload.events)) {
            payload.events.forEach((msg, idx) => {
              if (msg && typeof msg === "object") {
                msg.__perf_ws_rx_ms = rxMs;
                msg.__from_batch = true;
                msg.__batch_index = idx;
                msg.__batch_size = payload.events.length;
              }
              this.onMessage(msg);
            });
          } else {
            if (payload && typeof payload === "object") {
              payload.__perf_ws_rx_ms = rxMs;
              payload.__from_batch = false;
            }
            this.onMessage(payload);
          }
        } catch (_) {
          // Ignore malformed payloads.
        }
      };

      this.ws.onclose = () => {
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        if (this.ws) {
          this.ws.close();
        }
      };
    }

    scheduleReconnect() {
      this.clearRetry();
      this.retryTimer = setTimeout(() => {
        this.connect();
      }, this.retryDelayMs);
      this.retryDelayMs = Math.min(this.retryDelayMs * 1.8, this.maxRetryMs);
    }

    clearRetry() {
      if (this.retryTimer) {
        clearTimeout(this.retryTimer);
        this.retryTimer = null;
      }
    }
  }

  window.OverlaySocket = OverlaySocket;
})();
