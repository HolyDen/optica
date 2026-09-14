// Optica curation page — only what differs from labeling.
//
// Plan § "Curation Server" → Browser UI (curate): an image grid with
// click-to-toggle, Select All / Deselect All, per-class tabs or a dropdown
// (the server decides which), scroll arrows only when the tabs overflow,
// viewport-aware pagination, a 280 ms hover zoom, and a low-selection warning
// with a Fetch More banner that is advisory only. Every toggle is a request, and
// the server writes it to curation.json before answering.
//
// TODO(test): exercised only by driving a real browser against a running server.

import {
  api,
  cellsThatFit,
  el,
  initTheme,
  renderPager,
  showEnded,
  showNotice,
  watchSession,
} from "/static/shared.js";

const $ = (id) => document.getElementById(id);
const CELL = 150;
const GAP = 10;
const RESERVE_BELOW = 96; // the Confirm bar and page padding
const ZOOM_DELAY_MS = 280;
const FETCH_POLL_MS = 1500;

let state = null;
let page = 1;
let perPage = 24;
let busy = false;
let noticeShown = false;
let fetchPoll = null;
let zoomTimer = null;
let zoom = null;

async function act(path, body) {
  if (busy) return;
  busy = true;
  try {
    render(await api(path, { method: "POST", body }));
  } catch (error) {
    if (!document.querySelector(".ended-overlay")) window.alert(error.message);
  } finally {
    busy = false;
  }
}

const active = () => state.classes[state.active];

// ------------------------------------------------------------ navigation

function renderNav() {
  const nav = $("class-nav");
  nav.replaceChildren();
  if (state.navigation === "dropdown") {
    const select = el(
      "select",
      { "aria-label": "Class", onchange: (e) => switchClass(Number(e.target.value)) },
      state.classes.map((c) =>
        el(
          "option",
          { value: c.index, selected: c.index === state.active },
          `${c.name} — ${c.selected} of ${c.fetched} selected${c.warnings.length ? " ⚠" : ""}`,
        ),
      ),
    );
    nav.append(select);
    return;
  }

  const viewport = el("div", { class: "tabs-viewport" });
  const tabs = el("div", { class: "tabs", role: "tablist" });
  for (const c of state.classes) {
    tabs.append(
      el(
        "button",
        {
          class: `tab${c.warnings.length ? " warn" : ""}`,
          role: "tab",
          type: "button",
          "aria-selected": c.index === state.active ? "true" : "false",
          onclick: () => switchClass(c.index),
        },
        [c.name, el("span", { class: "tab-count" }, `${c.selected}/${c.fetched}`)],
      ),
    );
  }
  viewport.append(tabs);
  const left = el("button", { class: "btn", type: "button", "aria-label": "Scroll classes left" }, "‹");
  const right = el("button", { class: "btn", type: "button", "aria-label": "Scroll classes right" }, "›");
  left.addEventListener("click", () => viewport.scrollBy({ left: -viewport.clientWidth / 2 }));
  right.addEventListener("click", () => viewport.scrollBy({ left: viewport.clientWidth / 2 }));
  nav.append(left, viewport, right);

  // Arrows only when the tabs actually overflow the viewport.
  const updateArrows = () => {
    const overflow = tabs.scrollWidth > viewport.clientWidth + 1;
    left.hidden = !overflow;
    right.hidden = !overflow;
  };
  requestAnimationFrame(updateArrows);
  window.addEventListener("resize", updateArrows, { once: true });
}

function switchClass(index) {
  if (index === state.active) return;
  page = 1;
  act("/api/curate/active", { class: index });
}

// ---------------------------------------------------------------- banner

function renderBanner() {
  const banner = $("low-selection");
  const button = $("fetch-more");
  const c = active();
  const lines = [...c.warnings];
  const fetching = state.fetching && state.fetching.class === c.name;
  if (fetching) {
    lines.push(`Fetching ${state.fetching.requested} more for ${c.name}: ${state.fetching.delivered} so far…`);
  }
  const last = state.last_fetch && state.last_fetch.class === c.name ? state.last_fetch : null;
  if (last && !fetching) {
    lines.push(
      last.error
        ? `Fetch More for ${c.name} stopped: ${last.error}`
        : `Fetch More added ${last.delivered} of ${last.requested} requested images to ${c.name}.`,
    );
  }
  if (!lines.length) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.querySelector(".banner-text").replaceChildren(
    el("ul", {}, lines.map((line) => el("li", {}, line))),
  );
  const offer = c.warnings.length && c.fetch_more.available && !state.fetching;
  button.hidden = !offer;
  if (offer) button.textContent = `Fetch ${c.fetch_more.count} more`;
}

// ------------------------------------------------------------------ grid

function hideZoom() {
  clearTimeout(zoomTimer);
  zoomTimer = null;
  if (zoom) zoom.remove();
  zoom = null;
}

function showZoom(tile, src) {
  hideZoom();
  zoomTimer = setTimeout(() => {
    const rect = tile.getBoundingClientRect();
    zoom = el("div", { class: "zoom", "aria-hidden": "true" }, [el("img", { src, alt: "" })]);
    document.body.append(zoom);
    const box = zoom.getBoundingClientRect();
    const left = rect.right + 8 + box.width < window.innerWidth ? rect.right + 8 : Math.max(8, rect.left - 8 - box.width);
    const top = Math.min(Math.max(8, rect.top), window.innerHeight - box.height - 8);
    zoom.style.left = `${left}px`;
    zoom.style.top = `${top}px`;
  }, ZOOM_DELAY_MS);
}

function renderGrid() {
  hideZoom();
  const grid = $("grid");
  perPage = cellsThatFit(grid, CELL, GAP, RESERVE_BELOW);
  const pages = Math.max(1, Math.ceil(state.images.length / perPage));
  page = Math.min(page, pages);
  const start = (page - 1) * perPage;
  const shown = state.images.slice(start, start + perPage);
  const classIndex = state.active;
  const fetching = state.fetching && state.fetching.class === active().name;

  grid.replaceChildren(
    ...shown.map((image) => {
      const index = Number(image.id.split("/")[1]);
      const src = `/api/image/${image.id}`;
      const img = el("img", { src, alt: image.name, loading: "lazy" });
      const tile = el(
        "button",
        {
          class: `tile${image.selected ? "" : " deselected"}`,
          type: "button",
          role: "listitem",
          "aria-pressed": image.selected ? "true" : "false",
          "aria-label": `${image.name}, ${image.selected ? "selected" : "not selected"}`,
          disabled: fetching,
          onclick: () => act("/api/curate/select", { class: classIndex, image: index, selected: !image.selected }),
          onmouseenter: () => showZoom(tile, src),
          onmouseleave: hideZoom,
        },
        [img, el("span", { class: "mark", "aria-hidden": "true" }, image.selected ? "✓" : "")],
      );
      img.addEventListener("error", () => {
        tile.replaceChildren(el("span", { class: "broken" }, "Could not display"), tile.lastChild);
      });
      return tile;
    }),
  );

  renderPager($("pager"), page, pages, (next) => {
    page = next;
    renderGrid();
  });
}

// ---------------------------------------------------------------- render

function render(next) {
  state = next;
  const c = active();
  renderNav();
  renderBanner();
  $("summary").textContent = `${c.name}: ${c.selected} of ${c.fetched} selected`;
  $("select-all").disabled = c.selected === c.fetched;
  $("deselect-all").disabled = c.selected === 0;
  renderGrid();

  // Only a class with zero selected disables Confirm; the reason is always shown.
  $("confirm").disabled = !state.confirm.enabled;
  $("confirm-hint").hidden = state.confirm.enabled;
  $("confirm-hint").textContent = state.confirm.hint || "";

  if (!noticeShown && state.incomplete.length) {
    noticeShown = true;
    showNotice(
      $("notices"),
      `The fetch for ${state.incomplete.join(", ")} did not finish; curating what was fetched.`,
    );
  }

  if (state.fetching && !fetchPoll) {
    fetchPoll = setInterval(async () => {
      try {
        const latest = await api("/api/curate/state");
        if (!latest.fetching) {
          clearInterval(fetchPoll);
          fetchPoll = null;
        }
        if (!busy) render(latest);
      } catch {
        clearInterval(fetchPoll);
        fetchPoll = null;
      }
    }, FETCH_POLL_MS);
  }
}

$("select-all").addEventListener("click", () => act("/api/curate/select-all", { class: state.active, selected: true }));
$("deselect-all").addEventListener("click", () => act("/api/curate/select-all", { class: state.active, selected: false }));
$("fetch-more").addEventListener("click", () => act("/api/curate/fetch-more", { class: state.active }));
$("confirm").addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  try {
    const result = await api("/api/curate/confirm", { method: "POST" });
    if (result.status === "finished") {
      hideZoom();
      showEnded("Selection confirmed", "Optica continues in the terminal. You can close this tab.");
      return;
    }
    render(result.state);
  } catch (error) {
    if (!document.querySelector(".ended-overlay")) window.alert(error.message);
  } finally {
    busy = false;
  }
});

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => state && renderGrid(), 120);
});

initTheme($("theme"));
watchSession($("timeout-banner"));
api("/api/curate/state").then(render).catch((error) => window.alert(error.message));
