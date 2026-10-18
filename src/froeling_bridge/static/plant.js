"use strict";
const plantState = { loading: false, expanded: new Set(), refreshing: new Set(), attempted: new Map(), data: null };
const plantKinds = { kessel: ["◉", "Kessel"], puffer: ["▥", "Puffer"], boiler: ["♨", "Warmwasser"], heizkreis: ["⌁", "Heizkreis"] };

function plantOffline() {
  $("plant-status").textContent = "API nicht erreichbar · angezeigte Werte sind ein gespeicherter Stand.";
  $("plant-view").classList.add("plant-offline");
  for (const marker of $("plant-view").querySelectorAll(".plant-running")) marker.classList.remove("plant-running");
  for (const output of $("plant-view").querySelectorAll(".plant-output")) {
    output.querySelector("span:not(.plant-rotor)").textContent = "Zustand unbekannt";
  }
}

function plantMetric(metric) {
  const sensor = metric.sensor;
  const latest = sensor.latest;
  const unknown = metric.ambiguous || !latest || latest.stale;
  const item = element("div", "", "plant-metric" + (unknown ? " plant-unknown" : ""));
  item.append(element("span", metric.title, "plant-metric-title"));
  const text = latest ? latest.text || format(latest.value, latest.unit || sensor.unit) : "Noch nicht gelesen";
  item.append(element("strong", text));
  if (["pump", "mixer"].includes(metric.role)) {
    const numeric = latest ? Number(latest.value) : NaN;
    const running = !unknown && Number.isFinite(numeric) && numeric > 0;
    const output = element("div", "", "plant-output" + (running ? " plant-running" : ""));
    output.append(element("span", metric.role === "pump" ? "✣" : "⇄", "plant-rotor"));
    output.append(element("span", unknown ? "Zustand unbekannt" : running ? "Angesteuert" : "Nicht angesteuert"));
    if (sensor.unit === "%") {
      const meter = document.createElement("meter");
      meter.min = 0; meter.max = 100;
      meter.value = unknown ? 0 : Math.max(0, Math.min(100, numeric || 0));
      meter.setAttribute("aria-label", "Pumpenansteuerung");
      output.append(meter);
    }
    item.append(output);
  }
  item.append(element("small", metric.ambiguous ? "Zuordnung ungeklärt" : !latest ? "Abfrage noch nicht erfolgt" :
    latest.stale ? "Veralteter Stand · " + stamp(latest.observed_at) : "Gelesen: " + stamp(latest.observed_at)));
  return item;
}

async function refreshPlantComponent(component, force = false) {
  if (plantState.refreshing.has(component.id) || component.refresh_job_id) return;
  if (!force && Date.now() - (plantState.attempted.get(component.id) || 0) < 60000) return;
  plantState.attempted.set(component.id, Date.now());
  plantState.refreshing.add(component.id);
  try {
    const result = await job({operation: "refresh_component", component_id: component.id});
    if (result?.errors?.length) notice("Einige Einstellungen konnten nicht gelesen werden. Der letzte Stand bleibt sichtbar.", true);
  } catch (error) { notice(explain(error), true); }
  finally {
    plantState.refreshing.delete(component.id);
    if (state.view === "plant") loadPlant();
  }
}

function plantCard(component) {
  const card = element("article", "", "plant-card");
  card.dataset.componentId = component.id;
  const heading = element("div", "", "plant-card-heading");
  const [icon, kind] = plantKinds[component.kind];
  heading.append(element("span", icon, "plant-component-icon"));
  const title = element("div");
  title.append(element("small", kind), element("h2", component.title));
  heading.append(title);
  card.append(heading, element("p", component.path.join(" › "), "plant-path"));
  const metrics = element("div", "", "plant-metrics");
  for (const metric of component.metrics) metrics.append(plantMetric(metric));
  if (!component.metrics.length) metrics.append(element("p", "Keine eindeutigen Messwerte zugeordnet.", "muted"));
  card.append(metrics);
  const details = document.createElement("details");
  details.className = "plant-settings";
  details.open = plantState.expanded.has(component.id);
  details.append(element("summary", "Sollwerte & Schaltbedingungen (" + component.settings.length + ")"));
  const settings = element("div", "", "plant-settings-list");
  for (const setting of component.settings) {
    const row = element("div", "", "plant-setting" + (setting.stale || setting.error ? " plant-unknown" : ""));
    row.append(element("span", setting.title), element("strong", format(setting.value, setting.unit)));
    row.append(element("small", setting.error ? "Lesen fehlgeschlagen · letzter Stand" : setting.observed_at ?
      (setting.stale ? "Gespeicherter Stand · " : "Gelesen: ") + stamp(setting.observed_at) : "Noch nicht gelesen"));
    settings.append(row);
  }
  if (!component.settings.length) settings.append(element("p", "Keine passenden Einstellungen im Menü gefunden.", "muted"));
  details.append(settings);
  const refreshing = component.refresh_job_id || plantState.refreshing.has(component.id);
  const refresh = element("button", refreshing ? "Einstellungen werden gelesen …" : "Einstellungen aktualisieren", "button secondary");
  refresh.type = "button";
  refresh.disabled = !state.health?.capabilities.controller_read || Boolean(refreshing) || !component.settings.length;
  refresh.addEventListener("click", () => refreshPlantComponent(component, true));
  details.append(refresh, element("p", "Schwellen sind Einstellungen, keine vollständige Erklärung der aktuellen Regelung. Änderungen erfolgen im Servicemenü.", "plant-context"));
  details.addEventListener("toggle", () => {
    if (details.open) {
      plantState.expanded.add(component.id);
      if (state.health?.capabilities.controller_read && component.settings.some(s => s.stale)) refreshPlantComponent(component);
    } else plantState.expanded.delete(component.id);
  });
  card.append(details);
  return card;
}

async function loadPlant() {
  if (plantState.loading) return;
  plantState.loading = true;
  try {
    const data = await api("/plant");
    if (state.view !== "plant") return;
    plantState.data = data;
    $("plant-view").classList.remove("plant-offline");
    $("plant-status").textContent = data.components.length ?
      `${data.components.length} Gruppen · ${data.additional_sensors.length} zusätzliche Messwerte noch nicht zur Abfrage ausgewählt` :
      "Noch keine unterstützten Anlagengruppen im Katalog. Die Erkennung muss zuerst abgeschlossen sein.";
    $("plant-activate").hidden = !data.activation_available || (!data.additional_sensors.length && data.enabled);
    $("plant-activate").textContent = data.additional_sensors.length ? `${data.additional_sensors.length} zusätzliche Messwerte abfragen` : "Anlagenübersicht aktivieren";
    $("plant-grid").replaceChildren(...data.components.map(plantCard));
    $("plant-unassigned").hidden = !data.unassigned.length;
    $("plant-unassigned-values").replaceChildren(...data.unassigned.map(s => plantMetric({sensor: s, title: s.usrtitle || s.title, role: /mischer/i.test(s.title) ? "mixer" : "pump"})));
  } catch (error) { plantOffline(); notice(explain(error), true); }
  finally { plantState.loading = false; }
}

$("plant-activate").addEventListener("click", async () => {
  $("plant-activate").disabled = true;
  try {
    const result = await api("/plant/activate", {method: "POST", body: "{}"});
    notice(`${result.activated.length} zusätzliche Messwerte zur Abfrage ausgewählt. Die Historienauswahl bleibt erhalten.`);
    await loadPlant();
  } catch (error) { notice(explain(error), true); }
  finally { $("plant-activate").disabled = false; }
});
