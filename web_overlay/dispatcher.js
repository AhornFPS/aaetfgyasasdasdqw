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
  let crosshairRing = null;

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

  function updateStats(data) {
    const textOffsetX = Number(data.tx || 0);
    const textOffsetY = Number(data.ty || 0);

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
    content.style.left = `${textOffsetX}px`;
    content.style.top = `${textOffsetY}px`;
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

    statsLayer.innerHTML = "";
    statsLayer.appendChild(card);
    setPos(card, data, false, false);

    activateSystem("stats");
    setTelemetry("COMBAT METRICS SYNCHRONIZED");
  }

  function clearFeed() {
    feedLayer.innerHTML = "";
  }

  function clearStats() {
    statsLayer.innerHTML = "";
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

  function appendFeed(data) {
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

  function updateCrosshair(data) {
    crosshairLayer.innerHTML = "";
    crosshairRing = null;
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

    const ring = document.createElement("div");
    ring.className = "crosshair-ring";
    setPos(ring, data, true, false);
    crosshairLayer.appendChild(ring);
    crosshairRing = ring;
    const initialLevel = Number(data.recoil_level);
    if (Number.isFinite(initialLevel)) {
      setCrosshairRecoil({ level: initialLevel });
    } else {
      setCrosshairRecoil({ active: Boolean(data.recoil_active) });
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

  function setCrosshairRecoil(data) {
    if (!crosshairRing) {
      return;
    }
    let level = Number.NaN;
    if (data && data.level !== undefined) {
      level = Number(data.level);
    }
    if (!Number.isFinite(level)) {
      level = Boolean(data && data.active) ? 1.0 : 0.0;
    }
    const clamped = Math.max(0, Math.min(1, level));
    crosshairRing.style.setProperty("--recoil-level", clamped.toFixed(4));
    const active = clamped > 0.001;
    crosshairRing.classList.toggle("recoil-active", active);
    crosshairRing.classList.toggle("recoil-tracking", active);
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

    const centered = Boolean(data.centered);
    setPos(img, data, centered);
    layer.appendChild(img);

    activateSystem(evType === "hitmarker" ? "hitmarker" : "event", warn);
    setTelemetry(`EVENT: ${evType.toUpperCase()}`, warn);

    const isHitmarker = evType.includes("hitmarker");
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
    setTimeout(() => {
      img.classList.add("fade-out");
      setTimeout(() => {
        if (img.parentNode) {
          img.remove();
        }
      }, 320);
    }, duration);
  }

  function clearEvents() {
    eventsLayer.innerHTML = "";
    hitmarkerLayer.innerHTML = "";
  }

  const handlers = {
    stats: updateStats,
    feed: appendFeed,
    feed_config: applyFeedContainer,
    feed_clear: clearFeed,
    stats_clear: clearStats,
    streak: renderStreak,
    crosshair: updateCrosshair,
    crosshair_recoil: setCrosshairRecoil,
    event: (data) => pushEvent(eventsLayer, data, "event"),
    hitmarker: (data) => pushEvent(hitmarkerLayer, data, data.event_type || "hitmarker"),
    events_clear: clearEvents,
    scifi_mode: setSciFiMode,
    overlay_visibility: setOverlayVisibility
  };

  updateClock();
  setInterval(updateClock, 500);

  new window.OverlaySocket((message) => {
    const type = message.category;
    const payload = message.data || {};
    const handler = handlers[type];
    if (handler) {
      handler(payload);
    }
  });
})();
