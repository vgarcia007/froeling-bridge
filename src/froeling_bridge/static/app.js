"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  health: null,
  parent: 1,
  crumbs: [{ parent: 1, title: "Heizung" }],
  view: "menu",
  generation: 0,
  editorGeneration: 0,
  parameter: null,
  item: null,
  busy: false,
  pending: null,
  times: [],
};
const editableTypes = new Set([7, 8, 10, 50, 57, 64]);
const views = {
  menu: [
    "Servicemenü",
    "Parameter finden, Werte prüfen und Änderungen nachvollziehen.",
  ],
  values: ["Messwerte", "Zuletzt gelesene Werte und ihre Aktualität."],
  times: [
    "Zeitprogramme",
    "Laufzeiten übersichtlich prüfen und gezielt ändern.",
  ],
  collector: ["Aufzeichnung", "Datensammlung und Speicherung nachvollziehen."],
};
const errorMessages = {
  outcome_unknown:
    "Das Ergebnis ist unklar. Der Wert wurde möglicherweise geändert. Bitte separat nachlesen; nicht blind erneut speichern.",
  verification_failed: "Der nachgelesene Wert weicht vom gewünschten Wert ab.",
  validation_error: "Die Eingabe wurde abgewiesen.",
  ReadOnlyViolation: "Schreiben ist in diesem Test gesperrt.",
  read_only: "Schreiben ist in diesem Test gesperrt.",
  database_unavailable: "Die Datenbank ist nicht erreichbar.",
  controller_unavailable:
    "In der Bestandsansicht ist keine direkte Heizungsabfrage verfügbar.",
  service_busy: "Die Steuerung ist gerade ausgelastet oder der Dienst beendet.",
  not_found:
    "Dieser Auftrag ist nicht mehr verfügbar. Eine Änderung nicht erneut senden, sondern den Wert separat prüfen.",
};
function element(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notice(text, error = false) {
  $("notice").textContent = text;
  $("notice").className = error ? "error" : "";
  $("notice").hidden = !text;
}
function explain(error) {
  return (
    errorMessages[error?.code] ||
    error?.message ||
    "Die Anfrage konnte nicht abgeschlossen werden."
  );
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch("/api/v1" + path, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(explain(data.error));
      error.code = data.error?.code;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timeout);
  }
}
function format(value, unit = "") {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return (
    (Number.isFinite(numeric)
      ? new Intl.NumberFormat("de-DE", { maximumFractionDigits: 5 }).format(
          numeric
        )
      : String(value)) + (unit ? " " + unit : "")
  );
}
function stamp(value) {
  if (!value) return "Noch nicht vorhanden";
  return new Date(value).toLocaleString("de-DE");
}
async function job(payload, onStatus = () => {}, valid = () => true) {
  // A POST is sent exactly once. Network failures leave its outcome unknown.
  let accepted;
  try {
    accepted = await api("/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if (payload.operation.startsWith("write_") && !error.code)
      throw new Error(
        "Übertragung unterbrochen. Ein Auftrag könnte angenommen worden sein. Bitte separat nachlesen; nicht erneut speichern."
      );
    throw error;
  }
  const deadline = Date.now() + 130000;
  let delay = 300;
  while (Date.now() < deadline) {
    if (!valid()) return null;
    await new Promise((resolve) => setTimeout(resolve, delay));
    let result;
    try {
      result = await api("/jobs/" + accepted.id);
      delay = 300;
    } catch (error) {
      if (error.code) throw error;
      onStatus("Verbindung unterbrochen. Auftragsstatus wird erneut geprüft …");
      delay = Math.min(5000, delay * 2);
      continue;
    }
    onStatus(
      result.state === "queued"
        ? "Auftrag wartet auf die Steuerung …"
        : "Steuerung wird abgefragt …"
    );
    if (result.state === "failed") {
      const error = new Error(explain(result.error));
      error.code = result.error.code;
      error.actual = result.error.actual;
      throw error;
    }
    if (result.state === "completed") return result.result;
  }
  throw new Error(
    "Auftragsstatus nicht rechtzeitig bestätigt. Schreibauftrag nicht wiederholen; Wert separat nachlesen."
  );
}
function renderCrumbs() {
  const nav = $("breadcrumbs");
  nav.replaceChildren();
  state.crumbs.forEach((crumb, index) => {
    if (index) nav.append(element("span", "›"));
    const button = element("button", crumb.title);
    button.type = "button";
    button.addEventListener("click", () => {
      state.crumbs = state.crumbs.slice(0, index + 1);
      loadMenu(crumb.parent);
    });
    nav.append(button);
  });
}
function parameterValue(item, result) {
  return item.type === 8
    ? result.raw_value
      ? "Ja"
      : "Nein"
    : item.type === 10
    ? `${String(Math.floor(result.raw_value / 60)).padStart(2, "0")}:${String(
        result.raw_value % 60
      ).padStart(2, "0")}`
    : format(result.value, result.unit);
}
async function readMenuValues(items, generation) {
  if (!state.health?.capabilities.controller_read) return;
  for (const item of items) {
    if (generation !== state.generation) return;
    if (item.child || !editableTypes.has(item.type)) continue;
    const node = document.querySelector(`[data-value-id="${item.id}"]`);
    if (!node) continue;
    try {
      const result = await job(
        { operation: "read_parameter", menu_id: item.id },
        () => {},
        () => generation === state.generation
      );
      if (!result || generation !== state.generation) return;
      node.replaceChildren(
        element("strong", parameterValue(item, result)),
        element("small", "Frisch gelesen")
      );
    } catch (error) {
      if (generation !== state.generation) return;
      node.append(element("small", "Nicht frisch gelesen", "stale"));
      if (state.health.mode === "hardware-read") return;
    }
  }
}
function rowValue(item) {
  if (item.value === null || item.value === undefined) return "—";
  return String(item.value) + (item.unit ? " " + item.unit : "");
}
function renderRows(items, search = false) {
  const container = $("menu-items");
  container.replaceChildren();
  if (!items.length) {
    container.append(
      element(
        "p",
        search
          ? "Keine passenden Menüeinträge gefunden."
          : "Diese Menüebene enthält keine Einträge.",
        "empty"
      )
    );
    return;
  }
  for (const item of items) {
    const group = Boolean(item.child);
    const row = element("div", "", "menu-row" + (group ? " group" : ""));
    row.append(element("div", group ? "▱" : "≋", "row-icon"));
    const title = element("div");
    title.append(
      element("p", item.title || "Unbenannter Eintrag", "row-title"),
      element(
        "span",
        group
          ? "Untermenü"
          : `Adresse 0x${Number(item.address)
              .toString(16)
              .toUpperCase()
              .padStart(4, "0")} · Typ 0x${Number(item.type)
              .toString(16)
              .toUpperCase()}`,
        "row-subtitle"
      )
    );
    row.append(title);
    const value = element("div", "", "row-value");
    value.dataset.valueId = String(item.id);
    value.append(
      element("strong", group ? "" : rowValue(item)),
      element(
        "small",
        group
          ? ""
          : state.health?.mode === "demo" || state.health?.mode === "demo-db"
          ? "Simulationsmenü"
          : "Gespeicherter Menüwert"
      )
    );
    row.append(value);
    const button = element(
      "button",
      group
        ? "Öffnen →"
        : editableTypes.has(item.type)
        ? state.health?.capabilities?.heating_write
          ? "Bearbeiten"
          : "Ansehen"
        : "Details",
      "button secondary row-action"
    );
    button.type = "button";
    button.addEventListener("click", async () => {
      if (group) {
        if (search) {
          state.crumbs = [{ parent: 1, title: "Heizung" }];
          if (item.parent !== 1)
            state.crumbs.push({
              parent: item.parent,
              title: "Ebene " + item.parent,
            });
        }
        state.crumbs.push({
          parent: item.child,
          title: item.title || "Untermenü",
        });
        await loadMenu(item.child);
      } else {
        await openParameter(item, value);
      }
    });
    row.append(button);
    container.append(row);
  }
}
async function loadMenu(parent = state.parent, search = "") {
  const generation = ++state.generation;
  state.parent = parent;
  if (!search) $("search").value = "";
  renderCrumbs();
  $("menu-items").replaceChildren(element("p", "Menü wird geladen …", "empty"));
  notice("");
  try {
    const data = await api(
      search
        ? "/menu/search?q=" + encodeURIComponent(search)
        : "/menu?parent=" + parent
    );
    if (generation !== state.generation) return;
    $("level-title").textContent = search
      ? "Suchergebnisse"
      : state.crumbs[state.crumbs.length - 1]?.title || "Heizungsmenü";
    $("level-subtitle").textContent = `${data.items.length} Einträge · ${
      search ? "Suche im gesamten Menü" : "Werte bei Bedarf frisch auslesen"
    }`;
    renderRows(data.items, Boolean(search));
    readMenuValues(data.items, generation);
  } catch (error) {
    if (generation === state.generation) {
      $("menu-items").replaceChildren(
        element("p", "Menü konnte nicht geladen werden.", "empty")
      );
      notice(error.message, true);
    }
  }
}
function readOnlyLabel() {
  return state.health?.mode === "hardware-read"
    ? "Lesender Hardwaretest: Änderungen gesperrt."
    : "Bestandsansicht: gespeicherte Daten, keine direkte Heizungsabfrage.";
}
async function openParameter(item, rowValueNode) {
  const generation = ++state.editorGeneration;
  state.item = item;
  state.rowValueNode = rowValueNode;
  state.parameter = null;
  $("editor-title").textContent = item.title || "Parameter";
  $("editor-description").textContent = "Aktueller Wert wird geladen …";
  $("parameter-meta").replaceChildren();
  $("input-wrap").replaceChildren();
  $("edit-result").textContent = "";
  $("edit-result").className = "";
  $("save-parameter").hidden = true;
  $("input-label").hidden = true;
  $("editor").showModal();
  try {
    if (!editableTypes.has(item.type)) {
      $("editor-description").textContent =
        "Dieser Menütyp ist nicht als veränderbarer Parameter bekannt. Gespeicherter Wert: " +
        rowValue(item);
      return;
    }
    if (!state.health.capabilities.controller_read) {
      $("editor-description").textContent =
        readOnlyLabel() + " Gespeicherter Wert: " + rowValue(item);
      return;
    }
    const result = await job(
      { operation: "read_parameter", menu_id: item.id },
      (text) => {
        if (generation === state.editorGeneration)
          $("edit-result").textContent = text;
      },
      () => generation === state.editorGeneration
    );
    if (!result || generation !== state.editorGeneration) return;
    state.parameter = result;
    const current = parameterValue(item, result);
    rowValueNode.replaceChildren(
      element("strong", current),
      element("small", "Frisch gelesen")
    );
    $("editor-description").textContent = `Aktueller Wert: ${current}`;
    $("parameter-meta").replaceChildren();
    for (const [title, value] of [
      ["Minimum", result.minimum],
      ["Maximum", result.maximum],
      ["Standard", result.default],
    ]) {
      const box = element("div");
      box.append(element("small", title), element("strong", String(value)));
      $("parameter-meta").append(box);
    }
    const input = element("input");
    input.id = "parameter-input";
    input.type =
      item.type === 8 ? "checkbox" : item.type === 10 ? "time" : "text";
    if (item.type === 8) input.checked = Boolean(result.raw_value);
    else if (item.type === 10) {
      input.value = current;
      input.step = "60";
    } else {
      input.inputMode = "decimal";
      input.value = result.value;
      input.maxLength = 40;
    }
    input.disabled = !state.health.capabilities.heating_write;
    $("input-wrap").replaceChildren(input);
    $("input-label").hidden = false;
    $("input-label").textContent = state.health.capabilities.heating_write
      ? "Neuer Wert"
      : "Aktueller Wert";
    $("save-parameter").hidden = !state.health.capabilities.heating_write;
    $("edit-result").textContent = state.health.capabilities.heating_write
      ? "Änderungen werden nach dem Schreiben erneut geprüft."
      : readOnlyLabel();
  } catch (error) {
    if (generation === state.editorGeneration) {
      $("edit-result").textContent = error.message;
      $("edit-result").className = "error";
    }
  }
}
function closeEditor() {
  if (state.busy) return;
  state.editorGeneration++;
  $("editor").close();
}
$("close-editor").addEventListener("click", closeEditor);
$("cancel-editor").addEventListener("click", closeEditor);
$("editor").addEventListener("cancel", (event) => {
  if (state.busy) event.preventDefault();
  else state.editorGeneration++;
});
$("edit-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (
    state.busy ||
    !state.parameter ||
    !state.health.capabilities.heating_write
  )
    return;
  const input = $("parameter-input");
  const value =
    state.item.type === 8
      ? input.checked
      : state.item.type === 10
      ? input.value
      : input.value.trim().replace(",", ".");
  state.pending = {
    operation: "write_parameter",
    menu_id: state.item.id,
    value,
  };
  $("confirm-description").textContent = `${state.item.title}: neuer Wert ${
    typeof value === "boolean" ? (value ? "Ja" : "Nein") : value
  }`;
  $("confirmation").showModal();
});
$("cancel-confirm").addEventListener("click", () => $("confirmation").close());
$("confirm-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy || !state.pending) return;
  const pending = state.pending;
  state.pending = null;
  $("confirmation").close();
  state.busy = true;
  let mustReadAgain = false;
  $("save-parameter").disabled = true;
  $("close-editor").disabled = true;
  $("cancel-editor").disabled = true;
  $("edit-result").className = "";
  try {
    const result = await job(
      pending,
      (text) => ($("edit-result").textContent = text)
    );
    $("edit-result").textContent =
      result.status === "unchanged"
        ? "Unverändert: es war kein Schreibbefehl nötig."
        : "Änderung bestätigt: Zielwert erfolgreich nachgelesen.";
    state.parameter = result.current;
    if (state.rowValueNode)
      state.rowValueNode.replaceChildren(
        element("strong", parameterValue(state.item, result.current)),
        element("small", "Nachgelesen")
      );
    if (state.item.type !== 8 && state.item.type !== 10)
      $("parameter-input").value = result.current.value;
  } catch (error) {
    mustReadAgain = error.code !== "validation_error";
    $("edit-result").textContent =
      error.message +
      (mustReadAgain
        ? " Schließen und vor einer weiteren Änderung erneut auslesen."
        : "");
    $("edit-result").className = "error";
    if (error.actual) state.parameter = error.actual;
  } finally {
    state.busy = false;
    $("save-parameter").disabled = mustReadAgain;
    $("close-editor").disabled = false;
    $("cancel-editor").disabled = false;
  }
});
async function loadValues() {
  const generation = state.generation;
  try {
    const data = await api("/values");
    if (state.view !== "values" || generation !== state.generation) return;
    const container = $("values-grid");
    container.replaceChildren();
    if (!data.items.length)
      container.append(
        element(
          "p",
          "Noch keine Werte gelesen. Der erste Sammeldurchlauf läuft möglicherweise noch.",
          "empty"
        )
      );
    for (const row of data.items) {
      const card = element("article", "", "value-card");
      card.append(
        element(
          "h2",
          row.title ||
            `${row.type} · 0x${row.address.toString(16).toUpperCase()}`
        ),
        element(
          "strong",
          row.type === "UD" && row.text ? row.text : format(row.value, row.unit)
        ),
        element(
          "small",
          `${row.stale ? "Veraltet · " : ""}Gelesen ${stamp(row.observed_at)}`,
          row.stale ? "stale" : ""
        )
      );
      container.append(card);
    }
  } catch (error) {
    if (state.view === "values") notice(error.message, true);
  }
}
async function loadCollector() {
  try {
    const data = await api("/collector");
    if (state.view !== "collector") return;
    const container = $("collector-content");
    container.replaceChildren(element("h2", "Kontinuierliche Aufzeichnung"));
    const grid = element("div", "", "stat-grid");
    for (const [label, value] of [
      [
        "Status",
        !data.enabled ? "Inaktiv" : data.running ? "Durchlauf läuft" : "Bereit",
      ],
      ["Intervall", data.interval_seconds + " s"],
      ["Zuletzt gespeichert", data.stored],
      ["Erfolgreiche Durchläufe", data.successful_cycles || 0],
    ]) {
      const box = element("div", "", "stat");
      box.append(element("span", label), element("strong", String(value)));
      grid.append(box);
    }
    container.append(
      grid,
      element("p", "Letzter Durchlauf: " + stamp(data.last_cycle)),
      element("p", "Letzte Speicherung: " + stamp(data.last_successful_store))
    );
    if (data.errors.length) {
      container.append(element("h2", "Fehler"));
      for (const error of data.errors)
        container.append(
          element(
            "p",
            `${error.type || ""} ${error.address ?? ""}: ${explain(
              error.error
            )}`,
            "stale"
          )
        );
    }
    if (data.skipped.length)
      container.append(
        element(
          "p",
          `${data.skipped.length} Sensoren wurden übersprungen (nicht unterstützter Typ).`
        )
      );
  } catch (error) {
    if (state.view === "collector") notice(error.message, true);
  }
}
async function loadTimes() {
  if (!state.health?.capabilities.controller_read) {
    notice(readOnlyLabel());
    return;
  }
  const button = $("load-times");
  button.disabled = true;
  const generation = state.generation;
  try {
    const times = await job(
      { operation: "time_ranges" },
      (text) => notice(text),
      () => state.view === "times" && state.generation === generation
    );
    if (!times) return;
    state.times = times;
    renderTimes();
    notice("Zeitprogramme frisch gelesen.");
  } catch (error) {
    notice(error.message, true);
  } finally {
    button.disabled = false;
  }
}
function renderTimes() {
  const container = $("time-programs");
  container.replaceChildren();
  for (const program of state.times) {
    if (program.address === 223) continue;
    const section = element("section", "", "time-program");
    section.append(
      element(
        "h2",
        "Adresse 0x" +
          program.address.toString(16).toUpperCase().padStart(2, "0")
      )
    );
    program.ranges.forEach((interval, index) => {
      const form = element("form", "", "interval-row");
      const prefix = `time-${program.address}-${index}`;
      const start = element("input");
      start.type = state.health.capabilities.heating_write ? "time" : "text";
      start.step = "600";
      start.value = interval.start || "";
      start.id = prefix + "-start";
      const end = element("input");
      end.type = state.health.capabilities.heating_write ? "time" : "text";
      end.step = "600";
      end.value = interval.end || "";
      end.id = prefix + "-end";
      const startLabel = element("label", `${index + 1}. Von`);
      startLabel.htmlFor = start.id;
      const endLabel = element("label", "bis");
      endLabel.htmlFor = end.id;
      const button = element(
        "button",
        "Prüfen & speichern",
        "button secondary"
      );
      button.type = "submit";
      const output = element("output");
      start.disabled =
        end.disabled =
        button.disabled =
          !state.health.capabilities.heating_write;
      form.append(startLabel, start, endLabel, end, button, output);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!state.health.capabilities.heating_write) return;
        if (
          !window.confirm(
            `Intervall ${index + 1} auf ${start.value || "unbelegt"} – ${
              end.value || "unbelegt"
            } setzen?`
          )
        )
          return;
        button.disabled = true;
        let uncertain = false;
        try {
          const result = await job(
            {
              operation: "write_time_range",
              address: program.address,
              index,
              start: start.value || null,
              end: end.value || null,
            },
            (text) => (output.textContent = text)
          );
          program.ranges = result.current.ranges;
          renderTimes();
          notice(
            result.status === "unchanged"
              ? "Zeitprogramm unverändert."
              : "Zeitprogramm durch Nachlesen bestätigt."
          );
        } catch (error) {
          uncertain = error.code !== "validation_error";
          output.textContent =
            error.message +
            (uncertain ? " Vor einer weiteren Änderung erneut auslesen." : "");
        } finally {
          button.disabled =
            !state.health.capabilities.heating_write || uncertain;
        }
      });
      section.append(form);
    });
    container.append(section);
  }
  if (!container.children.length)
    container.append(element("p", "Keine Zeitprogramme gefunden.", "empty"));
}
function switchView(view) {
  state.view = view;
  state.generation++;
  notice("");
  for (const [key, description] of Object.entries(views)) {
    $(key + "-view").hidden = key !== view;
    $("nav-" + key).classList.toggle("active", key === view);
  }
  [$("view-title").textContent, $("view-description").textContent] =
    views[view];
  if (view === "menu") loadMenu();
  if (view === "values") loadValues();
  if (view === "collector") loadCollector();
  if (view === "times")
    $("load-times").disabled = !state.health?.capabilities.controller_read;
}
for (const button of document.querySelectorAll("[data-view]"))
  button.addEventListener("click", () => switchView(button.dataset.view));
$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadMenu(state.parent, $("search").value.trim());
});
$("refresh").addEventListener("click", () => switchView(state.view));
$("load-times").addEventListener("click", loadTimes);
async function healthLoop() {
  let delay = 4000;
  try {
    const health = await api("/health");
    const first = !state.health;
    state.health = health;
    $("version").textContent = health.version || "";
    $("connection").textContent = health.fatal_reason
      ? "Test wird beendet"
      : "API verbunden";
    $("connection-dot").className =
      "dot " + (health.fatal_reason ? "offline" : "online");
    const hardware = health.mode === "hardware-read";
    $("mode").textContent = hardware
      ? "HEIZUNG · NUR LESEN"
      : health.mode === "database"
      ? "BESTAND · NUR LESEN"
      : "DEMO · SIMULATOR";
    $("mode").classList.toggle("hardware", hardware);
    $("mode-note").classList.toggle("hardware", hardware);
    $("mode-note").textContent = hardware
      ? "Lesender Hardwaretest. Neue Messpunkte werden nur in der separaten Testdatenbank gespeichert."
      : health.mode === "database"
      ? "Gespeicherte p4d-Daten. Keine direkte Heizungsabfrage und keine Änderungen."
      : "Du arbeitest mit fiktiven Heizungsdaten. Änderungen betreffen ausschließlich den Simulator.";
    if (first) loadMenu();
    if (state.view === "values") loadValues();
    if (state.view === "collector") loadCollector();
  } catch (error) {
    $("connection").textContent = "Verbindung unterbrochen";
    $("connection-dot").className = "dot offline";
    delay = 5000;
  } finally {
    setTimeout(healthLoop, delay);
  }
}
healthLoop();
