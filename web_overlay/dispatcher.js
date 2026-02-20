(function () {
  const feedLayer = document.getElementById("feed-layer");
  const statsLayer = document.getElementById("stats-layer");
  const streakLayer = document.getElementById("streak-layer");
  const eventsLayer = document.getElementById("events-layer");
  const hitmarkerLayer = document.getElementById("hitmarker-layer");
  const crosshairLayer = document.getElementById("crosshair-layer");
  const burstLayer = document.getElementById("burst-layer");
  const impactWave = document.getElementById("fx-impact-wave");
  const telemetryLeft = document.getElementById("telemetry-left");
  const telemetryRight = document.getElementById("telemetry-right");
  const perfHud = document.getElementById("perf-hud");

  const systemPips = {};
  document.querySelectorAll(".sys-pip").forEach((el) => {
    systemPips[String(el.dataset.system || "").toLowerCase()] = el;
  });

  const startupTime = performance.now();
  const startupQuietMs = 1300;
  let feedConfig = { x: 0, y: 0, width: 600, height: 550 };
  let telemetryWarnTimer = null;
  let scifiEnabled = true;
  let overlayVisible = true;
  let statsCard = null;
  let lastStatsSignature = "";
  const pendingFeedPayloads = [];
  const activeTransientByKey = new Map();
  let perfDebug = Boolean(window.OVERLAY_CONFIG && window.OVERLAY_CONFIG.perfDebug);
  let jsSchedulerV2 = !window.OVERLAY_CONFIG || window.OVERLAY_CONFIG.jsSchedulerV2 !== false;
  const transientPerFrameBudget = Math.max(
    16,
    Number((window.OVERLAY_CONFIG && window.OVERLAY_CONFIG.transientPerFrameBudget) || 512)
  );
  const stateLikeCategories = new Set([
    "stats",
    "streak",
    "crosshair",
    "feed_config",
    "scifi_mode",
    "overlay_visibility",
    "perf_debug_mode",
    "perf_stats"
  ]);
  const frameStateByType = new Map();
  const transientQueue = [];
  let transientReadIdx = 0;
  const cosmeticQueue = [];
  let cosmeticReadIdx = 0;
  const cosmeticPerFrameBudget = Math.max(4, Math.floor(transientPerFrameBudget * 0.35));
  const maxCosmeticQueue = Math.max(32, Math.min(256, transientPerFrameBudget * 2));
  let frameRafId = 0;
  const perfState = {
    messageCount: 0,
    renderCount: 0,
    dispatchMsAvg: 0,
    dispatchMsLast: 0,
    e2eMsAvg: 0,
    e2eMsLast: 0,
    wsToJsMsAvg: 0,
    wsToJsMsLast: 0,
    lastCategory: "-",
    lastServerStats: null,
    lastHudUpdateMs: 0,
    queueDepth: 0
  };

  function applyPerfDebugMode(enabled) {
    perfDebug = Boolean(enabled);
    document.body.classList.toggle("perf-debug", perfDebug);
    if (!perfDebug && perfHud) {
      perfHud.textContent = "";
    }
  }

  applyPerfDebugMode(perfDebug);

  function isStartupReplay() {
    return performance.now() - startupTime < startupQuietMs;
  }

  function assetUrl(filename) {
    if (!filename) return "";
    if (filename.startsWith("http") || filename.startsWith("/")) return filename;
    return `/assets/${filename}`;
  }

  function setPos(el, data, centered, applyScale = true) {
    const x = Number(data.x || 0);
    const y = Number(data.y || 0);
    const scale = Number(data.scale || 1);
    if (centered) {
      el.style.left = `${x}px`;
      el.style.top = `${y}px`;
      el.style.transform = applyScale
        ? `translate(-50%, -50%) scale(${scale})`
        : "translate(-50%, -50%)";
      return;
    }
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.transform = applyScale ? `scale(${scale})` : "none";
  }

  function updateClock() {
    if (!telemetryRight) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    telemetryRight.textContent = `${hh}:${mm}:${ss}`;
  }

  function setTelemetry(text, isWarn = false) {
    if (!scifiEnabled) {
      return;
    }
    if (telemetryLeft && text) {
      telemetryLeft.textContent = text;
    }
    if (isWarn) {
      document.body.classList.add("hud-warn");
      if (telemetryWarnTimer) {
        clearTimeout(telemetryWarnTimer);
      }
      telemetryWarnTimer = setTimeout(() => {
        document.body.classList.remove("hud-warn");
      }, 380);
    }
  }

  function activateSystem(name, warn = false) {
    if (!scifiEnabled) return;
    const key = String(name || "").toLowerCase();
    const pip = systemPips[key];
    if (!pip || isStartupReplay()) return;
    pip.classList.remove("active", "warn");
    // Restart animation.
    void pip.offsetWidth;
    pip.classList.add("active");
    if (warn) pip.classList.add("warn");
    setTimeout(() => {
      pip.classList.remove("active", "warn");
    }, 320);
  }

  function spawnBurst(x, y, warn = false) {
    if (!scifiEnabled) return;
    if (!burstLayer || isStartupReplay()) return;
    const burst = document.createElement("div");
    burst.className = warn ? "fx-burst warn" : "fx-burst";
    burst.style.left = `${Number(x)}px`;
    burst.style.top = `${Number(y)}px`;
    burstLayer.appendChild(burst);
    setTimeout(() => {
      if (burst.parentNode) burst.remove();
    }, 540);
  }

  function spawnGlitch(x, y, warn = false) {
    if (!burstLayer || isStartupReplay()) return;
    const glitch = document.createElement("div");
    glitch.className = warn ? "fx-glitch warn" : "fx-glitch";
    glitch.style.left = `${Number(x)}px`;
    glitch.style.top = `${Number(y)}px`;
    glitch.style.setProperty("--glitch-rot", `${Math.round((Math.random() * 14) - 7)}deg`);
    burstLayer.appendChild(glitch);
    setTimeout(() => {
      if (glitch.parentNode) glitch.remove();
    }, 320);
  }

  function triggerImpact(type, x, y) {
    document.body.classList.remove("hud-impact");
    void document.body.offsetWidth;
    document.body.classList.add("hud-impact");
    setTimeout(() => document.body.classList.remove("hud-impact"), 450);

    if (impactWave) {
      impactWave.classList.remove("active");
      void impactWave.offsetWidth;
      impactWave.classList.add("active");
      setTimeout(() => impactWave.classList.remove("active"), 400);
    }

    const warn = type === "death";
    spawnGlitch(
      Number.isFinite(Number(x)) ? Number(x) : window.innerWidth / 2,
      Number.isFinite(Number(y)) ? Number(y) : window.innerHeight / 2,
      warn
    );
  }

  function setSciFiMode(data) {
    scifiEnabled = !(data && data.enabled === false);
    document.body.classList.toggle("scifi-off", !scifiEnabled);
    if (!scifiEnabled) {
      document.body.classList.remove("hud-impact", "hud-warn");
      if (burstLayer) burstLayer.innerHTML = "";
      if (impactWave) impactWave.classList.remove("active");
    } else {
      setTelemetry("AURAXIS LINK ONLINE");
    }
  }

  function setOverlayVisibility(data) {
    overlayVisible = !(data && data.visible === false);
    document.body.classList.toggle("overlay-hidden", !overlayVisible);
    if (!overlayVisible) {
      document.body.classList.remove("hud-impact", "hud-warn");
      if (burstLayer) burstLayer.innerHTML = "";
      if (impactWave) impactWave.classList.remove("active");
    }
  }

  function shouldTriggerImpact(data, evType) {
    if (typeof data.impact === "boolean") {
      return data.impact;
    }
    return evType === "headshot" || evType === "death";
  }

  function buildStatsSignature(data) {
    return JSON.stringify({
      html: String(data.html || ""),
      tx: Number(data.tx || 0),
      ty: Number(data.ty || 0),
      glow: data.glow !== false,
      glowColor: String(data.glow_color || "")
    });
  }

  function positionStatsCard(card, data) {
    const x = Number(data.x || 0);
    const y = Number(data.y || 0);
    const tx = Number(data.tx || 0);
    const ty = Number(data.ty || 0);
    const boxWidth = Number(data.box_width || 450);
    const boxHeight = Number(data.box_height || 60);
    setPos(
      card,
      {
        x: x + (boxWidth / 2) + tx,
        y: y + (boxHeight / 2) + ty
      },
      true,
      false
    );
  }

  function updateStats(data) {
    const signature = buildStatsSignature(data);
    if (statsCard && signature === lastStatsSignature) {
      positionStatsCard(statsCard, data);
      return;
    }

    const card = document.createElement("div");
    card.className = "stats-card";
    card.style.position = "absolute";
    card.style.width = "auto";
    card.style.height = "auto";
    card.style.overflow = "visible";
    card.style.display = "inline-block";
    card.style.minWidth = "0";
    card.style.padding = "0";
    card.style.border = "none";
    card.style.background = "transparent";
    card.style.boxShadow = "none";

    const glowActive = data.glow !== false;

    const content = document.createElement("div");
    content.className = "stats-content";
    content.style.position = "relative";
    content.style.whiteSpace = "nowrap";
    if (!glowActive) {
      content.style.textShadow = "1px 1px 2px rgba(0,0,0,0.9)";
    } else if (data.glow_color) {
      content.style.textShadow =
        `1px 1px 2px rgba(0,0,0,0.9), 0 0 10px ${data.glow_color}, 0 0 24px ${data.glow_color}`;
    } else {
      content.style.textShadow = "1px 1px 2px rgba(0,0,0,0.9)";
    }
    content.innerHTML = data.html || "";
    card.appendChild(content);

    statsLayer.replaceChildren(card);
    statsCard = card;
    lastStatsSignature = signature;
    positionStatsCard(card, data);

    activateSystem("stats");
    setTelemetry("COMBAT METRICS SYNCHRONIZED");
  }

  function clearFeed() {
    pendingFeedPayloads.length = 0;
    feedLayer.innerHTML = "";
  }

  function clearStats() {
    statsLayer.innerHTML = "";
    statsCard = null;
    lastStatsSignature = "";
  }

  function applyFeedContainer(data) {
    feedConfig = {
      x: Number(data.x || 0),
      y: Number(data.y || 0),
      width: Number(data.width || 600),
      height: Number(data.height || 550)
    };
    feedLayer.style.left = `${feedConfig.x}px`;
    feedLayer.style.top = `${feedConfig.y}px`;
    feedLayer.style.width = `${feedConfig.width}px`;
    feedLayer.style.maxHeight = `${feedConfig.height}px`;
  }

  function classifyFeed(html) {
    const text = String(html || "").toLowerCase();
    if (text.includes("death")) return "death";
    if (text.includes("headshot")) return "headshot";
    if (text.includes("gunner")) return "gunner";
    if (text.includes("revive")) return "revive";
    if (text.includes("kill")) return "kill";
    return "feed";
  }

  function appendFeedItem(data) {
    applyFeedContainer(data);
    const item = document.createElement("div");
    item.className = "feed-item";
    item.innerHTML = data.html || "";

    const imgs = item.querySelectorAll("img");
    imgs.forEach((img) => {
      const src = img.getAttribute("src") || "";
      const parts = src.split(/[\\/]/);
      img.src = assetUrl(parts[parts.length - 1]);
    });

    feedLayer.prepend(item);

    const maxItems = Number(data.max_items || 6);
    while (feedLayer.children.length > maxItems) {
      feedLayer.lastElementChild.remove();
    }

    const feedType = classifyFeed(data.html);
    const warn = feedType === "death";
    activateSystem("feed", warn);
    setTelemetry(
      warn ? "COMBAT ALERT: DEATH REGISTERED" : `KILLFEED UPDATE: ${feedType.toUpperCase()}`,
      warn
    );

    if (!isStartupReplay()) {
      spawnGlitch(feedConfig.x + feedConfig.width - 50, feedConfig.y + 28, warn);
    }

    const autoRemove = data.auto_remove !== false;
    if (autoRemove) {
      const duration = Number(data.hold_ms || 10000);
      setTimeout(() => {
        item.classList.add("fade-out");
        setTimeout(() => {
          if (item.parentNode) {
            item.remove();
          }
        }, 320);
      }, duration);
    }
  }

  function appendFeed(data) {
    pendingFeedPayloads.push(data || {});
  }

  function flushFeedBatch() {
    if (!pendingFeedPayloads.length) return;
    // Bound per-frame killfeed work to avoid long DOM bursts.
    const budget = 12;
    let processed = 0;
    while (pendingFeedPayloads.length && processed < budget) {
      const payload = pendingFeedPayloads.shift();
      appendFeedItem(payload);
      processed += 1;
    }
  }

  function updateCrosshair(data) {
    crosshairLayer.innerHTML = "";
    if (!data.enabled || !data.filename) {
      return;
    }

    if (data.shadow) {
      const core = document.createElement("div");
      core.className = "crosshair-core-shadow";
      const size = Number(data.size || 64);
      const coreSize = Math.max(5, Math.round(size * 0.26));
      core.style.width = `${coreSize}px`;
      core.style.height = `${coreSize}px`;
      setPos(core, data, true);
      crosshairLayer.appendChild(core);
    }

    const img = document.createElement("img");
    img.className = "crosshair";
    img.src = assetUrl(data.filename);
    img.style.width = `${Number(data.size || 64)}px`;
    img.style.height = `${Number(data.size || 64)}px`;
    img.style.filter = data.shadow
      ? "drop-shadow(0 0 1px rgba(0,0,0,0.95)) drop-shadow(0 0 3px rgba(0,0,0,0.78))"
      : "none";

    setPos(img, data, true);
    crosshairLayer.appendChild(img);

    activateSystem("crosshair");
  }

  function renderStreak(data) {
    streakLayer.innerHTML = "";
    if (!data.visible) {
      return;
    }

    const core = document.createElement("div");
    core.className = "streak-core";

    const knifeLayer = document.createElement("div");
    knifeLayer.className = "streak-knife-layer";
    if (data.anim_active !== false) {
      const speedVal = Number(data.anim_speed || 50);
      const duration = Math.max(0.6, Math.min(4.0, 120 / Math.max(1, speedVal)));
      knifeLayer.style.animation = `streakPulse ${duration.toFixed(2)}s ease-in-out infinite`;
    } else {
      knifeLayer.style.animation = "none";
    }

    const skull = document.createElement("img");
    skull.className = "streak-bg";
    skull.src = assetUrl(data.bg_filename);
    skull.style.width = `${Number(data.bg_width || 200)}px`;
    skull.style.height = `${Number(data.bg_height || 200)}px`;

    const count = document.createElement("div");
    count.className = "streak-count";
    count.style.fontSize = `${Number(data.font_size || 26)}px`;
    count.style.color = data.color || "#ffffff";
    count.style.fontWeight = data.bold ? "700" : "400";
    count.style.transform = `translate(-50%, -50%) translate(${Number(data.tx || 0)}px, ${Number(data.ty || 0)}px)`;
    count.textContent = String(data.count || 0);

    const streakGlow = data.streak_glow !== false;
    if (!streakGlow) {
      count.classList.add("no-glow");
    } else if (data.glow_color) {
      count.style.textShadow = `0 0 10px ${data.glow_color}, 0 0 24px ${data.glow_color}`;
    }

    const knives = Array.isArray(data.knives) ? data.knives : [];
    knives.forEach((knife) => {
      const img = document.createElement("img");
      img.className = "knife";
      img.src = assetUrl(knife.filename);
      img.style.width = `${Number(knife.size || 90)}px`;
      img.style.height = `${Number(knife.size || 90)}px`;
      if (!streakGlow) {
        img.classList.add("no-glow");
      } else if (data.glow_color) {
        img.style.filter = `drop-shadow(0 0 7px ${data.glow_color})`;
      }
      img.style.transform = `translate(-50%, -50%) translate(${Number(knife.x_off || 0)}px, ${Number(knife.y_off || 0)}px) rotate(${Number(knife.rotation || 0)}deg)`;
      knifeLayer.appendChild(img);
    });

    core.appendChild(knifeLayer);
    core.appendChild(skull);
    core.appendChild(count);
    setPos(core, data, false);
    streakLayer.appendChild(core);

    activateSystem("streak");
    setTelemetry(`KILLSTREAK LOCKED: x${Number(data.count || 0)}`);
  }

  function pushEvent(layer, data, fallbackType) {
    if (!data.filename) {
      return;
    }

    const message = data.__message || null;
    const img = document.createElement("img");
    img.className = "event-item";
    img.src = assetUrl(data.filename);
    img.style.width = `${Number(data.width || 220)}px`;
    img.style.height = `${Number(data.height || 220)}px`;

    const evType = String(data.event_type || fallbackType || "event").toLowerCase();
    const warn = evType === "death";
    if (evType === "death" || evType === "headshot") {
      img.classList.add("death-impact");
    } else if (data.glow !== false && data.glow_color) {
      img.style.filter = `drop-shadow(0 0 10px ${data.glow_color})`;
    }

    const isHitmarker = evType.includes("hitmarker");
    const centered = Boolean(data.centered);
    const coalesceKeyRaw = String(((((message || {}).meta || {}).v2 || {}).coalesce_key) || "").trim();
    const coalesceMapKey = !isHitmarker && coalesceKeyRaw
      ? `${String(fallbackType || "event").toLowerCase()}:${coalesceKeyRaw}`
      : "";

    let targetNode = img;
    const existingEntry = coalesceMapKey ? activeTransientByKey.get(coalesceMapKey) : null;
    if (existingEntry && existingEntry.el && existingEntry.el.isConnected) {
      targetNode = existingEntry.el;
      targetNode.src = img.src;
      targetNode.style.width = img.style.width;
      targetNode.style.height = img.style.height;
      targetNode.classList.toggle("death-impact", evType === "death" || evType === "headshot");
      if (evType !== "death" && evType !== "headshot") {
        if (data.glow !== false && data.glow_color) {
          targetNode.style.filter = `drop-shadow(0 0 10px ${data.glow_color})`;
        } else {
          targetNode.style.filter = "";
        }
      }
      setPos(targetNode, data, centered);
      targetNode.classList.remove("fade-out");
    } else {
      setPos(targetNode, data, centered);
      layer.appendChild(targetNode);
      if (coalesceMapKey) {
        activeTransientByKey.set(coalesceMapKey, { el: targetNode, timer: null });
      }
    }

    activateSystem(evType === "hitmarker" ? "hitmarker" : "event", warn);
    setTelemetry(`EVENT: ${evType.toUpperCase()}`, warn);

    if (isHitmarker && !isStartupReplay()) {
      spawnBurst(
        Number(data.x || 0) + Number(data.width || 220) / 2,
        Number(data.y || 0) + Number(data.height || 220) / 2,
        warn
      );
    }

    if (shouldTriggerImpact(data, evType)) {
      const cx = Number(data.x || 0) + Number(data.width || 220) / 2;
      const cy = Number(data.y || 0) + Number(data.height || 220) / 2;
      triggerImpact(evType, cx, cy);
    } else if (!isHitmarker && !isStartupReplay()) {
      spawnGlitch(
        Number(data.x || 0) + Number(data.width || 220) / 2,
        Number(data.y || 0) + Number(data.height || 220) / 2,
        warn
      );
    }

    const duration = Number(data.duration || 180);
    if (coalesceMapKey) {
      const entry = activeTransientByKey.get(coalesceMapKey);
      if (entry && entry.timer) {
        clearTimeout(entry.timer);
      }
      const timer = setTimeout(() => {
        targetNode.classList.add("fade-out");
        setTimeout(() => {
          if (targetNode.parentNode) {
            targetNode.remove();
          }
          const current = activeTransientByKey.get(coalesceMapKey);
          if (current && current.el === targetNode) {
            activeTransientByKey.delete(coalesceMapKey);
          }
        }, 320);
      }, duration);
      if (entry) {
        entry.timer = timer;
      } else {
        activeTransientByKey.set(coalesceMapKey, { el: targetNode, timer });
      }
    } else {
      setTimeout(() => {
        targetNode.classList.add("fade-out");
        setTimeout(() => {
          if (targetNode.parentNode) {
            targetNode.remove();
          }
        }, 320);
      }, duration);
    }
  }

  function clearEvents() {
    activeTransientByKey.forEach((entry) => {
      if (entry && entry.timer) {
        clearTimeout(entry.timer);
      }
    });
    activeTransientByKey.clear();
    eventsLayer.innerHTML = "";
    hitmarkerLayer.innerHTML = "";
  }

  function updatePerfAverages(sampleDispatchMs, sampleE2eMs, sampleWsToJsMs, category) {
    perfState.messageCount += 1;
    perfState.renderCount += 1;
    perfState.lastCategory = String(category || "-");
    perfState.dispatchMsLast = Number(sampleDispatchMs || 0);
    perfState.e2eMsLast = Number(sampleE2eMs || 0);
    perfState.wsToJsMsLast = Number(sampleWsToJsMs || 0);

    const n = perfState.messageCount;
    perfState.dispatchMsAvg += (perfState.dispatchMsLast - perfState.dispatchMsAvg) / n;
    perfState.e2eMsAvg += (perfState.e2eMsLast - perfState.e2eMsAvg) / n;
    perfState.wsToJsMsAvg += (perfState.wsToJsMsLast - perfState.wsToJsMsAvg) / n;
  }

  function renderPerfHud(nowMs) {
    if (!perfDebug || !perfHud) return;
    if (nowMs - perfState.lastHudUpdateMs < 250) return;
    perfState.lastHudUpdateMs = nowMs;

    const s = perfState.lastServerStats || {};
    perfHud.textContent =
      `PERF DEBUG\n` +
      `msg=${perfState.messageCount} cat=${perfState.lastCategory}\n` +
      `dispatch_ms last=${perfState.dispatchMsLast.toFixed(2)} avg=${perfState.dispatchMsAvg.toFixed(2)}\n` +
      `e2e_ms last=${perfState.e2eMsLast.toFixed(1)} avg=${perfState.e2eMsAvg.toFixed(1)}\n` +
      `ws_to_js_ms last=${perfState.wsToJsMsLast.toFixed(2)} avg=${perfState.wsToJsMsAvg.toFixed(2)}\n` +
      `server in=${Number(s.events_in_total || 0)} out=${Number(s.events_out_total || 0)}\n` +
      `lanes in[s/c/n/cos]=${Number(s.events_in_state || 0)}/${Number(s.events_in_critical || 0)}/${Number(s.events_in_normal || 0)}/${Number(s.events_in_cosmetic || 0)}\n` +
      `lanes out[s/c/n/cos]=${Number(s.events_out_state || 0)}/${Number(s.events_out_critical || 0)}/${Number(s.events_out_normal || 0)}/${Number(s.events_out_cosmetic || 0)}\n` +
      `server flush=${Number(s.flush_count || 0)} last_flush=${Number(s.last_flush_size || 0)}\n` +
      `server pend_state=${Number(s.max_pending_state || 0)} pend_trans=${Number(s.max_pending_transient || 0)}\n` +
      `server coalesced=${Number(s.coalesce_replaced || 0)} deduped=${Number(s.deduped_total || 0)}\n` +
      `server dropped=${Number(s.dropped_total || 0)} ovf_drop=${Number(s.dropped_transient_overflow || 0)} cos_drop=${Number(s.dropped_cosmetic_total || 0)}\n` +
      `cfg dedupe_ms=${Number(s.dedupe_window_ms || 0)} cap=${Number(s.max_transient_pending_cfg || 0)} cos_cap=${Number(s.max_cosmetic_pending_cfg || 0)}\n` +
      `ws batch=${Boolean(s.ws_batching_v2)} batch_flush=${Number(s.batch_flush_count || 0)} legacy_flush=${Number(s.legacy_flush_count || 0)} last_batch=${Number(s.last_batch_size || 0)}\n` +
      `ui queue=${Number(perfState.queueDepth || 0)} frame_budget=${transientPerFrameBudget} js_sched_v2=${Boolean(jsSchedulerV2)}`;
  }

  function getTransientQueueDepth() {
    return (transientQueue.length - transientReadIdx) + (cosmeticQueue.length - cosmeticReadIdx);
  }

  function compactTransientQueueIfNeeded() {
    if (transientReadIdx >= 512 && transientReadIdx * 2 >= transientQueue.length) {
      transientQueue.splice(0, transientReadIdx);
      transientReadIdx = 0;
    }
    if (cosmeticReadIdx >= 512 && cosmeticReadIdx * 2 >= cosmeticQueue.length) {
      cosmeticQueue.splice(0, cosmeticReadIdx);
      cosmeticReadIdx = 0;
    }
  }

  function dispatchSingleMessage(message) {
    const dispatchStart = performance.now();
    const type = message.category;
    const payload = message.data || {};
    // Provide message metadata to handlers without changing wire format.
    payload.__message = message;
    const handler = handlers[type];
    if (handler) {
      handler(payload);
    }
    if (!jsSchedulerV2) {
      flushFeedBatch();
    }
    const dispatchEnd = performance.now();
    const dispatchMs = dispatchEnd - dispatchStart;
    const sourceMs = Number(payload.ts_source_ms || 0);
    const nowEpochMs = Date.now();
    const e2eMs = sourceMs > 0 ? Math.max(0, nowEpochMs - sourceMs) : 0;
    const wsRx = Number(message.__perf_ws_rx_ms || 0);
    const wsToJsMs = wsRx > 0 ? Math.max(0, dispatchStart - wsRx) : 0;
    updatePerfAverages(dispatchMs, e2eMs, wsToJsMs, type);
  }

  function processFrameQueue() {
    frameRafId = 0;

    if (frameStateByType.size > 0) {
      const stateMessages = Array.from(frameStateByType.values());
      frameStateByType.clear();
      for (let i = 0; i < stateMessages.length; i += 1) {
        dispatchSingleMessage(stateMessages[i]);
      }
    }

    let processed = 0;
    while (transientReadIdx < transientQueue.length && processed < transientPerFrameBudget) {
      dispatchSingleMessage(transientQueue[transientReadIdx]);
      transientReadIdx += 1;
      processed += 1;
    }
    let cosmeticProcessed = 0;
    while (
      cosmeticReadIdx < cosmeticQueue.length &&
      processed < transientPerFrameBudget &&
      cosmeticProcessed < cosmeticPerFrameBudget
    ) {
      dispatchSingleMessage(cosmeticQueue[cosmeticReadIdx]);
      cosmeticReadIdx += 1;
      cosmeticProcessed += 1;
      processed += 1;
    }
    compactTransientQueueIfNeeded();
    flushFeedBatch();

    perfState.queueDepth = frameStateByType.size + getTransientQueueDepth();
    renderPerfHud(performance.now());

    if (
      frameStateByType.size > 0 ||
      transientReadIdx < transientQueue.length ||
      cosmeticReadIdx < cosmeticQueue.length
    ) {
      frameRafId = window.requestAnimationFrame(processFrameQueue);
    }
  }

  function scheduleFrameDispatch() {
    if (frameRafId) return;
    frameRafId = window.requestAnimationFrame(processFrameQueue);
  }

  function drainQueuedMessagesImmediate() {
    if (frameStateByType.size > 0) {
      const stateMessages = Array.from(frameStateByType.values());
      frameStateByType.clear();
      for (let i = 0; i < stateMessages.length; i += 1) {
        dispatchSingleMessage(stateMessages[i]);
      }
    }
    while (transientReadIdx < transientQueue.length) {
      dispatchSingleMessage(transientQueue[transientReadIdx]);
      transientReadIdx += 1;
    }
    while (cosmeticReadIdx < cosmeticQueue.length) {
      dispatchSingleMessage(cosmeticQueue[cosmeticReadIdx]);
      cosmeticReadIdx += 1;
    }
    compactTransientQueueIfNeeded();
    flushFeedBatch();
    perfState.queueDepth = frameStateByType.size + getTransientQueueDepth();
    renderPerfHud(performance.now());
  }

  function applyJsSchedulerMode(enabled) {
    jsSchedulerV2 = Boolean(enabled);
    if (!jsSchedulerV2) {
      if (frameRafId) {
        window.cancelAnimationFrame(frameRafId);
        frameRafId = 0;
      }
      drainQueuedMessagesImmediate();
      return;
    }
    if (
      frameStateByType.size > 0 ||
      transientReadIdx < transientQueue.length ||
      cosmeticReadIdx < cosmeticQueue.length
    ) {
      scheduleFrameDispatch();
    }
  }

  const handlers = {
    stats: updateStats,
    feed: appendFeed,
    feed_config: applyFeedContainer,
    feed_clear: clearFeed,
    stats_clear: clearStats,
    streak: renderStreak,
    crosshair: updateCrosshair,
    event: (data) => pushEvent(eventsLayer, data, "event"),
    hitmarker: (data) => pushEvent(hitmarkerLayer, data, data.event_type || "hitmarker"),
    events_clear: clearEvents,
    scifi_mode: setSciFiMode,
    overlay_visibility: setOverlayVisibility,
    perf_debug_mode: (data) => {
      applyPerfDebugMode(Boolean(data && data.enabled));
    },
    perf_js_scheduler_mode: (data) => {
      applyJsSchedulerMode(Boolean(data && data.enabled));
    },
    perf_stats: (data) => {
      perfState.lastServerStats = data || {};
    }
  };

  updateClock();
  setInterval(updateClock, 500);

  new window.OverlaySocket((message) => {
    if (!message || typeof message !== "object") {
      return;
    }
    if (!jsSchedulerV2) {
      dispatchSingleMessage(message);
      perfState.queueDepth = frameStateByType.size + getTransientQueueDepth();
      renderPerfHud(performance.now());
      return;
    }
    const category = String(message.category || "").toLowerCase();
    const lane = String((((message.meta || {}).v2 || {}).category) || "").toLowerCase();
    const isState = lane === "state" || stateLikeCategories.has(category);

    if (isState) {
      frameStateByType.set(category || "unknown", message);
    } else {
      if (lane === "cosmetic") {
        cosmeticQueue.push(message);
        if (cosmeticQueue.length - cosmeticReadIdx > maxCosmeticQueue) {
          cosmeticReadIdx += 1;
        }
      } else {
        transientQueue.push(message);
      }
    }
    perfState.queueDepth = frameStateByType.size + getTransientQueueDepth();
    scheduleFrameDispatch();
  });
})();
