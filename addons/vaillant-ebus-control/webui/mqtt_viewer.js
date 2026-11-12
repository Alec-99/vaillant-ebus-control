/* Frontend-only MQTT Explorer mock. No broker, REST, storage or network I/O.
 * Only synthetic messages, deliberately limited and non-persistent.
 */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const MAX_MESSAGES = 200;
  const VIEW_LIMIT = 100;
  const DEMO = [
    { topic: "vaillant_ebus/v1/availability", value: "online", qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/climate/mode", value: "heat", qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/climate/temperature", value: "21.5", qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/climate/current_temperature", value: "18.2", qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/weather/outdoor", value: "6.0", qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/heatcurve/desired_flow_c", value: "46.7", qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/runtime", value: JSON.stringify({ controller: "monitor", simulated_demand: true, simulated_flow_c: 46.7, write_enabled: false, ebusd_bus_enabled: false, reason: "simulated-heat-request" }), qos: 1, retain: true },
    { topic: "vaillant_ebus/v1/state/climate/action", value: "off", qos: 1, retain: true },
    { topic: "ebusd/bai/FlowTemp", value: "36.25;ok", qos: 0, retain: false },
    { topic: "ebusd/bai/ReturnTemp", value: "31.50;ok", qos: 0, retain: false },
    { topic: "ebusd/bai/Flame", value: "off", qos: 0, retain: false },
    { topic: "ebusd/bai/WP", value: "on", qos: 0, retain: false }
  ];
  let messages = [];
  let selectedId = null;
  let nextId = 1;
  let tick = 0;
  let paused = false;
  let live = false;
  let brokerConnected = false;
  let latestServerId = 0;
  let expansion = new Set(["vaillant_ebus", "vaillant_ebus/v1", "vaillant_ebus/v1/state", "ebusd"]);
  let firstTreeRender = true;

  function validFilter(filter) {
    if (!filter || filter.length > 180) return false;
    const levels = filter.split("/");
    return levels.every((segment, index) =>
      (segment === "#" ? index === levels.length - 1 :
       segment === "+" || (!segment.includes("#") && !segment.includes("+"))));
  }
  function matches(topic, filter) {
    if (!validFilter(filter)) return false;
    const left = topic.split("/");
    const right = filter.split("/");
    let i = 0;
    for (; i < right.length; i++) {
      if (right[i] === "#") return true;
      if (i >= left.length || (right[i] !== "+" && right[i] !== left[i])) return false;
    }
    return i === left.length;
  }
  function topicPreview(value) {
    return value.length > 85 ? value.slice(0, 82) + "…" : value;
  }
  function timeLabel(stamp) {
    return new Date(stamp).toLocaleTimeString("nl-BE", { hour12: false });
  }
  function appendDemo(source, stamp = Date.now()) {
    const item = { id: nextId++, topic: source.topic, payload: String(source.value),
                   qos: source.qos, retained: source.retain, timestamp: stamp };
    messages.unshift(item);
    if (messages.length > MAX_MESSAGES) messages.length = MAX_MESSAGES;
    refresh();
  }
  function create(tag, cls, value) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function filterMessages() {
    const filter = $("mqtt-filter").value.trim();
    const query = $("mqtt-search").value.trim().toLocaleLowerCase();
    const valid = validFilter(filter);
    $("mqtt-filter-error").textContent = valid ? "" : "Ongeldig topicfilter. Gebruik volledige niveaus, + voor één niveau of # alleen op het einde.";
    return valid ? messages.filter(item =>
      matches(item.topic, filter) &&
      (!query || (item.topic + " " + item.payload).toLocaleLowerCase().includes(query))) : [];
  }
  function renderFeed(list) {
    const feed = $("mqtt-feed");
    feed.textContent = "";
    $("mqtt-visible-count").textContent = "(" + list.length + " zichtbaar)";
    if (!list.length) {
      feed.appendChild(create("p", "mqtt-empty", "Geen berichten voor dit filter."));
      return;
    }
    for (const item of list.slice(0, VIEW_LIMIT)) {
      const row = create("button", "mqtt-message" + (item.id === selectedId ? " selected" : ""));
      row.type = "button";
      row.setAttribute("role", "listitem");
      row.setAttribute("aria-label", "Bericht " + item.topic + " om " + timeLabel(item.timestamp));
      row.appendChild(create("span", "mqtt-message-time", timeLabel(item.timestamp)));
      row.appendChild(create("span", "mqtt-message-topic", item.topic));
      row.appendChild(create("span", "mqtt-message-flags", "Q" + item.qos + (item.retained ? " · R" : "")));
      row.appendChild(create("span", "mqtt-message-value", topicPreview(item.payload)));
      row.addEventListener("click", () => { selectedId = item.id; renderFeed(list); renderDetails(item); });
      feed.appendChild(row);
    }
  }
  function renderDetails(item) {
    if (!item) {
      $("mqtt-detail-heading").textContent = "Selecteer een bericht";
      $("mqtt-detail-type").textContent = live ? "READ-ONLY" : "DEMO";
      $("mqtt-detail-meta").textContent = "Geen bericht geselecteerd.";
      $("mqtt-detail-payload").textContent = "Geen bericht geselecteerd.";
      return;
    }
    $("mqtt-detail-heading").textContent = item.topic;
    $("mqtt-detail-meta").textContent = new Date(item.timestamp).toLocaleString("nl-BE") +
      " · QoS " + item.qos + " · Retained: " + (item.retained ? "ja" : "nee") +
      " · " + item.payload.length + " tekens · " + (live ? "MQTT ontvangen (fysieke meettijd onbekend)" : "fictieve bron");
    let formatted = item.payload;
    let isJson = false;
    try {
      const parsed = JSON.parse(item.payload);
      if (typeof parsed === "object" && parsed !== null) {
        formatted = JSON.stringify(parsed, null, 2);
        isJson = true;
      }
    } catch (_) { /* ordinary text payload */ }
    $("mqtt-detail-type").textContent = (isJson ? "JSON" : "TEKST") + (live ? " · MQTT" : " · DEMO");
    // Use textContent: MQTT payloads are untrusted text, never parsed as HTML.
    $("mqtt-detail-payload").textContent = formatted;
  }
  function renderTree() {
    const container = $("mqtt-tree");
    if (!firstTreeRender) {
      expansion = new Set([...container.querySelectorAll("details[data-mqtt-branch][open]")].map(node => node.dataset.mqttBranch));
    }
    container.textContent = "";
    const root = { children: new Map(), count: 0 };
    const latestByTopic = new Set();
    for (const item of messages) {
      const segments = item.topic.split("/");
      let node = root;
      node.count++;
      let path = "";
      for (const label of segments) {
        path += (path ? "/" : "") + label;
        if (!node.children.has(label)) node.children.set(label, { children: new Map(), count: 0, path });
        node = node.children.get(label);
        node.count++;
      }
      latestByTopic.add(item.topic);
    }
    const allButton = create("button", "mqtt-tree-all", (live ? "Alle toegestane topics (#) · " : "Alle demo-topics (#) · ") + latestByTopic.size);
    allButton.type = "button";
    allButton.addEventListener("click", () => pickFilter("#"));
    container.appendChild(allButton);
    function addChildren(parent, branch, depth) {
      for (const [label, child] of [...branch.children.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
        if (child.children.size) {
          const details = document.createElement("details");
          details.dataset.mqttBranch = child.path;
          details.open = expansion.has(child.path);
          const summary = document.createElement("summary");
          const button = create("button", "mqtt-tree-select", label);
          button.type = "button";
          button.title = child.path + "/#";
          button.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            pickFilter(child.path + "/#");
          });
          summary.appendChild(button);
          summary.appendChild(create("small", "mqtt-tree-count", String(child.count)));
          details.appendChild(summary);
          const children = create("div", "mqtt-tree-children");
          addChildren(children, child, depth + 1);
          details.appendChild(children);
          parent.appendChild(details);
        } else {
          const leaf = create("button", "mqtt-tree-leaf");
          leaf.type = "button";
          leaf.title = child.path;
          leaf.appendChild(create("span", "", label));
          leaf.appendChild(create("small", "mqtt-tree-count", String(child.count)));
          leaf.addEventListener("click", () => pickFilter(child.path));
          parent.appendChild(leaf);
        }
      }
    }
    addChildren(container, root, 0);
    firstTreeRender = false;
  }
  function refresh() {
    const visible = filterMessages();
    const topics = new Set(messages.map(item => item.topic));
    $("mqtt-count").textContent = String(messages.length);
    $("mqtt-topics").textContent = String(topics.size);
    $("mqtt-stream-status").textContent = paused ? "Gepauzeerd" : live ? (brokerConnected ? "MQTT gekoppeld" : "MQTT offline") : "Demo actief";
    $("mqtt-pause").textContent = paused ? "Hervatten" : "Pauzeren";
    if (selectedId !== null && !messages.some(item => item.id === selectedId)) selectedId = null;
    renderTree();
    renderFeed(visible);
    // A filtered-out message is no longer shown in the detail pane.
    renderDetails(visible.find(item => item.id === selectedId) || null);
  }
  function pickFilter(filter) {
    $("mqtt-filter").value = filter;
    $("mqtt-search").value = "";
    refresh();
  }

  $("mqtt-filter").addEventListener("input", refresh);
  $("mqtt-search").addEventListener("input", refresh);
  $("mqtt-pause").addEventListener("click", () => { paused = !paused; refresh(); });
  $("mqtt-clear").addEventListener("click", () => {
    messages = []; selectedId = null; refresh();
  });
  document.querySelectorAll("[data-mqtt-filter]").forEach(button =>
    button.addEventListener("click", () => pickFilter(button.dataset.mqttFilter)));

  // The server-side Ingress adapter can switch this viewer from demo to
  // broker-observed messages; the browser itself has no MQTT credentials.
  function setLive() {
    live = true;
    paused = false;
    messages = [];
    selectedId = null;
    latestServerId = 0;
    $("mqtt-live-caption").textContent = "Ingress · brokerberichten · alleen lezen";
    $("mqtt-live-description").textContent =
      "Read-only MQTT-berichten uit toegestane ketel- en controller-topics. "
      + "Ontvangsttijd is niet automatisch de fysieke eBUS-meettijd.";
    $("mqtt-broker-connection").textContent = "Verbinden…";
    refresh();
  }
  function setConnection(connected) {
    brokerConnected = Boolean(connected);
    if (live) {
      $("mqtt-broker-connection").textContent = brokerConnected
        ? "Broker verbonden via backend" : "Broker niet verbonden";
      refresh();
    }
  }
  function appendLive(item) {
    if (!live || !item || !Number.isInteger(item.id) || item.id <= latestServerId) return;
    latestServerId = item.id;
    if (paused) return;
    messages.unshift({
      id: item.id, topic: String(item.topic), payload: String(item.payload),
      qos: Number(item.qos) || 0, retained: Boolean(item.retained),
      timestamp: Date.parse(item.timestamp) || Date.now()
    });
    if (messages.length > MAX_MESSAGES) messages.length = MAX_MESSAGES;
    refresh();
  }
  window.VaillantMqttViewer = {setLive, setConnection, appendLive};

  const now = Date.now();
  DEMO.forEach((sample, index) => appendDemo(sample, now - (DEMO.length - index) * 2400));
  // Low-cost fake stream only while this tab is open; no external subscription.
  window.setInterval(() => {
    if (live || paused || $("panel-mqtt").hidden) return;
    tick++;
    const source = DEMO[tick % DEMO.length];
    let next = source;
    if (source.topic.endsWith("current_temperature")) {
      next = { ...source, value: (18.1 + (tick % 14) / 10).toFixed(1) };
    } else if (source.topic.endsWith("FlowTemp")) {
      next = { ...source, value: (33.7 + (tick % 19) / 10).toFixed(2) + ";ok" };
    } else if (source.topic.endsWith("runtime")) {
      next = { ...source, value: JSON.stringify({ controller: "monitor", simulated_demand: true,
        simulated_flow_c: 46.7, reason: "simulated-heat-request", write_enabled: false, ebusd_bus_enabled: false }) };
    }
    appendDemo(next);
  }, 1600);
})();
