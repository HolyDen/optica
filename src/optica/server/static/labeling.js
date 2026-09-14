// Optica labeling page — only what differs from curation.
//
// Plan § "Labeling UI": one image at a time, a class widget (radio for 2–5
// classes, dropdown for 6+), a per-class count row, a position indicator, and
// Assign / Next / Back / Finish. The server decides everything — the widget,
// the Finish gate and its hint, the unlabeled split — and every decision is
// written to the session file before the response comes back.
//
// TODO(test): exercised only by driving a real browser against a running server.

import { api, el, initTheme, showEnded, showNotice, watchSession } from "/static/shared.js";

const $ = (id) => document.getElementById(id);
let state = null;
let busy = false;
let noticeShown = false;

async function act(path, body) {
  if (busy) return;
  busy = true;
  try {
    const next = await api(path, { method: "POST", body });
    render(next);
  } catch (error) {
    if (!document.querySelector(".ended-overlay")) window.alert(error.message);
  } finally {
    busy = false;
  }
}

function renderWidget() {
  const container = $("class-widget");
  container.replaceChildren();
  const current = state.image.state === "labeled" ? state.image.class : null;
  const assign = (name) => act("/api/label/assign", { index: state.index, class: name });

  if (state.widget === "radio") {
    const group = el("fieldset", { class: "class-radios" }, [el("legend", {}, "Class")]);
    for (const name of state.classes) {
      const input = el("input", {
        type: "radio",
        name: "class",
        value: name,
        checked: name === current,
        onchange: () => assign(name),
      });
      group.append(el("label", {}, [input, name]));
    }
    container.append(group);
    return;
  }

  const select = el("select", { "aria-label": "Class", onchange: (e) => assign(e.target.value) }, [
    el("option", { value: "", disabled: true, selected: current === null }, "Choose a class…"),
    ...state.classes.map((name) =>
      el("option", { value: name, selected: name === current }, name),
    ),
  ]);
  container.append(select);
}

function renderImage() {
  const stage = $("stage");
  const img = el("img", { src: `/api/image/${state.image.id}`, alt: state.image.name });
  // A truncated file can pass pre-flight's header check and still fail to draw.
  img.addEventListener("error", () => {
    stage.replaceChildren(
      el("div", { class: "broken" }, [
        el("strong", {}, "This image could not be displayed."),
        el("div", {}, "You can still assign a class, or press Next to skip it."),
      ]),
    );
  });
  stage.replaceChildren(img);
}

function render(next) {
  state = next;
  $("source").textContent = state.source;
  $("position").textContent = state.position;
  $("image-name").textContent = state.image.name;
  $("image-state").textContent = state.image.state === "skipped" ? "Skipped" : "";
  renderImage();
  renderWidget();

  $("auto-advance").checked = state.auto_advance;
  $("back").disabled = state.index === 0;
  // Next is always enabled: advancing without an assignment is how an image is skipped.
  $("next").disabled = false;

  $("counts").textContent = state.counts_line;
  const p = state.progress;
  $("progress").textContent = `${p.labeled} labeled · ${p.skipped} skipped · ${p.not_reached} not yet reached`;

  // Disabled buttons often do not register clicks, so the reason is always shown too.
  $("finish").disabled = !state.finish.enabled;
  $("finish-hint").hidden = state.finish.enabled;
  $("finish-hint").textContent = state.finish.hint || "";

  if (!noticeShown && state.unreadable.count > 0) {
    noticeShown = true;
    const n = state.unreadable.count;
    showNotice(
      $("notices"),
      `${n} file${n === 1 ? "" : "s"} could not be read and ${n === 1 ? "is" : "are"} not in this session. The files are untouched.`,
      state.unreadable.lines,
      state.unreadable.more,
    );
  }
}

async function finish() {
  if (busy) return;
  busy = true;
  try {
    let result = await api("/api/label/finish", { method: "POST", body: { confirmed: false } });
    if (result.status === "confirm") {
      if (!window.confirm(`${result.message}\n\nFinish anyway?`)) {
        render(result.state);
        return;
      }
      result = await api("/api/label/finish", { method: "POST", body: { confirmed: true } });
    }
    if (result.status === "finished") {
      showEnded("Labels submitted", "Optica is copying them into your dataset — the terminal shows the result. You can close this tab.");
      return;
    }
    render(result.state);
  } catch (error) {
    if (!document.querySelector(".ended-overlay")) window.alert(error.message);
  } finally {
    busy = false;
  }
}

$("next").addEventListener("click", () => act("/api/label/next", { index: state.index }));
$("back").addEventListener("click", () => act("/api/label/back", { index: state.index }));
$("auto-advance").addEventListener("change", (e) =>
  act("/api/label/auto-advance", { enabled: e.target.checked }),
);
$("finish").addEventListener("click", finish);

initTheme($("theme"));
watchSession($("timeout-banner"));
api("/api/label/state").then(render).catch((error) => window.alert(error.message));
