let eventCount = 0;
let clickThrough = false;
let wsAttemptIndex = 0;
let wsCurrent = null;
let wsConnectedUrl = "";
let lastSnapshotPath = "";
let configuredHttpPort = null;
let configuredWsPort = null;
const assetUrlCache = new Map();
const assetImageCache = new Map(); // filename -> HTMLImageElement
const preloadInFlight = new Set();
const observedAssets = new Set();
const observedAssetOrder = [];
let assetCacheHits = 0;
let assetCacheMisses = 0;
let overlayMode = false;
let layoutEditMode = false;
let layoutEditTargets = [];
let activeDrag = null;
let lastLayoutExitMs = 0;
const LAT_WINDOW = 200;
const srcSamples = [];
const rxSamples = [];

const wsState = document.getElementById("ws-state");
const eventCountEl = document.getElementById("event-count");
const lastCategoryEl = document.getElementById("last-category");
const logEl = document.getElementById("log");
const toggleOverlayModeBtn = document.getElementById("toggle-overlay-mode");
const toggleLegacyOverlayBtn = document.getElementById("toggle-legacy-overlay");
const toggleBtn = document.getElementById("toggle-click");
const preloadAssetsBtn = document.getElementById("preload-assets");
const saveSnapshotBtn = document.getElementById("save-snapshot");
const copySnapshotPathBtn = document.getElementById("copy-snapshot-path");
const clearBtn = document.getElementById("clear-log");
const eventStageEl = document.getElementById("event-stage");
const burstLayerEl = document.getElementById("burst-layer");
const impactWaveEl = document.getElementById("impact-wave");
const headshotFlashEl = document.getElementById("headshot-flash");
const feedLayerEl = document.getElementById("feed-layer");
const statsLayerEl = document.getElementById("stats-layer");
const streakLayerEl = document.getElementById("streak-layer");
const twitchLayerEl = document.getElementById("twitch-layer");
const layoutEditLayerEl = document.getElementById("layout-edit-layer");
const eventsLayerEl = document.getElementById("events-layer");
const hitmarkerLayerEl = document.getElementById("hitmarker-layer");
const crosshairLayerEl = document.getElementById("crosshair-layer");
const latSrcLastEl = document.getElementById("lat-src-last");
const latSrcP50P95El = document.getElementById("lat-src-p50p95");
const latRxLastEl = document.getElementById("lat-rx-last");
const latRxP50P95El = document.getElementById("lat-rx-p50p95");
const telemetryLeftEl = document.getElementById("telemetry-left");
const telemetryRightEl = document.getElementById("telemetry-right");
const lastSnapshotPathEl = document.getElementById("last-snapshot-path");
const assetCacheStatsEl = document.getElementById("asset-cache-stats");
const nativeOverlayEl = document.getElementById("native-overlay");

const MAX_ASSET_CACHE = 50;
const LAYOUT_SNAP_THRESHOLD = 12;

let overlayVisible = false;
let scifiEnabled = true;
try {
  const persistedSciFi = window.localStorage.getItem("tauri_scifi_enabled");
  if (persistedSciFi === "0") {
    scifiEnabled = false;
  } else if (persistedSciFi === "1") {
    scifiEnabled = true;
  }
} catch {}
document.body.classList.toggle("scifi-off", !scifiEnabled);
let suppressLegacyOverlay = false;
let wsConnectedAtMs = 0;
const STARTUP_QUIET_MS = 1300;
let feedConfig = { x: 0, y: 0, width: 600, height: 550, max_items: 6 };
let twitchConfig = { x: 50, y: 300, width: 350, height: 400, opacity: 30, font_size: 12 };
let twitchVisible = false;
let lastStatsPayload = null;
let lastCrosshairPayload = null;
let lastStreakPayload = null;
let layoutPreview = { event: false, streak: false, stats: false };
const activeTransientByKey = new Map();
const systemPips = {};
document.querySelectorAll(".sys-pip").forEach((el) => {
  systemPips[String(el.dataset.system || "").toLowerCase()] = el;
});

function invokeBridge() {
  return (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke)
    || (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke);
}

async function loadConfiguredOverlayPorts() {
  const invoke = invokeBridge();
  if (!invoke) return;
  try {
    const res = await invoke("get_overlay_service_ports");
    const hp = Number(res && res.http_port);
    const wp = Number(res && res.ws_port);
    if (Number.isFinite(hp) && hp > 0) configuredHttpPort = hp;
    if (Number.isFinite(wp) && wp > 0) configuredWsPort = wp;
    appendLog(
      `[overlay] port source=${res && res.source ? res.source : "default"} http=${configuredHttpPort ?? "-"} ws=${configuredWsPort ?? "-"}`,
      "ok",
    );
  } catch {
    // fallback to defaults/probing
  }
}

function appendLog(line, cls = "") {
  const row = document.createElement("div");
  if (cls) row.className = cls;
  row.textContent = line;
  logEl.appendChild(row);
  logEl.scrollTop = logEl.scrollHeight;
}

function updateClock() {
  if (!telemetryRightEl) return;
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  telemetryRightEl.textContent = `${hh}:${mm}:${ss}`;
}

function inStartupQuietPeriod() {
  return wsConnectedAtMs > 0 && (Date.now() - wsConnectedAtMs) < STARTUP_QUIET_MS;
}

function setTelemetry(text) {
  if (!scifiEnabled || !telemetryLeftEl || !text) return;
  telemetryLeftEl.textContent = text;
}

function applyOverlayVisibility(visible) {
  overlayVisible = Boolean(visible);
  if (!overlayVisible) {
    clearEventsLayer();
    if (feedLayerEl) feedLayerEl.innerHTML = "";
    if (streakLayerEl) streakLayerEl.innerHTML = "";
    if (burstLayerEl) burstLayerEl.innerHTML = "";
    if (impactWaveEl) impactWaveEl.classList.remove("active");
    if (headshotFlashEl) headshotFlashEl.classList.remove("active");
  }
  if (feedLayerEl) feedLayerEl.style.display = overlayVisible ? "block" : "none";
  if (twitchLayerEl) twitchLayerEl.style.display = (overlayVisible && twitchVisible) ? "block" : "none";
  if (statsLayerEl) statsLayerEl.style.display = overlayVisible ? "block" : "none";
  if (streakLayerEl) streakLayerEl.style.display = overlayVisible ? "block" : "none";
  if (eventsLayerEl) eventsLayerEl.style.display = overlayVisible ? "block" : "none";
  if (hitmarkerLayerEl) hitmarkerLayerEl.style.display = overlayVisible ? "block" : "none";
  if (crosshairLayerEl) crosshairLayerEl.style.display = overlayVisible ? "block" : "none";
  if (nativeOverlayEl) nativeOverlayEl.style.visibility = overlayVisible ? "visible" : "hidden";
  updateLayoutEditTargets();
}

function applyTwitchConfig(data) {
  if (!twitchLayerEl || !data) return;
  twitchConfig = {
    x: Number(data.x ?? twitchConfig.x ?? 50),
    y: Number(data.y ?? twitchConfig.y ?? 300),
    width: Number(data.width ?? twitchConfig.width ?? 350),
    height: Number(data.height ?? twitchConfig.height ?? 400),
    opacity: Number(data.opacity ?? twitchConfig.opacity ?? 30),
    font_size: Number(data.font_size ?? twitchConfig.font_size ?? 12),
  };
  twitchLayerEl.style.left = `${twitchConfig.x}px`;
  twitchLayerEl.style.top = `${twitchConfig.y}px`;
  twitchLayerEl.style.width = `${twitchConfig.width}px`;
  twitchLayerEl.style.height = `${twitchConfig.height}px`;
  const alpha = Math.max(0, Math.min(1, twitchConfig.opacity / 100));
  twitchLayerEl.style.backgroundColor = `rgba(0, 0, 0, ${alpha})`;
  updateLayoutEditTargets();
}

function setTwitchVisibility(data) {
  twitchVisible = !(data && data.visible === false);
  if (twitchLayerEl) twitchLayerEl.style.display = (overlayVisible && twitchVisible) ? "block" : "none";
}

function appendTwitchMessage(data) {
  if (!twitchLayerEl || !data) return;
  applyTwitchConfig(data);
  const row = document.createElement("div");
  row.className = "overlay-twitch-msg";
  const user = String(data.user || "");
  const color = String(data.color || "#00f2ff");
  const fontSize = Number(data.font_size || twitchConfig.font_size || 12);
  const html = String(data.html || "");
  row.style.fontSize = `${fontSize}pt`;
  row.innerHTML = `<span style="color:${color}; font-weight:900;">${user}:</span> ${html}`;
  const imgs = row.querySelectorAll("img");
  imgs.forEach((img) => {
    const src = img.getAttribute("src") || "";
    if (src.startsWith("file:///")) return;
    img.src = assetUrl(src);
    img.style.maxHeight = "2em";
    img.style.verticalAlign = "middle";
  });
  twitchLayerEl.appendChild(row);
  while (twitchLayerEl.childElementCount > 50) {
    twitchLayerEl.removeChild(twitchLayerEl.firstElementChild);
  }
  const holdSeconds = Number(data.hold_seconds || 0);
  if (holdSeconds > 0) {
    setTimeout(() => {
      row.classList.add("fade-out");
      setTimeout(() => row.remove(), 1000);
    }, holdSeconds * 1000);
  }
}

function activateSystem(name, warn = false) {
  if (inStartupQuietPeriod()) return;
  if (!scifiEnabled) return;
  const pip = systemPips[String(name || "").toLowerCase()];
  if (!pip) return;
  pip.classList.remove("active", "warn");
  // restart animation
  void pip.offsetWidth;
  pip.classList.add("active");
  if (warn) pip.classList.add("warn");
  setTimeout(() => pip.classList.remove("active", "warn"), 320);
}

function spawnBurst(x, y, warn = false) {
  if (inStartupQuietPeriod()) return;
  if (!scifiEnabled || !burstLayerEl) return;
  const burst = document.createElement("div");
  burst.className = warn ? "fx-burst warn" : "fx-burst";
  burst.style.left = `${Number(x)}px`;
  burst.style.top = `${Number(y)}px`;
  burstLayerEl.appendChild(burst);
  setTimeout(() => burst.remove(), 560);
}

function spawnGlitch(x, y, warn = false, glowColor = "") {
  if (inStartupQuietPeriod()) return;
  if (!burstLayerEl) return;
  const glitch = document.createElement("div");
  glitch.className = warn ? "fx-glitch warn" : "fx-glitch";
  glitch.style.left = `${Number(x)}px`;
  glitch.style.top = `${Number(y)}px`;
  if (glowColor) {
    const cHi = rgbaFromHex(glowColor, 0.92);
    const cMid = rgbaFromHex(glowColor, 0.42);
    const cShadow = rgbaFromHex(glowColor, 0.56);
    if (cHi) glitch.style.setProperty("--glitch-hi", cHi);
    if (cMid) glitch.style.setProperty("--glitch-mid", cMid);
    if (cShadow) glitch.style.setProperty("--glitch-shadow", cShadow);
  }
  glitch.style.setProperty("--glitch-rot", `${Math.round((Math.random() * 14) - 7)}deg`);
  burstLayerEl.appendChild(glitch);
  setTimeout(() => glitch.remove(), 320);
}

function parseHexColor(value) {
  const v = String(value || "").trim();
  const m = v.match(/^#([0-9a-f]{6})$/i);
  if (!m) return null;
  const n = m[1];
  return {
    r: parseInt(n.slice(0, 2), 16),
    g: parseInt(n.slice(2, 4), 16),
    b: parseInt(n.slice(4, 6), 16),
  };
}

function rgbaFromHex(hex, alpha) {
  const c = parseHexColor(hex);
  if (!c) return "";
  return `rgba(${c.r}, ${c.g}, ${c.b}, ${alpha})`;
}

function updateAssetCacheStatsUi() {
  if (!assetCacheStatsEl) return;
  assetCacheStatsEl.textContent =
    `hits ${assetCacheHits} / misses ${assetCacheMisses} / preloaded ${assetImageCache.size}`;
}

function setWsState(text, ok) {
  wsState.textContent = text;
  wsState.className = ok ? "ok" : "bad";
}

function percentile(arr, p) {
  if (!arr.length) return null;
  const sorted = arr.slice().sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor((p / 100) * sorted.length)));
  return sorted[idx];
}

function pushSample(buf, v) {
  buf.push(v);
  if (buf.length > LAT_WINDOW) buf.shift();
}

function formatMs(v) {
  return v == null ? "-" : `${Math.round(v)} ms`;
}

function updateLatencyUi() {
  const srcP50 = percentile(srcSamples, 50);
  const srcP95 = percentile(srcSamples, 95);
  const rxP50 = percentile(rxSamples, 50);
  const rxP95 = percentile(rxSamples, 95);

  latSrcP50P95El.textContent = srcP50 == null ? "-" : `${Math.round(srcP50)} / ${Math.round(srcP95)} ms`;
  latRxP50P95El.textContent = rxP50 == null ? "-" : `${Math.round(rxP50)} / ${Math.round(rxP95)} ms`;
}

function latencySummary(buf) {
  if (!buf.length) return { count: 0, last_ms: null, p50_ms: null, p95_ms: null };
  return {
    count: buf.length,
    last_ms: Math.round(buf[buf.length - 1]),
    p50_ms: Math.round(percentile(buf, 50)),
    p95_ms: Math.round(percentile(buf, 95)),
  };
}

function connectedWsPort() {
  try {
    if (!wsConnectedUrl) return 31338;
    const u = new URL(wsConnectedUrl);
    return Number(u.port || 31338);
  } catch {
    return 31338;
  }
}

function assetBaseCandidates() {
  const wsPort = connectedWsPort();
  const wsPorts = new Set([wsPort, configuredWsPort, 31338, 31339].filter((p) => Number.isFinite(p) && p > 0));
  const ports = [configuredHttpPort, 31337, 31340, 31341];
  const uniq = [];
  for (const p of ports) {
    if (!Number.isFinite(p) || p <= 0) continue;
    if (wsPorts.has(p)) continue;
    if (!uniq.includes(p)) uniq.push(p);
  }
  return uniq.map((p) => `http://127.0.0.1:${p}/assets/`);
}

function basenameOf(input) {
  if (!input || typeof input !== "string") return "";
  const raw = input.trim();
  if (!raw) return "";
  const parts = raw.split(/[\\/]/);
  return parts[parts.length - 1];
}

function testImageUrl(url, timeoutMs = 400) {
  return new Promise((resolve) => {
    const img = new Image();
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      resolve(ok);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    img.onload = () => {
      clearTimeout(timer);
      finish(true);
    };
    img.onerror = () => {
      clearTimeout(timer);
      finish(false);
    };
    img.src = url;
  });
}

async function resolveAssetUrl(filename) {
  const name = basenameOf(filename);
  if (!name) return null;
  if (assetUrlCache.has(name)) return assetUrlCache.get(name);

  for (const base of assetBaseCandidates()) {
    const url = `${base}${encodeURIComponent(name)}`;
    // eslint-disable-next-line no-await-in-loop
    const ok = await testImageUrl(url);
    if (ok) {
      assetUrlCache.set(name, url);
      return url;
    }
  }
  assetUrlCache.set(name, null);
  return null;
}

function pickAssetFilename(data) {
  if (!data || typeof data !== "object") return "";
  const candidates = [data.filename, data.bg_filename, data.hs_icon, data.img, data.icon];
  for (const c of candidates) {
    const b = basenameOf(c);
    if (b) return b;
  }
  return "";
}

async function preloadAsset(filename) {
  const name = basenameOf(filename);
  if (!name) return false;
  if (assetImageCache.has(name)) return true;
  if (assetImageCache.size >= MAX_ASSET_CACHE) return false;
  if (preloadInFlight.has(name)) return false;
  preloadInFlight.add(name);
  try {
    const url = await resolveAssetUrl(name);
    if (!url) return false;
    const img = new Image();
    img.className = "event-thumb";
    img.alt = name;
    await new Promise((resolve, reject) => {
      img.onload = () => resolve(true);
      img.onerror = () => reject(new Error("image load failed"));
      img.src = url;
    });
    assetImageCache.set(name, img);
    updateAssetCacheStatsUi();
    return true;
  } catch {
    return false;
  } finally {
    preloadInFlight.delete(name);
  }
}

async function preloadHotAssets() {
  const list = observedAssetOrder.slice(0, MAX_ASSET_CACHE);
  let loaded = 0;
  for (const name of list) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await preloadAsset(name);
    if (ok) loaded += 1;
  }
  appendLog(`[assets] preload complete loaded=${loaded} total=${list.length}`, "ok");
}

function assetUrl(filename) {
  const name = basenameOf(filename);
  if (!name) return "";
  const cached = assetUrlCache.get(name);
  if (cached) return cached;
  const fallbackPort = Number.isFinite(configuredHttpPort) && configuredHttpPort > 0
    ? configuredHttpPort
    : 31337;
  return `http://127.0.0.1:${fallbackPort}/assets/${encodeURIComponent(name)}`;
}

function setPos(el, data, centered, applyScale = true) {
  const x = Number(data && data.x ? data.x : 0);
  const y = Number(data && data.y ? data.y : 0);
  const scale = Number(data && data.scale ? data.scale : 1);
  if (centered) {
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.transformOrigin = "center center";
    el.style.transform = applyScale
      ? `translate(-50%, -50%) scale(${scale})`
      : "translate(-50%, -50%)";
    return;
  }
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
  // Keep top-left anchoring stable even when scaling is applied.
  el.style.transformOrigin = "top left";
  el.style.transform = applyScale ? `scale(${scale})` : "none";
}

function clearEventsLayer() {
  activeTransientByKey.forEach((entry) => {
    if (entry && entry.timer) clearTimeout(entry.timer);
  });
  activeTransientByKey.clear();
  if (eventsLayerEl) eventsLayerEl.innerHTML = "";
  if (hitmarkerLayerEl) hitmarkerLayerEl.innerHTML = "";
  updateLayoutEditTargets();
}

function applyFeedConfig(data) {
  if (!feedLayerEl) return;
  feedConfig = {
    x: Number((data && data.x) || feedConfig.x || 0),
    y: Number((data && data.y) || feedConfig.y || 0),
    width: Number((data && data.width) || feedConfig.width || 600),
    height: Number((data && data.height) || feedConfig.height || 550),
    max_items: Number((data && data.max_items) || feedConfig.max_items || 6),
  };
  feedLayerEl.style.left = `${feedConfig.x}px`;
  feedLayerEl.style.top = `${feedConfig.y}px`;
  feedLayerEl.style.width = `${feedConfig.width}px`;
  feedLayerEl.style.maxHeight = `${feedConfig.height}px`;
  updateLayoutEditTargets();
}

function appendFeed(data) {
  if (!feedLayerEl || !data) return;
  applyFeedConfig(data);
  const item = document.createElement("div");
  item.className = "overlay-feed-item";
  const content = document.createElement("div");
  content.className = "overlay-feed-content";
  content.innerHTML = data.html || "";

  // Legacy parity: ensure feed text has the same shadow density even when
  // upstream HTML omitted text-shadow in inline styles.
  const textNodes = content.querySelectorAll("div, span");
  textNodes.forEach((el) => {
    if (!el.style.textShadow) {
      el.style.textShadow = "1px 1px 2px #000";
    }
  });
  item.appendChild(content);

  const imgs = content.querySelectorAll("img");
  imgs.forEach((img) => {
    const src = img.getAttribute("src") || "";
    img.src = assetUrl(src);
  });

  feedLayerEl.prepend(item);
  while (feedLayerEl.childElementCount > feedConfig.max_items) {
    feedLayerEl.removeChild(feedLayerEl.lastElementChild);
  }

  const autoRemove = data.auto_remove !== false;
  activateSystem("feed");
  setTelemetry("KILLFEED UPDATE");
  if (autoRemove) {
    const holdMs = Number(data.hold_ms || 10000);
    setTimeout(() => {
      item.classList.add("fade-out");
      setTimeout(() => item.remove(), 280);
    }, holdMs);
  }
}

function updateStats(data) {
  if (!statsLayerEl) return;
  if (!data || !data.html) {
    lastStatsPayload = null;
    statsLayerEl.innerHTML = "";
    updateLayoutEditTargets();
    return;
  }
  lastStatsPayload = { ...data };
  const card = document.createElement("div");
  card.className = "overlay-stats-card";
  card.innerHTML = data.html;
  const glowActive = data.glow !== false;
  if (!glowActive) {
    card.style.textShadow = "1px 1px 2px rgba(0,0,0,0.9)";
  } else if (data.glow_color) {
    card.style.textShadow =
      `1px 1px 2px rgba(0,0,0,0.9), 0 0 10px ${data.glow_color}, 0 0 24px ${data.glow_color}`;
  }
  setPos(card, {
    x: Number(data.x || 0) + Number((data.box_width || 450) / 2) + Number(data.tx || 0),
    y: Number(data.y || 0) + Number((data.box_height || 60) / 2) + Number(data.ty || 0),
    scale: 1
  }, true, false);
  statsLayerEl.replaceChildren(card);
  updateLayoutEditTargets();
  activateSystem("stats");
  setTelemetry("COMBAT METRICS SYNCHRONIZED");
}

function updateCrosshair(data) {
  if (!crosshairLayerEl) return;
  crosshairLayerEl.innerHTML = "";
  if (!data || !data.enabled || !data.filename) {
    lastCrosshairPayload = null;
    updateLayoutEditTargets();
    return;
  }
  lastCrosshairPayload = { ...data };

  if (data.shadow) {
    const core = document.createElement("div");
    core.className = "overlay-crosshair-core";
    const size = Number(data.size || 64);
    const coreSize = Math.max(5, Math.round(size * 0.26));
    core.style.width = `${coreSize}px`;
    core.style.height = `${coreSize}px`;
    setPos(core, data, true);
    crosshairLayerEl.appendChild(core);
  }

  const img = document.createElement("img");
  img.className = "overlay-transient";
  img.src = assetUrl(data.filename);
  img.style.width = `${Number(data.size || 64)}px`;
  img.style.height = `${Number(data.size || 64)}px`;
  setPos(img, data, true);
  crosshairLayerEl.appendChild(img);
  updateLayoutEditTargets();
  activateSystem("crosshair");
}

function renderStreak(data) {
  if (!streakLayerEl) return;
  streakLayerEl.innerHTML = "";
  if (!data || !data.visible) {
    lastStreakPayload = null;
    updateLayoutEditTargets();
    return;
  }
  lastStreakPayload = { ...data };

  const wrap = document.createElement("div");
  wrap.className = "overlay-streak";
  setPos(wrap, data, false);

  const knifeLayer = document.createElement("div");
  knifeLayer.className = "overlay-streak-knife-layer";
  if (data.anim_active !== false) {
    const speedVal = Number(data.anim_speed || 50);
    const duration = Math.max(0.6, Math.min(4.0, 120 / Math.max(1, speedVal)));
    knifeLayer.style.animation = `streakPulse ${duration.toFixed(2)}s ease-in-out infinite`;
  } else {
    knifeLayer.style.animation = "none";
  }
  wrap.appendChild(knifeLayer);

  if (data.bg_filename) {
    const bg = document.createElement("img");
    bg.className = "overlay-streak-bg";
    bg.src = assetUrl(data.bg_filename);
    bg.style.width = `${Number(data.bg_width || 200)}px`;
    bg.style.height = `${Number(data.bg_height || 200)}px`;
    wrap.appendChild(bg);
  }

  const knives = Array.isArray(data.knives) ? data.knives : [];
  const streakGlow = data.streak_glow !== false;
  for (const knife of knives) {
    if (!knife || !knife.filename) continue;
    const k = document.createElement("img");
    k.className = "overlay-knife";
    k.src = assetUrl(knife.filename);
    const kSize = Number(knife.size || 90);
    k.style.width = `${kSize}px`;
    k.style.height = `${kSize}px`;
    if (streakGlow && data.glow_color) {
      k.style.filter = `drop-shadow(0 0 7px ${data.glow_color})`;
    } else if (!streakGlow) {
      k.style.filter = "none";
    }
    const kx = Number(knife.x_off || 0);
    const ky = Number(knife.y_off || 0);
    const rot = Number(knife.rotation || 0);
    k.style.transform = `translate(-50%, -50%) translate(${kx}px, ${ky}px) rotate(${rot}deg)`;
    knifeLayer.appendChild(k);
  }

  const count = document.createElement("div");
  count.className = "overlay-streak-count";
  count.textContent = String(data.count || 0);
  count.style.fontSize = `${Number(data.font_size || 26)}px`;
  count.style.color = data.color || "#fff";
  count.style.fontWeight = data.bold ? "700" : "400";
  if (streakGlow && data.glow_color) {
    count.style.textShadow = `0 0 10px ${data.glow_color}, 0 0 24px ${data.glow_color}`;
  } else {
    count.style.textShadow = "none";
  }
  count.style.transform = `translate(-50%, -50%) translate(${Number(data.tx || 0)}px, ${Number(data.ty || 0)}px)`;
  wrap.appendChild(count);
  streakLayerEl.appendChild(wrap);
  updateLayoutEditTargets();
  activateSystem("streak");
  setTelemetry(`KILLSTREAK LOCKED: x${Number(data.count || 0)}`);
}

function pushTransientEvent(layerEl, data, fallbackType) {
  if (!layerEl || !data || !data.filename) return;
  const img = document.createElement("img");
  img.className = "overlay-transient";
  img.src = assetUrl(data.filename);
  img.style.width = `${Number(data.width || 220)}px`;
  img.style.height = `${Number(data.height || 220)}px`;

  const centered = Boolean(data.centered);
  const evType = String(data.event_type || fallbackType || "event").toLowerCase();
  const evClass = evType.includes("headshot")
    ? "event-headshot"
    : evType.includes("death")
      ? "event-death"
      : evType.includes("hitmarker")
        ? "event-hitmarker"
        : "event-generic";
  const warn = evType === "death";
  const glitchEnabled = shouldApplyGlitchFx(data, evType);
  const glowEnabled = data.glow !== false;
  const glowColor = glowEnabled ? String(data.glow_color || "").trim() : "";
  const message = data.__message || {};
  const coalesceKeyRaw = String(((((message.meta || {}).v2 || {}).coalesce_key) || "")).trim();
  // Keep hitmarkers stackable; only coalesce non-hitmarker event classes.
  const canCoalesce = !evType.includes("hitmarker");
  const mapKey = canCoalesce && coalesceKeyRaw ? `${evType}:${coalesceKeyRaw}` : "";
  let target = img;
  const existing = mapKey ? activeTransientByKey.get(mapKey) : null;
  if (existing && existing.el && existing.el.isConnected) {
    target = existing.el;
    target.src = img.src;
    target.style.width = img.style.width;
    target.style.height = img.style.height;
    target.classList.remove("fade-out");
    if (glitchEnabled) {
      pulseEventGlitch(layerEl, target, data, warn, glowColor);
    } else {
      target.classList.remove("glitch-impact");
    }
    if (!evType.includes("hitmarker")) {
      target.classList.toggle("no-glow", !glowEnabled);
      applyEventGlow(target, evType, glowEnabled, glowColor, glitchEnabled);
    }
  } else {
    target.classList.add("event-item", evClass);
    if (!evType.includes("hitmarker")) {
      target.classList.toggle("no-glow", !glowEnabled);
      applyEventGlow(target, evType, glowEnabled, glowColor, glitchEnabled);
    }
    layerEl.appendChild(target);
    if (glitchEnabled) pulseEventGlitch(layerEl, target, data, warn, glowColor);
    if (mapKey) activeTransientByKey.set(mapKey, { el: target, timer: null });
  }
  setPos(target, data, centered);

  const duration = Number(data.duration || 180);
  const armFade = () => {
    target.classList.add("fade-out");
    setTimeout(() => {
      if (target.parentNode) target.remove();
      if (mapKey) {
        const cur = activeTransientByKey.get(mapKey);
        if (cur && cur.el === target) activeTransientByKey.delete(mapKey);
      }
    }, 280);
  };
  if (mapKey) {
    const entry = activeTransientByKey.get(mapKey);
    if (entry && entry.timer) clearTimeout(entry.timer);
    const t = setTimeout(armFade, duration);
    if (entry) entry.timer = t;
    else activeTransientByKey.set(mapKey, { el: target, timer: t });
  } else {
    setTimeout(armFade, duration);
  }

  if (shouldTriggerImpact(data, evType)) {
    const cx = Number(data.x || 0) + Number(data.width || 220) / 2;
    const cy = Number(data.y || 0) + Number(data.height || 220) / 2;
    triggerImpact(evType, cx, cy, { glowEnabled, glowColor, glitchEnabled });
    if (glitchEnabled) spawnGlitch(cx, cy, warn, glowColor);
  } else if (evType.includes("hitmarker")) {
    const cx = Number(data.x || 0) + Number(data.width || 220) / 2;
    const cy = Number(data.y || 0) + Number(data.height || 220) / 2;
    spawnBurst(cx, cy, warn);
  }
  activateSystem(evType.includes("hitmarker") ? "event" : "event", warn);
  updateLayoutEditTargets();
}

function applyEventGlow(target, evType, glowEnabled, glowColor, glitchEnabled) {
  if (!target) return;
  const kind = String(evType || "").toLowerCase();
  if (kind.includes("hitmarker")) return;
  if (!glowEnabled) {
    target.style.filter = "";
    return;
  }
  // Keep glitch filter behavior untouched when glitch impact is active.
  if (glitchEnabled) {
    target.style.filter = "";
    return;
  }
  const useColor = glowColor || (
    kind.includes("headshot") || kind.includes("death")
      ? "rgba(255, 70, 70, 0.78)"
      : "rgba(0, 242, 255, 0.62)"
  );
  target.style.filter = `drop-shadow(0 0 8px ${useColor})`;
}

function shouldTriggerImpact(data, evType) {
  if (typeof data.impact === "boolean") {
    return data.impact;
  }
  return evType.includes("headshot") || evType.includes("death") || evType.includes("hitmarker");
}

function pulseEventGlitch(layerEl, target, data, warn = false, glowColor = "") {
  if (!layerEl || !target) return;
  if (glowColor) target.style.setProperty("--fx-color", glowColor);
  else target.style.removeProperty("--fx-color");
  target.classList.remove("glitch-impact");
  void target.offsetWidth;
  target.classList.add("glitch-impact");

  const makeSlice = (cls) => {
    const slice = document.createElement("img");
    slice.className = `overlay-transient event-glitch-slice ${cls}`;
    slice.src = target.src;
    slice.style.width = `${Number(data.width || 220)}px`;
    slice.style.height = `${Number(data.height || 220)}px`;
    if (glowColor) slice.style.setProperty("--fx-color", glowColor);
    else slice.style.removeProperty("--fx-color");
    setPos(slice, data, Boolean(data.centered));
    if (warn) slice.classList.add("warn");
    layerEl.appendChild(slice);
    setTimeout(() => {
      if (slice.parentNode) slice.remove();
    }, 220);
  };

  makeSlice("slice-a");
  makeSlice("slice-b");
}

function shouldApplyGlitchFx(data, evType) {
  if (String(evType || "").includes("hitmarker")) return false;
  if (typeof data.impact === "boolean") return data.impact;
  return String(evType || "").includes("headshot") || String(evType || "").includes("death");
}

function triggerImpact(evType, x, y, options = null) {
  const kind = String(evType || "").toLowerCase();
  const tx = Number.isFinite(Number(x)) ? Number(x) : window.innerWidth / 2;
  const ty = Number.isFinite(Number(y)) ? Number(y) : window.innerHeight / 2;
  const glowEnabled = !options || options.glowEnabled !== false;
  const glowColor = options && typeof options.glowColor === "string" ? options.glowColor : "";
  const glitchEnabled = !!(options && options.glitchEnabled);
  if (kind.includes("hitmarker")) {
    if (impactWaveEl) {
      impactWaveEl.classList.remove("active");
      void impactWaveEl.offsetWidth;
      impactWaveEl.classList.add("active");
    }
    return;
  }
  if (kind.includes("headshot")) {
    if (!glitchEnabled && headshotFlashEl) {
      headshotFlashEl.classList.remove("active");
      void headshotFlashEl.offsetWidth;
      headshotFlashEl.classList.add("active");
    }
    return;
  }
  if (impactWaveEl) {
    if (!glitchEnabled) {
      if (glowEnabled && glowColor) {
        const c0 = rgbaFromHex(glowColor, 0.28);
        const c1 = rgbaFromHex(glowColor, 0.0);
        if (c0 && c1) {
          impactWaveEl.style.background = `radial-gradient(circle at center, ${c0}, ${c1} 52%)`;
        }
      } else {
        impactWaveEl.style.background = "";
      }
      impactWaveEl.classList.remove("active");
      void impactWaveEl.offsetWidth;
      impactWaveEl.classList.add("active");
    } else {
      impactWaveEl.classList.remove("active");
    }
  }
  // No red screen flash for normal events.
  spawnGlitch(tx, ty, kind === "death", glowEnabled ? glowColor : "");
}

function setSciFiMode(data) {
  scifiEnabled = !(data && data.enabled === false);
  try {
    window.localStorage.setItem("tauri_scifi_enabled", scifiEnabled ? "1" : "0");
  } catch {}
  document.body.classList.toggle("scifi-off", !scifiEnabled);
  if (scifiEnabled) {
    setTelemetry("AURAXIS LINK ONLINE");
  }
}

function dispatchNativeEvent(evt) {
  const category = String((evt && evt.category) || "").toLowerCase();
  const data = evt && evt.data && typeof evt.data === "object" ? { ...evt.data } : {};
  data.__message = evt || null;
  const stateWhileHidden = new Set([
    "overlay_visibility",
    "scifi_mode",
    "layout_edit_mode",
    "feed_config",
    "twitch_config",
    "twitch_visibility",
    "stats",
    "stats_clear",
    "crosshair",
    "streak",
  ]);
  if (!overlayVisible && !stateWhileHidden.has(category)) return;

  if (category === "feed_config") applyFeedConfig(data);
  else if (category === "feed") appendFeed(data);
  else if (category === "feed_clear" && feedLayerEl) feedLayerEl.innerHTML = "";
  else if (category === "twitch_config") applyTwitchConfig(data);
  else if (category === "twitch_visibility") setTwitchVisibility(data);
  else if (category === "twitch_message") appendTwitchMessage(data);
  else if (category === "stats") updateStats(data);
  else if (category === "stats_clear" && statsLayerEl) statsLayerEl.innerHTML = "";
  else if (category === "crosshair") updateCrosshair(data);
  else if (category === "streak") renderStreak(data);
  else if (category === "event") pushTransientEvent(eventsLayerEl, data, "event");
  else if (category === "hitmarker") pushTransientEvent(hitmarkerLayerEl, data, "hitmarker");
  else if (category === "events_clear") clearEventsLayer();
  else if (category === "scifi_mode") setSciFiMode(data);
  else if (category === "overlay_visibility") {
    const target = String((data && data.target) || "").toLowerCase();
    // When legacy overlay is suppressed, ignore generic legacy visibility
    // broadcasts but still honor explicit tauri-targeted visibility.
    if (suppressLegacyOverlay && target !== "tauri") {
      return;
    }
    applyOverlayVisibility(!(data && data.visible === false));
  }
  else if (category === "layout_edit_mode") {
    applyLayoutEditMode(data);
  }
}

function updateLegacyToggleLabel() {
  if (!toggleLegacyOverlayBtn) return;
  toggleLegacyOverlayBtn.textContent = suppressLegacyOverlay
    ? "Legacy Overlay: OFF"
    : "Legacy Overlay: ON";
}

function overlayControlPortCandidates() {
  const wsPort = connectedWsPort();
  const wsPorts = new Set([wsPort, configuredWsPort].filter((p) => Number.isFinite(p) && p > 0));
  const out = [];
  const push = (p) => {
    if (!Number.isFinite(p) || p <= 0) return;
    if (wsPorts.has(p)) return;
    if (!out.includes(p)) out.push(p);
  };
  if (Number.isFinite(configuredHttpPort) && configuredHttpPort > 0) {
    for (let i = 0; i < 10; i += 1) push(configuredHttpPort + i);
  }
  for (let p = 31337; p <= 31346; p += 1) push(p);
  return out;
}

async function setLegacyOverlaySuppressed(enabled) {
  const mode = enabled ? "hide" : "auto";
  const ports = overlayControlPortCandidates();
  let ok = false;
  for (const p of ports) {
    const base = `http://127.0.0.1:${p}`;
    try {
      // eslint-disable-next-line no-await-in-loop
      const res = await fetch(`${base}/dev/overlay-visibility?mode=${mode}`, { cache: "no-store" });
      if (!res || !res.ok) continue;
      suppressLegacyOverlay = enabled;
      updateLegacyToggleLabel();
      appendLog(`[overlay] legacy mode ${enabled ? "OFF" : "ON"} via ${base}`, "ok");
      ok = true;
      break;
    } catch {
      // keep trying
    }
  }
  if (!ok) {
    appendLog(`[overlay] legacy toggle failed (no control endpoint found for mode=${mode})`, "bad");
  }
}

async function notifyItemMoved(item, x, y) {
  const name = String(item || "").trim().toLowerCase();
  if (!name) return false;
  const ports = overlayControlPortCandidates();
  for (const p of ports) {
    try {
      // eslint-disable-next-line no-await-in-loop
      const res = await fetch(
        `http://127.0.0.1:${p}/dev/item-moved?item=${encodeURIComponent(name)}&x=${encodeURIComponent(String(x))}&y=${encodeURIComponent(String(y))}`,
        { cache: "no-store" },
      );
      if (res && res.ok) return true;
    } catch {
      // keep trying
    }
  }
  return false;
}

async function notifyLayoutEditMode(enabled) {
  const ports = overlayControlPortCandidates();
  for (const p of ports) {
    try {
      // eslint-disable-next-line no-await-in-loop
      const res = await fetch(
        `http://127.0.0.1:${p}/dev/layout-edit-mode?enabled=${enabled ? "1" : "0"}`,
        { cache: "no-store" },
      );
      if (res && res.ok) return true;
    } catch {
      // keep trying
    }
  }
  return false;
}

function ensureSnapGuide(key, cls) {
  if (!layoutEditLayerEl) return null;
  let el = layoutEditLayerEl.querySelector(`.layout-snap-guide[data-guide="${key}"]`);
  if (!el) {
    el = document.createElement("div");
    el.className = `layout-snap-guide ${cls}`;
    el.dataset.guide = key;
    el.style.display = "none";
    layoutEditLayerEl.appendChild(el);
  }
  return el;
}

function updateSnapGuides(flags) {
  const f = flags || {};
  const gVCenter = ensureSnapGuide("center-v", "v");
  const gHCenter = ensureSnapGuide("center-h", "h");
  const gVLeft = ensureSnapGuide("edge-left", "v edge");
  const gVRight = ensureSnapGuide("edge-right", "v edge");
  const gHTop = ensureSnapGuide("edge-top", "h edge");
  const gHBottom = ensureSnapGuide("edge-bottom", "h edge");

  if (gVCenter) {
    gVCenter.style.display = f.centerX ? "block" : "none";
    gVCenter.style.left = `${Math.round(window.innerWidth / 2)}px`;
  }
  if (gHCenter) {
    gHCenter.style.display = f.centerY ? "block" : "none";
    gHCenter.style.top = `${Math.round(window.innerHeight / 2)}px`;
  }
  if (gVLeft) {
    gVLeft.style.display = f.left ? "block" : "none";
    gVLeft.style.left = "0px";
  }
  if (gVRight) {
    gVRight.style.display = f.right ? "block" : "none";
    gVRight.style.left = `${Math.max(0, Math.round(window.innerWidth - 1))}px`;
  }
  if (gHTop) {
    gHTop.style.display = f.top ? "block" : "none";
    gHTop.style.top = "0px";
  }
  if (gHBottom) {
    gHBottom.style.display = f.bottom ? "block" : "none";
    gHBottom.style.top = `${Math.max(0, Math.round(window.innerHeight - 1))}px`;
  }
}

function clearLayoutEditMarkers() {
  if (!layoutEditLayerEl) return;
  const handles = layoutEditLayerEl.querySelectorAll(".layout-handle");
  handles.forEach((h) => h.remove());
  updateSnapGuides({});
}

function getMoveTargetElement(target) {
  const t = String(target || "").toLowerCase();
  if (t === "feed") return feedLayerEl;
  if (t === "twitch") return twitchLayerEl;
  if (t === "stats") return statsLayerEl ? (statsLayerEl.querySelector(".layout-preview.overlay-stats-card") || statsLayerEl.firstElementChild) : null;
  if (t === "streak") return streakLayerEl ? (streakLayerEl.querySelector(".overlay-streak.layout-preview") || streakLayerEl.querySelector(".overlay-streak")) : null;
  if (t === "crosshair") return crosshairLayerEl ? crosshairLayerEl.querySelector("img.overlay-transient") : null;
  if (t === "event") {
    const preview = eventsLayerEl && eventsLayerEl.querySelector(".layout-preview.event-item");
    if (preview) return preview;
    return (eventsLayerEl && eventsLayerEl.lastElementChild) || (hitmarkerLayerEl && hitmarkerLayerEl.lastElementChild);
  }
  return null;
}

function clearLayoutPreviews() {
  if (eventsLayerEl) {
    const ev = eventsLayerEl.querySelectorAll(".layout-preview");
    ev.forEach((n) => n.remove());
  }
  if (streakLayerEl) {
    const st = streakLayerEl.querySelectorAll(".layout-preview");
    st.forEach((n) => n.remove());
  }
  layoutPreview.event = false;
  layoutPreview.streak = false;
  if (statsLayerEl) {
    const st = statsLayerEl.querySelectorAll(".layout-preview");
    st.forEach((n) => n.remove());
  }
  layoutPreview.stats = false;
}

function ensureLayoutEventPreview(previewData) {
  if (!eventsLayerEl) return;
  const existing = eventsLayerEl.querySelector(".layout-preview.event-item");
  if (existing) return;
  const data = previewData && typeof previewData === "object" ? previewData : {};
  const filename = String(data.filename || "").trim();
  if (!filename) return;
  const img = document.createElement("img");
  img.className = "overlay-transient event-item event-generic layout-preview";
  img.src = assetUrl(filename);
  img.style.width = `${Number(data.width || 220)}px`;
  img.style.height = `${Number(data.height || 220)}px`;
  const payload = {
    x: Number(data.x || 200),
    y: Number(data.y || 200),
    scale: Number(data.scale || 1),
  };
  setPos(img, payload, false);
  eventsLayerEl.appendChild(img);
  layoutPreview.event = true;
}

function ensureLayoutStreakPreview(previewData) {
  if (!streakLayerEl) return;
  if (lastStreakPayload && lastStreakPayload.visible) return;
  const existing = streakLayerEl.querySelector(".layout-preview.overlay-streak");
  if (existing) return;
  const data = previewData && typeof previewData === "object" ? previewData : {};
  const bg = String(data.bg_filename || "").trim();
  if (!bg) return;
  const wrap = document.createElement("div");
  wrap.className = "overlay-streak layout-preview";
  wrap.style.left = `${Number(data.x || 300)}px`;
  wrap.style.top = `${Number(data.y || 300)}px`;
  wrap.style.transform = "none";
  const bgImg = document.createElement("img");
  bgImg.className = "overlay-streak-bg";
  bgImg.src = assetUrl(bg);
  bgImg.style.width = `${Number(data.bg_width || 220)}px`;
  bgImg.style.height = `${Number(data.bg_height || 220)}px`;
  wrap.appendChild(bgImg);
  const count = document.createElement("div");
  count.className = "overlay-streak-count";
  count.textContent = String(data.count || 10);
  count.style.fontSize = `${Number(data.font_size || 26)}px`;
  count.style.color = String(data.color || "#fff");
  count.style.transform = `translate(-50%, -50%) translate(${Number(data.tx || 0)}px, ${Number(data.ty || 0)}px)`;
  wrap.appendChild(count);
  streakLayerEl.appendChild(wrap);
  layoutPreview.streak = true;
}

function ensureLayoutStatsPreview(previewData) {
  if (!statsLayerEl) return;
  if (statsLayerEl.firstElementChild && !statsLayerEl.firstElementChild.classList.contains("layout-preview")) return;
  const existing = statsLayerEl.querySelector(".layout-preview.overlay-stats-card");
  if (existing) return;
  const data = previewData && typeof previewData === "object" ? previewData : {};
  if (!data || !data.html) return;
  const card = document.createElement("div");
  card.className = "overlay-stats-card layout-preview";
  card.innerHTML = String(data.html || "");
  lastStatsPayload = { ...data };
  const payload = {
    x: Number(data.x || 50) + Number((data.box_width || 450) / 2) + Number(data.tx || 0),
    y: Number(data.y || 500) + Number((data.box_height || 60) / 2) + Number(data.ty || 0),
    scale: 1,
  };
  setPos(card, payload, true, false);
  statsLayerEl.appendChild(card);
  layoutPreview.stats = true;
}

function appendLayoutHandle(target, rect) {
  if (!layoutEditLayerEl || !rect) return;
  const h = document.createElement("div");
  h.className = "layout-handle";
  h.dataset.moveTarget = String(target);
  h.style.left = `${Math.round(rect.left)}px`;
  h.style.top = `${Math.round(rect.top)}px`;
  h.style.width = `${Math.max(14, Math.round(rect.width))}px`;
  h.style.height = `${Math.max(14, Math.round(rect.height))}px`;
  const lbl = document.createElement("div");
  lbl.className = "layout-handle-label";
  lbl.textContent = String(target).toUpperCase();
  h.appendChild(lbl);
  layoutEditLayerEl.appendChild(h);
}

function updateLayoutEditTargets() {
  if (activeDrag) return;
  clearLayoutEditMarkers();
  if (!layoutEditMode || !layoutEditLayerEl) return;
  const targets = new Set((Array.isArray(layoutEditTargets) ? layoutEditTargets : []).map((v) => String(v).toLowerCase()));
  targets.forEach((target) => {
    const el = getMoveTargetElement(target);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    appendLayoutHandle(target, rect);
  });
}

function startLayoutDrag(ev, targetEl, moveTarget) {
  if (!layoutEditMode || !targetEl) return;
  const rect = targetEl.getBoundingClientRect();
  const left = Number.isFinite(parseFloat(targetEl.style.left)) ? parseFloat(targetEl.style.left) : rect.left;
  const top = Number.isFinite(parseFloat(targetEl.style.top)) ? parseFloat(targetEl.style.top) : rect.top;
  activeDrag = {
    item: String(moveTarget || ""),
    el: targetEl,
    startMouseX: Number(ev.clientX || 0),
    startMouseY: Number(ev.clientY || 0),
    startLeft: left,
    startTop: top,
    width: rect.width,
    height: rect.height,
  };
  try {
    targetEl.setPointerCapture(ev.pointerId);
  } catch {}
  ev.preventDefault();
  ev.stopPropagation();
}

function updateLayoutDrag(ev) {
  if (!activeDrag) return;
  const dx = Number(ev.clientX || 0) - activeDrag.startMouseX;
  const dy = Number(ev.clientY || 0) - activeDrag.startMouseY;
  let x = Math.round(activeDrag.startLeft + dx);
  let y = Math.round(activeDrag.startTop + dy);
  const centerX = x + (activeDrag.width / 2);
  const centerY = y + (activeDrag.height / 2);
  const midX = window.innerWidth / 2;
  const midY = window.innerHeight / 2;
  const snapCenterX = Math.abs(centerX - midX) <= LAYOUT_SNAP_THRESHOLD;
  const snapCenterY = Math.abs(centerY - midY) <= LAYOUT_SNAP_THRESHOLD;
  const snapLeft = Math.abs(x - 0) <= LAYOUT_SNAP_THRESHOLD;
  const snapRight = Math.abs((x + activeDrag.width) - window.innerWidth) <= LAYOUT_SNAP_THRESHOLD;
  const snapTop = Math.abs(y - 0) <= LAYOUT_SNAP_THRESHOLD;
  const snapBottom = Math.abs((y + activeDrag.height) - window.innerHeight) <= LAYOUT_SNAP_THRESHOLD;

  if (snapCenterX) x = Math.round(midX - (activeDrag.width / 2));
  else if (snapLeft) x = 0;
  else if (snapRight) x = Math.round(window.innerWidth - activeDrag.width);

  if (snapCenterY) y = Math.round(midY - (activeDrag.height / 2));
  else if (snapTop) y = 0;
  else if (snapBottom) y = Math.round(window.innerHeight - activeDrag.height);

  updateSnapGuides({
    centerX: snapCenterX,
    centerY: snapCenterY,
    left: !snapCenterX && snapLeft,
    right: !snapCenterX && snapRight,
    top: !snapCenterY && snapTop,
    bottom: !snapCenterY && snapBottom,
  });
  activeDrag.el.style.left = `${x}px`;
  activeDrag.el.style.top = `${y}px`;
  const item = String(activeDrag.item || "").toLowerCase();
  const targetEl = getMoveTargetElement(item);
  if (targetEl) {
    if (item === "stats" || item === "crosshair") {
      const cx = Math.round(x + (activeDrag.width / 2));
      const cy = Math.round(y + (activeDrag.height / 2));
      targetEl.style.left = `${cx}px`;
      targetEl.style.top = `${cy}px`;
      targetEl.style.transform = "translate(-50%, -50%)";
      targetEl.style.transformOrigin = "center center";
    } else {
      targetEl.style.left = `${x}px`;
      targetEl.style.top = `${y}px`;
      // Keep existing scale transform for events and default style for others.
    }
  }
}

async function endLayoutDrag(ev) {
  if (!activeDrag) return;
  const d = activeDrag;
  activeDrag = null;
  updateSnapGuides({});
  try {
    d.el.releasePointerCapture(ev.pointerId);
  } catch {}
  const left = Number.isFinite(parseFloat(d.el.style.left)) ? parseFloat(d.el.style.left) : d.startLeft;
  const top = Number.isFinite(parseFloat(d.el.style.top)) ? parseFloat(d.el.style.top) : d.startTop;
  let sx = Math.round(left);
  let sy = Math.round(top);
  if (d.item === "crosshair") {
    sx = Math.round(left + (d.width / 2));
    sy = Math.round(top + (d.height / 2));
  } else if (d.item === "stats" && lastStatsPayload) {
    const centerX = left + (d.width / 2);
    const centerY = top + (d.height / 2);
    const bw = Number(lastStatsPayload.box_width || 450);
    const bh = Number(lastStatsPayload.box_height || 60);
    const tx = Number(lastStatsPayload.tx || 0);
    const ty = Number(lastStatsPayload.ty || 0);
    sx = Math.round(centerX - (bw / 2) - tx);
    sy = Math.round(centerY - (bh / 2) - ty);
  }
  const ok = await notifyItemMoved(d.item, sx, sy);
  if (!ok) appendLog(`[layout] failed to persist ${d.item} (${sx},${sy})`, "bad");
  updateLayoutEditTargets();
}

async function applyLayoutEditMode(data) {
  const enabled = !!(data && data.enabled);
  const targets = Array.isArray(data && data.targets) ? data.targets : [];
  const preview = (data && data.preview && typeof data.preview === "object") ? data.preview : {};
  layoutEditMode = enabled;
  layoutEditTargets = targets.map((v) => String(v).toLowerCase());
  document.body.classList.toggle("layout-edit-mode", layoutEditMode);
  if (layoutEditMode) {
    await setClickthrough(false);
    if (layoutEditTargets.includes("stats")) {
      ensureLayoutStatsPreview(preview.stats);
    }
    if (layoutEditTargets.includes("event")) {
      ensureLayoutEventPreview(preview.event);
    }
    if (layoutEditTargets.includes("streak")) {
      ensureLayoutStreakPreview(preview.streak);
    }
  } else if (overlayMode) {
    await setClickthrough(true);
    lastLayoutExitMs = Date.now();
    clearLayoutPreviews();
  }
  updateLayoutEditTargets();
  appendLog(`[layout] edit mode ${layoutEditMode ? "ON" : "OFF"} ${layoutEditTargets.join(",")}`, layoutEditMode ? "ok" : "");
}

function eventTypeOf(evt, data) {
  if (data && typeof data.event_type === "string" && data.event_type.trim()) return data.event_type;
  if (evt && typeof evt.category === "string" && evt.category.trim()) return evt.category;
  return "event";
}

function renderEventCard(evt, stageEl) {
  if (!stageEl) return;
  const data = evt && evt.data && typeof evt.data === "object" ? evt.data : {};
  const lane =
    (evt &&
      evt.meta &&
      evt.meta.v2 &&
      typeof evt.meta.v2.category === "string" &&
      evt.meta.v2.category) ||
    "normal";
  const evType = eventTypeOf(evt, data);
  const card = document.createElement("div");
  card.className = `event-card ${lane}`;

  const main = document.createElement("div");
  main.className = "event-main";
  main.textContent = `${evType}`;

  const sub = document.createElement("div");
  sub.className = "event-sub";
  const bits = [];
  if (typeof data.player_name === "string" && data.player_name) bits.push(data.player_name);
  if (typeof data.victim_name === "string" && data.victim_name) bits.push(`-> ${data.victim_name}`);
  if (typeof data.weapon_name === "string" && data.weapon_name) bits.push(data.weapon_name);
  if (bits.length === 0 && typeof data.filename === "string" && data.filename) bits.push(data.filename);
  if (bits.length === 0) bits.push(lane);
  sub.textContent = bits.join(" | ");

  const right = document.createElement("div");
  right.className = "event-sub";
  right.textContent = new Date().toLocaleTimeString();

  const left = document.createElement("div");
  left.className = "event-left";
  const textWrap = document.createElement("div");
  textWrap.className = "event-text";
  textWrap.appendChild(main);
  textWrap.appendChild(sub);
  left.appendChild(textWrap);
  card.appendChild(left);
  card.appendChild(right);
  stageEl.prepend(card);

  while (stageEl.childElementCount > 20) {
    stageEl.removeChild(stageEl.lastElementChild);
  }

  const assetName = pickAssetFilename(data);
  if (assetName && !observedAssets.has(assetName)) {
    observedAssets.add(assetName);
    observedAssetOrder.push(assetName);
  }
  if (assetName) {
    const cached = assetImageCache.get(assetName);
    if (cached) {
      assetCacheHits += 1;
      updateAssetCacheStatsUi();
      left.insertBefore(cached.cloneNode(false), left.firstChild);
    } else {
      assetCacheMisses += 1;
      updateAssetCacheStatsUi();
      preloadAsset(assetName).then((ok) => {
        if (!ok || !card.isConnected) return;
        const pre = assetImageCache.get(assetName);
        if (pre) left.insertBefore(pre.cloneNode(false), left.firstChild);
      });
    }
  }
}

function wsCandidates() {
  const ports = [];
  const pushPort = (p) => {
    if (!Number.isFinite(p) || p <= 0) return;
    if (!ports.includes(p)) ports.push(p);
  };
  pushPort(configuredWsPort);
  pushPort(31338);
  pushPort(31339);
  const urls = [];
  for (const p of ports) {
    urls.push(`ws://127.0.0.1:${p}/better_planetside`);
  }
  return urls;
}

function connectWs() {
  const candidates = wsCandidates();
  const url = candidates[wsAttemptIndex % candidates.length];
  wsAttemptIndex += 1;
  if (wsCurrent) {
    try { wsCurrent.close(); } catch {}
  }
  const ws = new WebSocket(url);
  wsCurrent = ws;
  setWsState(`connecting ${url}`, false);

  ws.onopen = () => {
    wsConnectedUrl = url;
    wsConnectedAtMs = Date.now();
    setWsState(`connected ${url}`, true);
    appendLog(`[ws] connected ${url}`, "ok");
  };

  ws.onclose = () => {
    if (wsConnectedUrl === url) wsConnectedUrl = "";
    setWsState(`disconnected ${url}`, false);
    appendLog(`[ws] disconnected ${url}`, "bad");
    setTimeout(connectWs, 1000);
  };

  ws.onerror = () => {
    setWsState("error", false);
  };

  ws.onmessage = (msg) => {
    try {
      const payload = JSON.parse(msg.data);
      if (payload && payload.kind === "batch" && Array.isArray(payload.events)) {
        for (const e of payload.events) {
          handleEvent(e);
        }
      } else {
        handleEvent(payload);
      }
    } catch {
      appendLog("[ws] non-json payload");
    }
  };
}

function handleEvent(evt) {
  const now = Date.now();
  eventCount += 1;
  eventCountEl.textContent = String(eventCount);
  const cat = evt && evt.category ? evt.category : "unknown";
  lastCategoryEl.textContent = cat;
  renderEventCard(evt, eventStageEl);
  dispatchNativeEvent(evt);

  const data = evt && evt.data && typeof evt.data === "object" ? evt.data : {};
  const tsSource = Number(data.ts_source_ms || 0);
  const tsRx = Number(data.ts_server_rx_ms || 0);
  if (tsSource > 0) {
    const d = Math.max(0, now - tsSource);
    pushSample(srcSamples, d);
    latSrcLastEl.textContent = formatMs(d);
  }
  if (tsRx > 0) {
    const d = Math.max(0, now - tsRx);
    pushSample(rxSamples, d);
    latRxLastEl.textContent = formatMs(d);
  }
  updateLatencyUi();

  if ((eventCount % 20) === 0) {
    appendLog(`[event] #${eventCount} category=${cat}`);
  }
}

async function setClickthrough(enabled) {
  const invoke = invokeBridge();
  if (!invoke) {
    appendLog("[tauri] invoke not available", "bad");
    return;
  }
  try {
    await invoke("set_clickthrough", { enabled });
    clickThrough = enabled;
    appendLog(`[tauri] click-through ${enabled ? "ON" : "OFF"}`);
  } catch (err) {
    appendLog(`[tauri] invoke failed: ${String(err)}`, "bad");
  }
}

async function setOverlayMode(enabled) {
  const invoke = invokeBridge();
  if (!invoke) {
    appendLog("[tauri] invoke not available", "bad");
    return;
  }
  try {
    if (enabled) {
      await invoke("set_overlay_mode", { enabled: true });
      await invoke("set_clickthrough", { enabled: true });
      clickThrough = true;
      overlayMode = true;
      document.body.classList.add("overlay-mode");
      appendLog("[overlay] native mode ON (click-through ON, exit with Esc)", "ok");
    } else {
      await invoke("set_overlay_mode", { enabled: false });
      await invoke("set_clickthrough", { enabled: false });
      clickThrough = false;
      overlayMode = false;
      document.body.classList.remove("overlay-mode");
      appendLog("[overlay] native mode OFF (click-through OFF)", "ok");
    }
  } catch (err) {
    appendLog(`[overlay] mode failed: ${String(err)}`, "bad");
  }
}

async function saveLatencySnapshot() {
  const invoke = invokeBridge();
  if (!invoke) {
    appendLog("[tauri] invoke not available", "bad");
    return;
  }
  try {
    const payload = {
      ws_endpoint: wsConnectedUrl || wsState.textContent || "",
      event_count: eventCount,
      source_latency: latencySummary(srcSamples),
      server_rx_latency: latencySummary(rxSamples),
      captured_at_ms: Date.now(),
    };
    const savedPath = await invoke("save_latency_snapshot", { snapshot: payload });
    lastSnapshotPath = String(savedPath || "");
    lastSnapshotPathEl.textContent = lastSnapshotPath || "-";
    lastSnapshotPathEl.title = lastSnapshotPath || "";
    appendLog(`[snapshot] saved ${savedPath}`, "ok");
  } catch (err) {
    appendLog(`[snapshot] failed: ${String(err)}`, "bad");
  }
}

if (toggleBtn) {
  toggleBtn.addEventListener("click", async () => {
    await setClickthrough(!clickThrough);
  });
}
if (toggleOverlayModeBtn) {
  toggleOverlayModeBtn.addEventListener("click", async () => {
    await setOverlayMode(!overlayMode);
  });
}
if (toggleLegacyOverlayBtn) {
  toggleLegacyOverlayBtn.addEventListener("click", async () => {
    await setLegacyOverlaySuppressed(!suppressLegacyOverlay);
  });
}
if (saveSnapshotBtn) {
  saveSnapshotBtn.addEventListener("click", async () => {
    await saveLatencySnapshot();
  });
}
if (preloadAssetsBtn) {
  preloadAssetsBtn.addEventListener("click", async () => {
    await preloadHotAssets();
  });
}
if (copySnapshotPathBtn) {
  copySnapshotPathBtn.addEventListener("click", async () => {
  if (!lastSnapshotPath) {
    appendLog("[snapshot] no saved path yet", "bad");
    return;
  }
  try {
    await navigator.clipboard.writeText(lastSnapshotPath);
    appendLog("[snapshot] path copied", "ok");
  } catch (err) {
    appendLog(`[snapshot] copy failed: ${String(err)}`, "bad");
  }
  });
}

window.addEventListener("pointerdown", (ev) => {
  if (!layoutEditMode) return;
  const targetEl = ev.target && ev.target.closest ? ev.target.closest("[data-move-target]") : null;
  if (!targetEl) return;
  const moveTarget = String(targetEl.dataset.moveTarget || "");
  if (!moveTarget) return;
  startLayoutDrag(ev, targetEl, moveTarget);
});

window.addEventListener("pointermove", (ev) => {
  updateLayoutDrag(ev);
});

window.addEventListener("pointerup", (ev) => {
  endLayoutDrag(ev).catch(() => {});
});

window.addEventListener("pointercancel", (ev) => {
  endLayoutDrag(ev).catch(() => {});
});

if (clearBtn) {
  clearBtn.addEventListener("click", () => {
  logEl.innerHTML = "";
  if (eventStageEl) eventStageEl.innerHTML = "";
  if (feedLayerEl) feedLayerEl.innerHTML = "";
  if (twitchLayerEl) twitchLayerEl.innerHTML = "";
  if (statsLayerEl) statsLayerEl.innerHTML = "";
  if (streakLayerEl) streakLayerEl.innerHTML = "";
  if (crosshairLayerEl) crosshairLayerEl.innerHTML = "";
  if (burstLayerEl) burstLayerEl.innerHTML = "";
  if (impactWaveEl) impactWaveEl.classList.remove("active");
  if (headshotFlashEl) headshotFlashEl.classList.remove("active");
  clearEventsLayer();
  srcSamples.length = 0;
  rxSamples.length = 0;
  wsConnectedUrl = "";
  latSrcLastEl.textContent = "-";
  latSrcP50P95El.textContent = "-";
  latRxLastEl.textContent = "-";
  latRxP50P95El.textContent = "-";
  lastSnapshotPath = "";
  lastSnapshotPathEl.textContent = "-";
  lastSnapshotPathEl.title = "";
  assetCacheHits = 0;
  assetCacheMisses = 0;
  assetImageCache.clear();
  observedAssets.clear();
  observedAssetOrder.length = 0;
  updateAssetCacheStatsUi();
  });
}

setClickthrough(false);
applyOverlayVisibility(false);
connectWs();
updateAssetCacheStatsUi();
updateLegacyToggleLabel();
loadConfiguredOverlayPorts();
updateClock();
setInterval(updateClock, 500);

async function startupOverlayMode() {
  // Native overlay mode should be the default for Tauri backend runs.
  if (!overlayMode) {
    await setOverlayMode(true);
  }
  if (!suppressLegacyOverlay) {
    await setLegacyOverlaySuppressed(true);
  }
}

setTimeout(() => {
  startupOverlayMode().catch(() => {});
}, 350);

window.addEventListener("keydown", async (ev) => {
  if (ev.key === "Escape" && layoutEditMode) {
    await notifyLayoutEditMode(false);
    await applyLayoutEditMode({ enabled: false, targets: [] });
    return;
  }
  if (ev.key === "Escape" && (Date.now() - lastLayoutExitMs) < 700) {
    return;
  }
  if (ev.key === "Escape" && overlayMode) {
    await setOverlayMode(false);
  }
});
