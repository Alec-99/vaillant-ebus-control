/* Read-only Home Assistant Ingress adapter.
 * This file is served ONLY by the add-on, never embedded in standalone HTML.
 * Browser speaks same-origin HTTPS Ingress; MQTT credentials remain server-side.
 * All normal thermostat/curve controls remain simulated and cannot write MQTT.
 */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const GET = async path => {
    const response = await fetch(path, { method: "GET", credentials: "same-origin",
      cache: "no-store", headers: { "Accept": "application/json" } });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "API " + response.status);
    return body;
  };
  const FIELDS = [
    ["flow_actual_c", "Aanvoer"], ["return_actual_c", "Retour"],
    ["flow_target_c", "Ketel-setpoint"], ["flame", "Brander"],
    ["pump", "Pomp"], ["boiler_state", "Toestand"],
    ["modulation_desired_pct", "Modulatievraag"],
    ["remaining_boiler_block_min", "Branderblokkering"]
  ];
  let lastId = 0;
  let stream = null;

  window.VaillantLive = {
    enabled: true,
    readCommand: async command => {
      const text = command.trim();
      const allowed = /^(help|info|state|read -c bai (FlowTemp|ReturnTemp|FlowTempDesired|Flame|WP|Statenumber|ModulationDesired|RemainingBoilerblocktime))$/;
      if (!allowed.test(text)) throw new Error("NIET UITGEVOERD: alleen read-only BAI-cacheregisters toegestaan.");
      const reply = await GET("api/v1/terminal?command=" + encodeURIComponent(text));
      return reply.output || "Geen beschikbare uitvoer.";
    }
  };

  function markConnection(label, state) {
    const element = $("live-connection");
    if (element) element.textContent = label;
    const badge = $("live-overview-status");
    if (badge) badge.textContent = label;
    if (window.VaillantMqttViewer) window.VaillantMqttViewer.setConnection(state);
  }

  function asField(key, observation) {
    const node = $("live-" + key);
    if (!node) return;
    if (!observation || observation.value === null || observation.value === undefined) {
      node.textContent = "— · " + (observation ? observation.quality : "geen telemetrie");
      return;
    }
    const unit = observation.unit ? " " + observation.unit : "";
    // Cache value is displayed with explicit uncertainty, never as confirmed live.
    node.textContent = String(observation.value) + unit + " · " + observation.quality;
  }

  function applyStatus(status) {
    markConnection(status.mqtt_connected ? "MQTT verbonden · alleen lezen" :
      "Ingress actief · MQTT niet verbonden", Boolean(status.mqtt_connected));
    $("live-bus-state").textContent = status.boiler_bus_enabled
      ? "Adapter ingeschakeld · cache niet als vers bevestigd"
      : "Adapter uitgeschakeld · geen echte ketelmetingen";
    const rt = status.runtime;
    $("live-controller-state").textContent = rt && rt.controller
      ? String(rt.controller) + " · geen eBUS-schrijfrechten"
      : "Geen controllerstatus ontvangen";
    const telemetry = status.telemetry;
    if (telemetry && telemetry.measurements) {
      for (const [key] of FIELDS) asField(key, telemetry.measurements[key]);
      $("live-snapshot-time").textContent = telemetry.sampled_at
        ? "Cache uitgevraagd: " + telemetry.sampled_at + " · oorspronkelijke meettijd onbekend"
        : "Geen eBUS-meettijd bekend";
    } else {
      for (const [key] of FIELDS) asField(key, null);
      $("live-snapshot-time").textContent = "Nog geen telemetrie-bericht ontvangen";
    }
  }

  function showEvents(data) {
    const target = $("live-events");
    if (!target) return;
    target.textContent = "";
    const items = Array.isArray(data.events) ? data.events.slice(-20).reverse() : [];
    if (!items.length) {
      target.textContent = "Nog geen backend-gebeurtenissen ontvangen.";
      return;
    }
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "event";
      const date = document.createElement("span");
      date.className = "time";
      date.textContent = new Date(item.timestamp).toLocaleTimeString("nl-BE", {hour12:false});
      const topic = document.createElement("span");
      topic.className = "description";
      topic.textContent = item.topic;
      row.append(date, topic);
      target.appendChild(row);
    }
  }

  function addMessage(item) {
    if (!item || !Number.isInteger(item.id) || item.id <= lastId) return;
    lastId = item.id;
    if (window.VaillantMqttViewer) window.VaillantMqttViewer.appendLive(item);
  }

  async function loadInitial() {
    try {
      const data = await GET("api/v1/mqtt");
      markConnection(data.connected ? "MQTT verbonden · alleen lezen" :
        "Ingress actief · MQTT niet verbonden", Boolean(data.connected));
      for (const msg of data.messages || []) addMessage(msg);
    } catch (error) {
      markConnection("Ingress-API niet bereikbaar: " + error.message, false);
    }
  }

  function openStream() {
    if (!window.EventSource) {
      $("live-stream-status").textContent = "Geen EventSource-ondersteuning in browser";
      return;
    }
    stream = new EventSource("api/v1/mqtt/stream?after=" + lastId);
    stream.onopen = () => { $("live-stream-status").textContent = "Read-only MQTT-stream actief"; };
    stream.onmessage = event => {
      try { addMessage(JSON.parse(event.data)); }
      catch (_) { $("live-stream-status").textContent = "Ongeldig bericht ontvangen"; }
    };
    stream.onerror = () => {
      $("live-stream-status").textContent = "Stream herverbindt automatisch";
    };
  }

  async function refreshStatus() {
    try {
      applyStatus(await GET("api/v1/status"));
    } catch (error) {
      markConnection("Geen verbinding met Ingress-backend", false);
      $("live-snapshot-time").textContent = "Backend niet bereikbaar; geen actuele status";
    }
  }

  async function refreshEvents() {
    try { showEvents(await GET("api/v1/events")); }
    catch (_) { $("live-events").textContent = "Backend-gebeurtenissen niet beschikbaar"; }
  }

  async function init() {
    if (window.VaillantMqttViewer) window.VaillantMqttViewer.setLive();
    $("live-mode-label").textContent = "HA Ingress · read-only backend";
    $("terminal-live-caption").textContent = "Ingress · read-only ebusd-cacheterminal";
    $("live-footer").textContent = "HA Ingress · read-only backend · geen ketelsturing";
    if (window.VaillantTerminalRefresh) window.VaillantTerminalRefresh();
    $("live-stream-status").textContent = "MQTT-stream verbinden…";
    await Promise.all([refreshStatus(), refreshEvents(), loadInitial()]);
    openStream();
    window.setInterval(refreshStatus, 5000);
    window.setInterval(refreshEvents, 10000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
