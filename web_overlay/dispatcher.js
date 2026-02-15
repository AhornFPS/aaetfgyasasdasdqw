(function () {
  const feedLayer = document.getElementById("feed-layer");
  const statsLayer = document.getElementById("stats-layer");
  const streakLayer = document.getElementById("streak-layer");
  const eventsLayer = document.getElementById("events-layer");
  const hitmarkerLayer = document.getElementById("hitmarker-layer");
  const crosshairLayer = document.getElementById("crosshair-layer");

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

  function triggerImpact(type) {
    document.body.classList.remove("hud-impact");
    void document.body.offsetWidth;
    document.body.classList.add("hud-impact");
    setTimeout(() => document.body.classList.remove("hud-impact"), 450);
  }

  function shouldTriggerImpact(data, evType) {
    if (typeof data.impact === "boolean") {
      return data.impact;
    }
    return evType === "headshot" || evType === "death";
  }

  function updateStats(data) {
    const card = document.createElement("div");
    card.className = "stats-card";
    if (data.glow === false) {
      card.classList.add("no-glow");
    }
    card.style.position = "absolute";
    card.style.width = `${Number(data.box_width || 600)}px`;
    card.style.height = `${Number(data.box_height || 60)}px`;
    card.style.overflow = "visible";
    card.style.display = "flex";
    card.style.alignItems = "center";
    card.style.justifyContent = "center";

    let bg = "";
    if (data.bg_filename) {
      bg = `background-image: url('${assetUrl(data.bg_filename)}'); background-repeat:no-repeat; background-size:100% 100%;`;
    }

    const pad = Number(data.padding || 15);
    card.style.padding = `${pad}px`;
    if (bg) {
      card.style.backgroundImage = `url('${assetUrl(data.bg_filename)}')`;
      card.style.backgroundRepeat = "no-repeat";
      card.style.backgroundSize = "100% 100%";
    } else {
      card.style.backgroundImage = "none";
    }
    const content = document.createElement("div");
    content.className = "stats-content";
    if (data.glow === false) {
      content.classList.add("no-glow");
    }
    content.style.position = "relative";
    content.style.left = `${Number(data.tx || 0)}px`;
    content.style.top = `${Number(data.ty || 0)}px`;
    content.style.whiteSpace = "nowrap";
    content.innerHTML = data.html || "";
    card.appendChild(content);

    statsLayer.innerHTML = "";
    statsLayer.appendChild(card);
    setPos(card, data, false, false);
  }

  function clearFeed() {
    feedLayer.innerHTML = "";
  }

  function clearStats() {
    statsLayer.innerHTML = "";
  }

  function applyFeedContainer(data) {
    feedLayer.style.left = `${Number(data.x || 0)}px`;
    feedLayer.style.top = `${Number(data.y || 0)}px`;
    feedLayer.style.width = `${Number(data.width || 600)}px`;
    feedLayer.style.maxHeight = `${Number(data.height || 550)}px`;
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

    const glow = data.shadow
      ? "drop-shadow(0 0 1px rgba(0,0,0,0.95)) drop-shadow(0 0 3px rgba(0,0,0,0.78))"
      : "none";
    img.style.filter = glow;

    setPos(img, data, true);
    crosshairLayer.appendChild(img);
  }

  function renderStreak(data) {
    streakLayer.innerHTML = "";
    if (!data.visible) {
      return;
    }

    const core = document.createElement("div");
    core.className = "streak-core";
    const animActive = data.anim_active !== false;
    const speedVal = Number(data.anim_speed || 50);
    core.style.animation = "none";

    const knifeLayer = document.createElement("div");
    knifeLayer.className = "streak-knife-layer";
    if (animActive) {
      // Old Qt speed: 50 -> medium. Map to ~2.4s cycle and clamp.
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
    }

    const knives = Array.isArray(data.knives) ? data.knives : [];
    knives.forEach((knife) => {
      const img = document.createElement("img");
      img.className = "knife";
      if (!streakGlow) {
        img.classList.add("no-glow");
      }
      img.src = assetUrl(knife.filename);
      img.style.width = `${Number(knife.size || 90)}px`;
      img.style.height = `${Number(knife.size || 90)}px`;
      if (knife.x_off !== undefined && knife.y_off !== undefined) {
        img.style.transform = `translate(-50%, -50%) translate(${Number(knife.x_off)}px, ${Number(knife.y_off)}px) rotate(${Number(knife.rotation || 0)}deg)`;
      } else {
        const angle = Number(knife.angle || 0);
        const radius = Number(knife.radius || 90);
        img.style.transform = `translate(-50%, -50%) rotate(${angle}deg) translate(0, -${radius}px) rotate(${Number(knife.img_rotation || 0)}deg)`;
      }
      knifeLayer.appendChild(img);
    });

    core.appendChild(knifeLayer);
    core.appendChild(skull);
    core.appendChild(count);

    setPos(core, data, false);
    streakLayer.appendChild(core);
  }

  function pushEvent(layer, data, fallbackType) {
    if (!data.filename) {
      return;
    }

    const img = document.createElement("img");
    img.className = "event-item";
    img.src = assetUrl(data.filename);

    const width = Number(data.width || 220);
    const height = Number(data.height || 220);
    img.style.width = `${width}px`;
    img.style.height = `${height}px`;

    const evType = data.event_type || fallbackType || "event";
    if (evType === "death" || evType === "headshot") {
      img.classList.add("death-impact");
    }
    if (shouldTriggerImpact(data, evType)) {
      triggerImpact(evType);
    }

    const centered = Boolean(data.centered);
    setPos(img, data, centered);
    layer.appendChild(img);

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
    event: (data) => pushEvent(eventsLayer, data, "event"),
    hitmarker: (data) => pushEvent(hitmarkerLayer, data, data.event_type || "hitmarker"),
    events_clear: clearEvents
  };

  new window.OverlaySocket((message) => {
    const type = message.category;
    const payload = message.data || {};
    const handler = handlers[type];
    if (handler) {
      handler(payload);
    }
  });
})();
