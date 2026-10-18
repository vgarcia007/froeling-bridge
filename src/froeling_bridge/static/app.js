"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  health: null,
  parent: 1,
  crumbs: [{ parent: 1, title: "Heizung" }],
  view: location.pathname === "/anlage" ? "plant" : "menu",
  generation: 0,
  editorGeneration: 0,
  parameter: null,
  item: null,
  busy: false,
  times: [],
  errorsOffset: 0,
  timeCatalog: [],
  timeGroupFilter: null,
};
const editableTypes = new Set([7, 8, 10, 50, 57, 64]);
const views = {
  plant: ["Anlagenübersicht", "Temperaturen, Pumpen und Schwellwerte je Anlagenteil zusammen sehen."],
  menu: [
    "Servicemenü",
    "Parameter finden, Werte prüfen und Änderungen nachvollziehen.",
  ],
  values: ["Messwerte", "Zuletzt gelesene Werte und ihre Aktualität."],
  times: [
    "Zeitprogramme",
    "Laufzeiten übersichtlich prüfen und gezielt ändern.",
  ],
  errors: ["Fehlerspeicher", "Meldungen der Steuerung mit Zustand und Zeitpunkten."],
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
    if (item.child || !item.readable) continue;
    const node = document.querySelector(`[data-value-id="${item.id}"]`);
    if (!node) continue;
    try {
      const result = await job(
        { operation: editableTypes.has(item.type) ? "read_parameter" : "read_menu_value", menu_id: item.id },
        () => {},
        () => generation === state.generation
      );
      if (!result || generation !== state.generation) return;
      node.replaceChildren(
        element("strong", editableTypes.has(item.type) ? parameterValue(item, result) : result.display || format(result.value, result.unit)),
        element("small", "Frisch gelesen")
      );
    } catch (error) {
      if (generation !== state.generation) return;
      node.append(element("small", "Nicht frisch gelesen", "stale"));
      if (["hardware-read", "hardware-live", "standalone"].includes(state.health.mode)) return;
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
        search && item.breadcrumbs?.length
          ? item.breadcrumbs.map((crumb) => crumb.title).join(" › ")
          : group ? "Untermenü" : item.unit || "",
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
        ? canWrite("write_parameter")
          ? "Bearbeiten"
          : "Ansehen"
        : "Details",
      "button secondary row-action"
    );
    button.type = "button";
    button.addEventListener("click", async () => {
      if (item.time_program) {
        switchView("times", item.id);
        return;
      }
      if (group) {
        if (search) {
          state.crumbs = [{ parent: 1, title: "Heizung" }, ...(item.breadcrumbs || [])];
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
function canWrite(operation) {
  return state.health?.write_operations ? state.health.write_operations.includes(operation) : !!state.health?.capabilities.heating_write;
}
function readOnlyLabel() {
  return ["hardware-read", "hardware-live", "standalone"].includes(state.health?.mode)
    ? "Heizungsparameter: Änderungen gesperrt."
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
      if (item.readable && state.health.capabilities.controller_read) {
        const result = await job({ operation: "read_menu_value", menu_id: item.id });
        if (generation !== state.editorGeneration) return;
        const display = result.display || format(result.value, result.unit);
        $("editor-description").textContent = "Aktuell gelesen: " + display;
        rowValueNode.replaceChildren(element("strong",display),element("small","Frisch gelesen"));
      } else {
        $("editor-description").textContent = readOnlyLabel() + " Gespeicherter Wert: " + rowValue(item);
      }
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
      item.type === 8 ? "checkbox" : item.type === 10 ? "time" : item.type === 7 ? "number" : "text";
    if (item.type === 8) input.checked = Boolean(result.raw_value);
    else if (item.type === 10) {
      input.value = current;
      input.step = "60";
    } else {
      input.inputMode = "decimal";
      input.value = result.value;
      if (item.type === 7) {
        input.min = result.minimum;
        input.max = result.maximum;
        input.step = String(1 / Math.pow(10, result.digits));
      } else {
        input.maxLength = 40;
      }
    }
    input.disabled = !canWrite("write_parameter");
    $("input-wrap").replaceChildren(input);
    $("input-label").hidden = false;
    $("input-label").textContent = canWrite("write_parameter")
      ? "Neuer Wert"
      : "Aktueller Wert";
    $("save-parameter").disabled = !canWrite("write_parameter");
    $("save-parameter").hidden = !canWrite("write_parameter");
    $("edit-result").textContent = canWrite("write_parameter")
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
$("edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (
    state.busy ||
    !state.parameter ||
    !canWrite("write_parameter")
  )
    return;
  const input = $("parameter-input");
  const value =
    state.item.type === 8
      ? input.checked
      : state.item.type === 10
      ? input.value
      : input.value.trim().replace(",", ".");
  const pending = {
    operation: "write_parameter",
    menu_id: state.item.id,
    value,
  };
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
    const data = await api("/sensors");
    if (state.view !== "values" || generation !== state.generation) return;
    const query = $("sensor-search").value.trim().toLocaleLowerCase();
    const filter = $("sensor-filter").value;
    const items = data.items.filter(row => {
      const title = `${row.title || ""} ${row.usrtitle || ""}`.toLocaleLowerCase();
      if (query && !title.includes(query)) return false;
      if (filter === "active" && !row.active && !row.recording) return false;
      if (filter === "record" && !row.recording) return false;
      return filter !== "current" || row.latest && !row.latest.stale;
    });
    $("sensor-summary").textContent = `${items.length} von ${data.items.length} Sensoren · Werte aus dem letzten Auslesen, keine zusätzliche Heizungsabfrage.`;
    const container = $("values-grid");
    container.replaceChildren();
    for (const sensor of items) {
      const row = sensor.latest;
      const card = element("article", "", "value-card");
      card.append(element("h2", sensor.usrtitle || sensor.title),
        element("strong", row ? row.type === "UD" && row.text ? row.text : format(row.value, sensor.unit) : "Noch kein Wert gelesen"),
        element("small", row ? `${row.stale ? "Veraltet · " : ""}${row.origin === "local-persisted" ? "Letzter gespeicherter Stand · " : ""}Gelesen ${stamp(row.observed_at)}` : "Nicht abgefragt oder noch nicht erreichbar", row?.stale ? "stale" : ""),
        element("small", `${sensor.type} · Adresse ${sensor.address}`));
      if (!sensor.supported) card.append(element("p", "Dieser Sensortyp wird noch nicht unterstützt.", "stale"));
      for (const [field, label, checked] of [["active", "Regelmäßig abfragen", sensor.active], ["record", "Historie aufzeichnen", sensor.recording]]) {
        const control = document.createElement("input");
        control.type = "checkbox";
        control.checked = checked;
        control.disabled = !state.health?.capabilities.sensor_configuration || (!sensor.supported && !checked) || (field === "record" && sensor.recording_required);
        control.setAttribute("aria-label", label + ": " + (sensor.usrtitle || sensor.title));
        control.addEventListener("change", async () => {
          control.disabled = true;
          try {
            await api(`/sensors/${sensor.type}/${sensor.address}`, {method:"PATCH", body:JSON.stringify({[field]:control.checked})});
            notice("Auswahl gespeichert. Sie gilt ab dem nächsten Sammeldurchlauf.");
          } catch (error) {notice(error.message, true);}
          finally {loadValues();}
        });
        const wrapper = element("label", "", "sensor-option");
        wrapper.append(control, document.createTextNode(label));
        card.append(wrapper);
      }
      if (sensor.recording_required) card.append(element("small", "Wird wie bei p4d automatisch aufgezeichnet: Status, Betriebsart und Heizungszeit."));
      if (sensor.recording && !sensor.active) card.append(element("small", "Wird für die aktivierte Historie mit abgefragt."));
      container.append(card);
    }
    if (!items.length) container.append(element("p", "Keine passenden Sensoren.", "empty"));
  } catch (error) {
    if (state.view === "values") notice(error.message, true);
  }
}
$("sensor-search").addEventListener("input", loadValues);
$("sensor-filter").addEventListener("change", loadValues);
async function loadErrors() {
  try {
    const offset = state.errorsOffset;
    const data = await api("/errors?limit=100&offset=" + offset);
    if (state.view !== "errors" || offset !== state.errorsOffset) return;
    const sync = (await api("/runtime")).history?.controller_errors;
    if (state.view !== "errors" || offset !== state.errorsOffset) return;
    $("errors-status").textContent =
      (data.source === "p4d-database" ? "Datenbankhistorie · " : "Steuerungsspeicher · ") + data.total + " Einträge · " +
      (data.observed_at ? "Heizung zuletzt gelesen: " + stamp(data.observed_at) : "Steuerung noch nicht vollständig gelesen.") +
      (data.stale ? " · Veraltet" : "") +
      (data.error ? " · " + data.error : "") +
      (sync?.error ? " · MariaDB-Abgleich gestört" : "") +
      (data.fallback ? " · Datenbankhistorie nicht erreichbar – nur Steuerungseinträge sichtbar" : "");
    $("errors-pagination").hidden = !data.has_more && data.offset === 0;
    $("errors-previous").disabled = data.offset === 0;
    $("errors-next").disabled = !data.has_more;
    $("errors-page-status").textContent = data.items.length ? `${data.offset + 1}–${data.offset + data.items.length} von ${data.total}` : `0 von ${data.total}`;
    const container = $("errors-list");
    container.replaceChildren();
    if (!data.items.length) container.append(element("p", data.available ? (data.source === "p4d-database" ? "Keine Fehler auf dieser Seite der Datenbankhistorie." : "Keine zuordenbaren Fehlereinträge im gelesenen Heizungsfehlerspeicher.") : "Fehlerspeicher noch nicht verfügbar.", "empty"));
    for (const item of data.items) {
      const row = element("article", "", "error-entry");
      const heading = element("div", "", "error-heading");
      heading.append(element("h3", item.number + " · " + item.text, "error-title"));
      const unconfirmed = item.active !== true && item.active !== false;
      const label = unconfirmed ? "Nicht bestätigt" : item.active ? "Aktiv bestätigt" : item.state === "gekommen" ? "Nicht aktiv" : item.state;
      const stateClass = unconfirmed ? "" : item.active ? "error-state-active" : item.state === "gegangen" ? "error-state-gone" : "error-state-acknowledged";
      heading.append(element("span", label, "error-state " + stateClass));
      const times = element("dl", "", "error-times");
      for (const [key, title] of [["time1", "Gekommen"], ["time4", "Gegangen"], ["time2", "Quittiert"]]) {
        if (!item[key]) continue;
        const pair = element("div");
        const value = element("dd");
        const time = element("time", stamp(item[key]));
        time.dateTime = item[key];
        value.append(time); pair.append(element("dt", title), value); times.append(pair);
      }
      row.append(heading);
      if (unconfirmed) row.append(element("p", item.activity_basis === "not_in_controller"
        ? "Historischer Eintrag ohne dokumentiertes Ende. Im aktuellen Steuerungsspeicher nicht mehr enthalten; keine aktuell bestätigte Störung."
        : "Der zuletzt gespeicherte Zustand ist aktuell nicht durch eine frische Steuerungsabfrage bestätigt.", "error-context"));
      row.append(times); container.append(row);
    }
  } catch (error) { notice(explain(error), true); }
}

$("errors-previous").addEventListener("click", () => {
  state.errorsOffset = Math.max(0, state.errorsOffset - 100); loadErrors();
});
$("errors-next").addEventListener("click", () => {
  state.errorsOffset += 100; loadErrors();
});

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
      ["Im Durchlauf gespeichert / zur Historie übergeben", data.stored],
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
    const runtime = await api("/runtime");
    if (state.view !== "collector") return;
    if (runtime.phase !== "legacy-mode") {
      container.append(element("h2", "Heizungsverbindung"), element("p", `Betrieb: ${runtime.phase} · ${runtime.connection.connected ? "Verbunden" : "Nicht verbunden"}`));
      if (runtime.error) container.append(element("p", runtime.error, "stale"));
      if (runtime.persistence_error) container.append(element("p", runtime.persistence_error, "stale"));
      const history = runtime.history;
      container.append(element("h2", "Historien-Datenbank"), element("p", history.configured ? (history.available ? "Erreichbar" : "Nicht bereit — Live-Abfragen laufen unabhängig weiter") : "Nicht konfiguriert"));
      if (history.error) container.append(element("p", history.error, "stale"));
      if (history.configured) {
        container.append(element("p", `Tatsächlich gespeichert: ${history.stored} · Letzter DB-Erfolg: ${stamp(history.last_success)} · Ausstehende Einstellungen: ${history.pending_settings}`));
        container.append(element("p", `Ausgelassene Aufzeichnungsdurchläufe: ${history.dropped_cycles || 0}`));
      }
      if (history.aggregation) {
        const a = history.aggregation;
        container.append(element("h2", "Verdichtung"), element("p", `${history.history_days} Tage Einzelwerte · ${history.aggregate_minutes} Minuten je Aggregat · Nächster Lauf: ${stamp(history.next_aggregation)}`),
          element("p", `Letzter Erfolg: ${stamp(a.last_success)} · Verarbeitete Einzelwerte: ${a.processed} · Konflikte: ${a.conflicts}`));
        if (a.error) container.append(element("p", a.error, "stale"));
      }
    }
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
async function loadCachedTimes(autoRead = true) {
  const generation = state.generation;
  try {
    const data = await api("/time-programs");
    if (state.view !== "times" || generation !== state.generation) return;
    state.timeCatalog = data.programs;
    if (data.cache.available) {
      state.times = data.cache.items;
      renderTimes();
      $("time-cache-status").textContent = "Zuletzt gelesen: " + stamp(data.cache.observed_at);
    } else if (autoRead && state.health?.capabilities.controller_read) {
      $("time-cache-status").textContent = "Zeitprogramme werden erstmals gelesen …";
      await loadTimes();
    } else {
      renderTimes();
    }
  } catch (error) {
    if (state.view === "times") notice(error.message, true);
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
    if (!state.timeCatalog.length) {
      const data = await api("/time-programs");
      state.timeCatalog = data.programs;
    }
    const times = await job(
      { operation: "time_ranges" },
      (text) => notice(text),
      () => state.view === "times" && state.generation === generation
    );
    if (!times) return;
    state.times = times;
    renderTimes();
    notice("Zeitprogramme frisch gelesen.");
    await loadCachedTimes(false);
  } catch (error) {
    notice(error.message, true);
  } finally {
    button.disabled = false;
  }
}
function renderTimes() {
  const container = $("time-programs");
  container.replaceChildren();
  const byAddress = new Map(state.times.map((program) => [program.address, program]));
  const devices = new Map();
  for (const label of state.timeCatalog) {
    if (state.timeGroupFilter !== null && label.menu_id !== state.timeGroupFilter) continue;
    const program = byAddress.get(label.address);
    if (!program) continue;
    let device = devices.get(label.menu_id);
    if (!device) {
      device = element("section", "", "time-device");
      device.append(element("h2", label.device), element("p", label.path.join(" › "), "row-subtitle"));
      devices.set(label.menu_id, device);
      container.append(device);
    }
    const section = element("section", "", "time-program");
    section.append(element("h3", label.weekday));
    program.ranges.forEach((interval, index) => {
      const canEdit = canWrite("write_time_range") && !interval.raw;
      const form = element("form", "", "interval-row");
      const prefix = `time-${program.address}-${index}`;
      const start = element("input");
      start.type = canEdit ? "time" : "text";
      start.step = "600";
      start.value = interval.start || "";
      start.id = prefix + "-start";
      const end = element("input");
      end.type = canEdit ? "time" : "text";
      end.step = "600";
      end.value = interval.end || "";
      end.id = prefix + "-end";
      const startLabel = element("label", `${index + 1}. Von`);
      startLabel.htmlFor = start.id;
      const endLabel = element("label", "bis");
      endLabel.htmlFor = end.id;
      const button = element(
        "button",
        "Speichern",
        "button secondary"
      );
      button.type = "submit";
      const output = element("output");
      start.disabled =
        end.disabled =
        button.disabled =
          !canEdit;
      form.append(startLabel, start, endLabel, end, button, output);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!canEdit) return;
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
            !canEdit || uncertain;
        }
      });
      section.append(form);
    });
    device.append(section);
  }
  if (!container.children.length)
    container.append(element("p", "Keine Zeitprogramme gefunden.", "empty"));
}
function switchView(view, timeGroupFilter = null, navigate = true) {
  state.view = view;
  if (view === "times") state.timeGroupFilter = timeGroupFilter;
  state.generation++;
  notice("");
  for (const [key, description] of Object.entries(views)) {
    $(key + "-view").hidden = key !== view;
    $("nav-" + key).classList.toggle("active", key === view);
  }
  [$("view-title").textContent, $("view-description").textContent] =
    views[view];
  const path = view === "plant" ? "/anlage" : "/";
  if (navigate && location.pathname !== path) history.pushState({}, "", path);
  if (view === "plant") loadPlant();
  if (view === "menu") loadMenu();
  if (view === "values") loadValues();
  if (view === "collector") loadCollector();
  if (view === "errors") { state.errorsOffset = 0; loadErrors(); }
  if (view === "times") {
    $("load-times").disabled = !state.health?.capabilities.controller_read;
    loadCachedTimes();
  }
}
for (const button of document.querySelectorAll("[data-view]"))
  button.addEventListener("click", () => switchView(button.dataset.view));
window.addEventListener("popstate", () => switchView(location.pathname === "/anlage" ? "plant" : "menu", null, false));
$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadMenu(state.parent, $("search").value.trim());
});
$("refresh").addEventListener("click", () => state.view === "times" ? loadTimes() : switchView(state.view));
$("load-times").addEventListener("click", loadTimes);
async function healthLoop() {
  let delay = 4000;
  try {
    const health = await api("/health");
    const first = !state.health;
    state.health = health;
    $("version").textContent = health.version || "";
    const heatingDisconnected = health.controller_connection && !health.controller_connection.connected;
    $("connection").textContent = health.fatal_reason
      ? "Dienst wird beendet"
      : heatingDisconnected ? "API verbunden · Heizung getrennt" : "API verbunden";
    $("connection-dot").className =
      "dot " + (health.fatal_reason || heatingDisconnected ? "offline" : "online");
    const hardware = ["hardware-read", "hardware-live", "standalone"].includes(health.mode);
    $("mode").textContent = hardware
      ? (health.capabilities.heating_write ? "HEIZUNG · BEDIENUNG" : "HEIZUNG · NUR LESEN")
      : health.mode === "database"
      ? "BESTAND · NUR LESEN"
      : "DEMO · SIMULATOR";
    $("mode").classList.toggle("hardware", hardware);
    $("mode-note").classList.toggle("hardware", hardware);
    $("mode-note").textContent = health.preview
      ? "Lesende Anlagenvorschau · Daten aus der bestehenden API. Änderungen und Heizungsaufträge sind in dieser Vorschau gesperrt."
      : hardware
      ? (health.mode === "standalone" ? "Eigenständiger Betrieb. Live-Abfragen und Menü funktionieren unabhängig von MariaDB. Lesezeitpunkte zeigen die Aktualität." : health.mode === "hardware-live" ? "Dauerbetrieb. Neue Messpunkte werden in der bestehenden p4d-Datenbank gespeichert. Heizungsparameter sind schreibgeschützt." : "Lesender Hardwaretest. Neue Messpunkte werden nur in der separaten Testdatenbank gespeichert.")
      : health.mode === "database"
      ? "Gespeicherte p4d-Daten. Keine direkte Heizungsabfrage und keine Änderungen."
      : "Du arbeitest mit fiktiven Heizungsdaten. Änderungen betreffen ausschließlich den Simulator.";
    if (first) switchView(state.view);
    if (!first && state.view === "plant") loadPlant();
    if (state.view === "values") loadValues();
    if (state.view === "collector") loadCollector();
    if (state.view === "errors") loadErrors();
  } catch (error) {
    $("connection").textContent = "Verbindung unterbrochen";
    $("connection-dot").className = "dot offline";
    if (state.view === "plant" && typeof plantOffline === "function") plantOffline();
    delay = 5000;
  } finally {
    setTimeout(healthLoop, delay);
  }
}
healthLoop();
