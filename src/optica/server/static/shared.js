// Optica browser pages — shared behaviour.
//
// Plan § "Labeling & Curation": timeout warnings, Keep Session Active, light/dark
// and pagination are shared by both pages; labeling.js and curation.js hold only
// what differs. Not inlined into either page, because two copies of shared
// behaviour is a drift surface.
//
// Vanilla ES module, no build step. The server is the source of truth: every
// decision is sent to it as it happens, and the page renders what comes back.

// TODO(test): no JavaScript test runner exists in this build (no build step,
// and CI installs no Node). pageItems() and the heartbeat banner are exercised
// only by driving a real browser against a running server.

const HEARTBEAT_MS = 5000;
const MISSED_HEARTBEATS_BEFORE_ENDED = 2;
const THEME_KEY = "optica-theme";

/** A failed API call, carrying the server's own message. */
export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/** Call the server's JSON API. Throws ApiError on any non-2xx response. */
export async function api(path, { method = "GET", body } = {}) {
  const init = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const message = (data && data.error) || `Request failed (${response.status})`;
    if (data && data.ended) {
      showEnded("Optica hit an error", "See the terminal for what went wrong.");
    }
    throw new ApiError(message, response.status, data);
  }
  return data;
}

/** Create an element: el("div", { class: "x", onclick: fn }, [children]). */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2), value);
    } else if (key === "class") {
      node.className = value;
    } else if (value === true) {
      node.setAttribute(key, "");
    } else {
      node.setAttribute(key, String(value));
    }
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** "30 minutes", "2 minutes 30 seconds", "45 seconds" — as the terminal says it. */
export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  const parts = [];
  if (minutes) parts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`);
  if (rest || !minutes) parts.push(`${rest} second${rest === 1 ? "" : "s"}`);
  return parts.join(" ");
}

// ------------------------------------------------------------------- theme

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
}

function effectiveTheme() {
  const explicit = document.documentElement.dataset.theme;
  if (explicit) return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Light/dark: follows the system until the user picks, then remembers the pick. */
export function initTheme(button) {
  let stored = null;
  try {
    stored = localStorage.getItem(THEME_KEY);
  } catch {
    stored = null;
  }
  applyTheme(stored);
  const label = () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    button.textContent = next === "dark" ? "Dark mode" : "Light mode";
    button.setAttribute("aria-label", `Switch to ${next} mode`);
  };
  button.addEventListener("click", () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // Storage unavailable: the choice lasts for this page only.
    }
    label();
  });
  label();
}

// ----------------------------------------------------------- session state

let ended = false;

/** Replace the page with the "session ended" card. Idempotent. */
export function showEnded(title, message) {
  if (ended) return;
  ended = true;
  const overlay = el("div", { class: "ended-overlay", role: "status" }, [
    el("div", { class: "card" }, [el("h2", {}, title), el("p", { class: "muted" }, message)]),
  ]);
  document.body.append(overlay);
}

export function sessionEnded() {
  return ended;
}

/**
 * Poll the server's idle timer and show its warning with "Keep Session Active".
 *
 * The heartbeat itself is not activity — an open tab must not keep a session
 * alive forever. The warning appears when the server says one is due (30 and 5
 * minutes before shutdown at the default), and counts down to shutdown.
 */
export function watchSession(banner) {
  const text = banner.querySelector(".banner-text");
  const keep = banner.querySelector("button");
  let remaining = null;
  let missed = 0;
  let tick = null;

  const render = () => {
    if (remaining === null) return;
    text.textContent =
      `This session closes in ${formatDuration(remaining)} without activity. ` +
      "Your progress is saved either way.";
  };

  const hide = () => {
    banner.hidden = true;
    if (tick) clearInterval(tick);
    tick = null;
  };

  keep.addEventListener("click", async () => {
    keep.disabled = true;
    try {
      await api("/api/keepalive", { method: "POST" });
      hide();
    } finally {
      keep.disabled = false;
    }
  });

  const beat = async () => {
    if (ended) return;
    try {
      const status = await api("/api/heartbeat");
      missed = 0;
      if (status.ended) {
        showEnded("This session has ended", "You can close this tab. The terminal has the details.");
        return;
      }
      if (status.timeout_enabled && status.warning_seconds_left !== null) {
        remaining = status.remaining_seconds;
        banner.hidden = false;
        render();
        if (!tick) {
          tick = setInterval(() => {
            remaining = Math.max(0, remaining - 1);
            render();
          }, 1000);
        }
      } else {
        hide();
      }
    } catch {
      missed += 1;
      if (missed >= MISSED_HEARTBEATS_BEFORE_ENDED) {
        showEnded("This session has ended", "You can close this tab. The terminal has the details.");
      }
    }
  };

  beat();
  setInterval(beat, HEARTBEAT_MS);
}

// -------------------------------------------------------------- pagination

/**
 * Page numbers to show, with "…" standing in for runs of hidden pages.
 *
 * Smart ellipsis: the first and last page, the current page and its neighbours
 * always show, and an ellipsis never hides a single page — that page is shown
 * instead, since "…" would take the same room. Pages are 1-based.
 */
export function pageItems(current, total, siblings = 1) {
  if (total <= 0) return [];
  const shown = new Set([1, total]);
  for (let p = current - siblings; p <= current + siblings; p += 1) {
    if (p >= 1 && p <= total) shown.add(p);
  }
  const sorted = [...shown].sort((a, b) => a - b);
  const items = [];
  let previous = 0;
  for (const page of sorted) {
    const gap = page - previous - 1;
    if (gap === 1) items.push(previous + 1);
    else if (gap > 1) items.push("…");
    items.push(page);
    previous = page;
  }
  return items;
}

/** Render a pager into `container`. `onSelect(page)` is called with a 1-based page. */
export function renderPager(container, current, total, onSelect) {
  container.replaceChildren();
  if (total <= 1) return;
  container.append(
    el("button", {
      class: "btn",
      disabled: current <= 1,
      "aria-label": "Previous page",
      onclick: () => onSelect(current - 1),
    }, "‹"),
  );
  for (const item of pageItems(current, total)) {
    if (item === "…") {
      container.append(el("span", { class: "ellipsis", "aria-hidden": "true" }, "…"));
    } else {
      container.append(
        el("button", {
          class: "btn",
          "aria-current": item === current ? "page" : undefined,
          onclick: () => onSelect(item),
        }, String(item)),
      );
    }
  }
  container.append(
    el("button", {
      class: "btn",
      disabled: current >= total,
      "aria-label": "Next page",
      onclick: () => onSelect(current + 1),
    }, "›"),
  );
}

/**
 * How many grid cells fit the viewport without scrolling the page.
 *
 * Viewport-aware: columns from the grid's width, rows from the height left
 * below the grid's top edge, minus room reserved for what follows it.
 */
export function cellsThatFit(grid, cellSize, gap, reserveBelow) {
  const width = grid.clientWidth || window.innerWidth;
  const top = grid.getBoundingClientRect().top;
  const height = window.innerHeight - top - reserveBelow;
  const columns = Math.max(1, Math.floor((width + gap) / (cellSize + gap)));
  const rows = Math.max(1, Math.floor((height + gap) / (cellSize + gap)));
  return columns * rows;
}

// ------------------------------------------------------------------ notice

/**
 * A dismissible notice. `lines` are listed individually; `more` counts what the
 * list truncated.
 */
export function showNotice(container, title, lines = [], more = 0) {
  const list = lines.length
    ? el("ul", {}, lines.map((line) => el("li", {}, line)).concat(more ? [el("li", {}, `and ${more} more`)] : []))
    : null;
  const notice = el("div", { class: "notice", role: "status" }, [
    el("div", { class: "notice-head" }, [
      el("strong", {}, title),
      el("button", {
        class: "btn btn-quiet",
        "aria-label": "Dismiss",
        onclick: () => notice.remove(),
      }, "Dismiss"),
    ]),
    list,
  ]);
  container.append(notice);
  return notice;
}
