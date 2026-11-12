/* Vaillant eBUS Control — UI-only prototype.
 * No fetch, WebSocket, MQTT, REST requests, localStorage or boiler writes.
 * Future REST adapter should replace the demo data boundary, not the UI view.
 */
(() => {
  "use strict";
  const TAB_META = {
    overview: ["Overzicht", "SYSTEEMOVERZICHT", "Jouw verwarmingsregeling", "Een centraal overzicht van de virtuele thermostaat en de eBUS-status."],
    climate: ["Thermostaat", "VIRTUELE THERMOSTAAT", "Regel jouw comfort", "Pas de simulatie aan zonder commando's naar de ketel te verzenden."],
    curve: ["Stooklijn", "WEERSAFHANKELIJKE REGELING", "De stooklijn", "Verken de invloed van buiten- en kamertemperatuur op de berekende aanvoer."],
    diagnostics: ["Diagnostiek", "SYNTHETISCHE VOORBEELDEN", "Keteldiagnostiek", "Voorbeeldgegevens uit eerdere metingen — niet live uit de eBUS-adapter."],
    events: ["Gebeurtenissen", "LOKALE ACTIVITEIT", "Gebeurtenissen", "Alleen gebeurtenissen van dit HTML-prototype, geen echte applicatielogs."],
    mqtt: ["MQTT Debugger", "BERICHTEN EN TOPICS", "MQTT-berichten bekijken", "Een lichte read-only MQTT Explorer met topicboom, filters en payloadinspectie (alleen demo)."],
    terminal: ["Terminal", "EBUSD EN CONTAINER", "Diagnostische terminal", "Probeer de terminalweergave met voorbeeldcommando\u0027s; er wordt niets in een container uitgevoerd."],
    settings: ["Instellingen", "FRONTEND PROTOTYPE", "Interface en integratie", "De toekomstige REST-koppeling volgt pas wanneer de schermindeling vastligt."]
  };
  const DEFAULTS = Object.freeze({
    mode: "heat", target: 21.5, room: 18.2, outdoor: 6,
    roomValid: true, outdoorValid: true,
    slope: 1.2, kp: 2.0, ki: 0, flowMin: 30, flowMax: 65
  });
  let state = { ...DEFAULTS };
  // Only demo records, grouped by intended use. Actual Home Assistant may not
  // reliably label indoor/outdoor; backend discovery must filter temperature
  // entities and let the user choose the role without hiding valid devices.
  const DEMO_SENSORS = Object.freeze({
    room: [
      { id: "sensor.example_living_room_temperature", label: "Woonkamer · temperatuur", value: 18.2 },
      { id: "sensor.example_dining_room_temperature", label: "Eetkamer · temperatuur", value: 20.8 },
      { id: "sensor.example_bedroom_temperature", label: "Slaapkamer · temperatuur", value: 19.4 },
      { id: "sensor.example_study_temperature", label: "Studeerkamer · temperatuur", value: 19.9 }
    ],
    outdoor: [
      { id: "sensor.example_outdoor_weather_temperature", label: "Weerstation · buitentemperatuur", value: 6.0 },
      { id: "sensor.example_garden_temperature", label: "Tuinsensor · temperatuur", value: 8.2 },
      { id: "sensor.example_weather_temperature", label: "Weerintegratie · temperatuur", value: 8.7 }
    ]
  });
  const DEFAULT_SENSOR_CHOICE = Object.freeze({ room: DEMO_SENSORS.room[0].id, outdoor: DEMO_SENSORS.outdoor[0].id });
  let sensorChoice = { ...DEFAULT_SENSOR_CHOICE };
  let openSensorMenu = null;
  let lastDemand = false;
  let activeTab = "overview";
  let events = [];
  const $ = id => document.getElementById(id);
  const format = (value, digits = 1) => Number.isFinite(value)
    ? value.toLocaleString("nl-BE", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "—";
  const bounded = (value, min, max) => Math.max(min, Math.min(max, value));

  function calculate() {
    if (state.mode !== "heat") {
      lastDemand = false;
      return { demand: false, flow: null, reason: "Modus uit" };
    }
    if (!state.roomValid || !state.outdoorValid) {
      lastDemand = false;
      return { demand: false, flow: null, reason: "Sensor ontbreekt of is ongeldig" };
    }
    const delta = state.target - state.room;
    const demand = lastDemand ? state.room < state.target + 0.2 : state.room < state.target - 0.2;
    lastDemand = demand;
    if (!demand) return { demand: false, flow: null, reason: "Doeltemperatuur bereikt" };
    const rawFlow = state.target + state.slope * (state.target - state.outdoor) + state.kp * delta;
    return { demand: true, flow: bounded(rawFlow, state.flowMin, state.flowMax), reason: "Warmtevraag berekend" };
  }
  function flowAtOutdoor(outdoor) {
    const raw = state.target + state.slope * (state.target - outdoor) + state.kp * (state.target - state.room);
    return bounded(raw, state.flowMin, state.flowMax);
  }
  function record(type, description) {
    const time = new Date().toLocaleTimeString("nl-BE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    events.unshift({ time, type, description });
    if (events.length > 80) events.pop();
    renderEvents();
  }
  function renderEvents() {
    const list = $("event-list");
    list.textContent = "";
    if (!events.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Nog geen activiteiten in deze demo.";
      list.appendChild(empty);
      return;
    }
    for (const item of events) {
      const node = document.createElement("div");
      node.className = "event";
      for (const [cls, value] of [["time", item.time], ["tag", item.type], ["description", item.description]]) {
        const span = document.createElement("span");
        span.className = cls;
        span.textContent = value;
        node.appendChild(span);
      }
      list.appendChild(node);
    }
  }
  function renderChart() { window.VaillantCurveDemo.render(state); }
  function render() {
    const decision = calculate();
    const bind = {
      target: format(state.target), room: state.roomValid ? format(state.room) : "—",
      outdoor: state.outdoorValid ? format(state.outdoor) : "—",
      flow: decision.flow === null ? "—" : format(decision.flow),
      mode: state.mode === "heat" ? "Verwarmen" : "Uit",
      demand: decision.demand ? "Ja" : "Nee",
      reason: decision.reason,
      slope: format(state.slope),
      roomValidity: state.roomValid ? "Voorbeeldsensor" : "Ongeldig",
      outdoorValidity: state.outdoorValid ? "Voorbeeldsensor" : "Ongeldig"
    };
    document.querySelectorAll("[data-bind]").forEach(node => {
      node.textContent = bind[node.dataset.bind] ?? "";
    });
    $("room-value").textContent = `${format(state.room)} °C`;
    $("outdoor-value").textContent = `${format(state.outdoor)} °C`;
    $("room-slider").value = state.room;
    $("outdoor-slider").value = state.outdoor;
    $("room-valid").checked = state.roomValid;
    $("outdoor-valid").checked = state.outdoorValid;
    $("climate-reason").textContent = decision.reason + " · geen echte ketelsturing";
    document.querySelectorAll("[data-mode]").forEach(button => {
      const active = button.dataset.mode === state.mode;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const json = {
      source: "frontend-demo", mode: state.mode, target_c: state.target,
      room_c: state.roomValid ? state.room : null,
      outdoor_c: state.outdoorValid ? state.outdoor : null,
      curve: { slope: state.slope, kp: state.kp, ki: state.ki, min_flow_c: state.flowMin, max_flow_c: state.flowMax },
      simulated_demand: decision.demand, desired_flow_c: decision.flow === null ? null : Math.round(decision.flow * 100) / 100,
      reason: decision.reason, controller: "monitor", write_enabled: false,
      bus_enabled: false, backend_connected: false
    };
    $("json-preview").textContent = JSON.stringify(json, null, 2);
    renderChart();
    renderSensorSelection();
  }
  function navigate(name, shouldFocus = false) {
    if (!TAB_META[name]) return;
    activeTab = name;
    document.querySelectorAll("[role=tab]").forEach(button => {
      const active = button.dataset.tab === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
      if (active && shouldFocus) button.focus({ preventScroll: true });
    });
    document.querySelectorAll("[role=tabpanel]").forEach(panel => panel.hidden = panel.id !== `panel-${name}`);
    const [label, eyebrow, heading, subtitle] = TAB_META[name];
    $("breadcrumb").textContent = label;
    $("section-eyebrow").textContent = eyebrow;
    $("page-title").textContent = heading;
    $("page-subtitle").textContent = subtitle;
    if (history.replaceState) {
      try { history.replaceState(null, "", `#${name}`); } catch (_) { /* file:// can reject history */ }
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function resetCurveFields() {
    for (const [id, val] of [["curve-slope", state.slope], ["room-kp", state.kp], ["room-ki", state.ki], ["flow-min", state.flowMin], ["flow-max", state.flowMax]]) $(id).value = val;
  }
  function changeCurve() {
    const values = [$("curve-slope").value, $("room-kp").value, $("room-ki").value, $("flow-min").value, $("flow-max").value].map(Number);
    const [slope, kp, ki, flowMin, flowMax] = values;
    const valid = values.every(Number.isFinite) && slope >= 0 && slope <= 5 && kp >= 0 && kp <= 20 && ki >= 0 && ki <= 1 && flowMin >= 20 && flowMin <= 80 && flowMax >= 20 && flowMax <= 85 && flowMin < flowMax;
    const message = $("curve-error");
    if (!valid) {
      message.textContent = "Controleer de waarden: minimum moet kleiner zijn dan maximum.";
      message.classList.add("error");
      return;
    }
    message.textContent = "De grafiek past zich direct aan. Alleen lokale demo-instellingen.";
    message.classList.remove("error");
    Object.assign(state, { slope, kp, ki, flowMin, flowMax });
    render();
  }
  document.querySelectorAll("[data-tab]").forEach(button => {
    button.addEventListener("click", () => navigate(button.dataset.tab));
    button.addEventListener("keydown", event => {
      const keys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const tabs = Object.keys(TAB_META);
      let idx = tabs.indexOf(button.dataset.tab);
      if (event.key === "Home") idx = 0;
      else if (event.key === "End") idx = tabs.length - 1;
      else idx = (idx + (["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1) + tabs.length) % tabs.length;
      navigate(tabs[idx], true);
    });
  });
  document.querySelectorAll("[data-navigate]").forEach(button => button.addEventListener("click", () => navigate(button.dataset.navigate)));
  $("decrease-target").addEventListener("click", () => { state.target = bounded(Math.round((state.target - 0.5) * 2) / 2, 5, 30); render(); record("Thermostaat", `Doeltemperatuur ingesteld op ${format(state.target)} °C (demo)`); });
  $("increase-target").addEventListener("click", () => { state.target = bounded(Math.round((state.target + 0.5) * 2) / 2, 5, 30); render(); record("Thermostaat", `Doeltemperatuur ingesteld op ${format(state.target)} °C (demo)`); });
  document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => { state.mode = button.dataset.mode; render(); record("Thermostaat", `Modus gewijzigd naar ${state.mode} (demo)`); }));
  for (const [id, key] of [["room-slider", "room"], ["outdoor-slider", "outdoor"]]) {
    $(id).addEventListener("input", event => { state[key] = Number(event.target.value); render(); });
    $(id).addEventListener("change", () => record("Sensor", `${key === "room" ? "Kamer" : "Buiten"} ingesteld op ${format(state[key])} °C (demo)`));
  }
  for (const [id, key] of [["room-valid", "roomValid"], ["outdoor-valid", "outdoorValid"]]) {
    $(id).addEventListener("change", event => { state[key] = event.target.checked; render(); record("Sensor", `${key === "roomValid" ? "Kamer" : "Buiten"}: ${state[key] ? "geldig" : "ongeldig"} (demo)`); });
  }
  for (const id of ["curve-slope", "room-kp", "room-ki", "flow-min", "flow-max"]) {
    $(id).addEventListener("input", changeCurve);
    $(id).addEventListener("change", () => { if (!$("curve-error").classList.contains("error")) record("Stooklijn", "Parameters aangepast (demo)"); });
  }
  $("reset-curve").addEventListener("click", () => { for (const key of ["slope", "kp", "ki", "flowMin", "flowMax"]) state[key] = DEFAULTS[key]; resetCurveFields(); render(); record("Stooklijn", "Standaardparameters hersteld (demo)"); });
  $("reset-all").addEventListener("click", () => { state = { ...DEFAULTS }; sensorChoice = { ...DEFAULT_SENSOR_CHOICE }; closeSensorDropdown(); lastDemand = false; resetCurveFields(); render(); record("Interface", "Volledige demosimulatie gereset"); });
  $("clear-events").addEventListener("click", () => { events = []; renderEvents(); });
  $("copy-state").addEventListener("click", async () => {
    const content = $("json-preview").textContent;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(content);
      record("Interface", "Demo-JSON gekopieerd");
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = content; area.style.position = "fixed"; area.style.opacity = "0";
      document.body.appendChild(area); area.select();
      const ok = document.execCommand("copy"); area.remove();
      record("Interface", ok ? "Demo-JSON gekopieerd" : "Kopiëren niet toegestaan in deze browser");
    }
  });


  // UI-only sensor selector. Search is part of the dropdown, which floats
  // over the layout.  Selections update only the in-browser simulation.
  function getDemoSensor(kind) {
    return DEMO_SENSORS[kind].find(item => item.id === sensorChoice[kind]) || DEMO_SENSORS[kind][0];
  }
  function renderSensorSelection() {
    for (const kind of ["room", "outdoor"]) {
      const chosen = getDemoSensor(kind);
      const valid = state[kind === "room" ? "roomValid" : "outdoorValid"];
      $("sensor-" + kind + "-selected").textContent = chosen.label;
      const availability = $("sensor-" + kind + "-availability");
      availability.textContent = valid ? "✓ Sensor beschikbaar" : "Sensor ongeldig (demo)";
      availability.classList.toggle("invalid", !valid);
      $("sensor-" + kind + "-value").textContent = valid ? format(state[kind]) + " °C" : "—";
    }
  }
  function renderSensorOptions(kind) {
    const list = $("sensor-" + kind + "-options");
    const query = $("sensor-" + kind + "-search").value.trim().toLocaleLowerCase("nl-BE");
    const matches = DEMO_SENSORS[kind].filter(item =>
      (item.label + " " + item.id).toLocaleLowerCase("nl-BE").includes(query));
    list.textContent = "";
    if (!matches.length) {
      const note = document.createElement("div");
      note.className = "sensor-no-match";
      note.textContent = "Geen overeenkomende temperatuursensoren.";
      list.appendChild(note);
    }
    for (const item of matches) {
      const option = document.createElement("button");
      const isSelected = item.id === sensorChoice[kind];
      option.type = "button";
      option.className = "sensor-option";
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(isSelected));
      const content = document.createElement("span");
      content.className = "sensor-option-name";
      content.textContent = item.label;
      const subtitle = document.createElement("small");
      subtitle.className = "sensor-option-id";
      subtitle.textContent = item.id;
      content.appendChild(subtitle);
      option.appendChild(content);
      if (isSelected) {
        const check = document.createElement("span");
        check.className = "sensor-option-check";
        check.textContent = "✓";
        option.appendChild(check);
      }
      option.addEventListener("click", () => {
        sensorChoice[kind] = item.id;
        state[kind] = item.value;
        state[kind === "room" ? "roomValid" : "outdoorValid"] = true;
        closeSensorDropdown();
        render();
        record("Sensor", (kind === "room" ? "Kamersensor" : "Buitensensor") + " gekozen: " + item.label + " (demo)");
      });
      list.appendChild(option);
    }
  }
  function closeSensorDropdown(restoreFocus = false) {
    const last = openSensorMenu;
    for (const kind of ["room", "outdoor"]) {
      $("sensor-" + kind + "-menu").hidden = true;
      $("sensor-" + kind + "-trigger").setAttribute("aria-expanded", "false");
    }
    openSensorMenu = null;
    if (restoreFocus && last) $("sensor-" + last + "-trigger").focus();
  }
  function toggleSensorDropdown(kind) {
    if (openSensorMenu === kind) { closeSensorDropdown(); return; }
    closeSensorDropdown();
    openSensorMenu = kind;
    $("sensor-" + kind + "-menu").hidden = false;
    $("sensor-" + kind + "-trigger").setAttribute("aria-expanded", "true");
    $("sensor-" + kind + "-search").value = "";
    renderSensorOptions(kind);
    $("sensor-" + kind + "-search").focus();
  }
  for (const kind of ["room", "outdoor"]) {
    $("sensor-" + kind + "-trigger").addEventListener("click", () => toggleSensorDropdown(kind));
    const field = $("sensor-" + kind + "-search");
    field.addEventListener("input", () => renderSensorOptions(kind));
    field.addEventListener("keydown", event => {
      if (event.key === "ArrowDown") {
        const first = $("sensor-" + kind + "-options").querySelector("button");
        if (first) { event.preventDefault(); first.focus(); }
      }
    });
    $("sensor-" + kind + "-options").addEventListener("keydown", event => {
      if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
      const list = [...event.currentTarget.querySelectorAll("button")];
      const index = list.indexOf(document.activeElement);
      const next = index + (event.key === "ArrowDown" ? 1 : -1);
      if (list[next]) { event.preventDefault(); list[next].focus(); }
      else if (event.key === "ArrowUp" && index === 0) {
        event.preventDefault(); $("sensor-" + kind + "-search").focus();
      }
    });
  }
  document.addEventListener("pointerdown", event => {
    if (openSensorMenu && !event.target.closest(".sensor-select-wrap")) closeSensorDropdown();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && openSensorMenu) {
      event.preventDefault(); closeSensorDropdown(true);
    }
  });

  // UI-only terminal: no shell execution, no REST, no socket, no eval or fetch.
  let terminalMode = "ebusd";
  const terminalHistory = [];
  let terminalHistoryIndex = 0;
  const TERMINAL_EXAMPLES = Object.freeze({
    "help": "Demo: help, info, state, read -c bai FlowTemp, read -c bai ReturnTemp, read -c bai Flame, read -c bai WP, clear, history.",
    "info": "VOORBEELD (geen echte daemon): ebusd 26.1 · adapter: niet verbonden · controller: monitor-only",
    "state": "VOORBEELD (geen echte daemon): signal = unknown, adapter = disabled, writes = disabled",
    "read -c bai FlowTemp": "HISTORISCHE VOORBEELDMETING: 36.25;ok °C (niet live)",
    "read -c bai ReturnTemp": "HISTORISCHE VOORBEELDMETING: 31.50;ok °C (niet live)",
    "read -c bai Flame": "SYNTHETISCH VOORBEELD: off (niet live)",
    "read -c bai WP": "SYNTHETISCH VOORBEELD: on (niet live)"
  });
  function addTerminalLine(value, kind = "reply") {
    const log = $("terminal-output");
    const line = document.createElement("div");
    line.className = "terminal-line terminal-" + kind;
    line.textContent = value;
    log.appendChild(line);
    while (log.children.length > 120) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
  }
  function resetTerminalScreen() {
    $("terminal-output").textContent = "";
    addTerminalLine(window.VaillantLive?.enabled ? "Vaillant eBUS Control · HA Ingress read-only" : "Vaillant eBUS Control · frontendprototype", "banner");
    addTerminalLine(terminalMode === "ebusd"
      ? window.VaillantLive?.enabled
        ? "Read-only cacheterminal via Ingress. Alleen exact toegestane BAI-lezingen; geen writes of shell."
        : "ebusd-console: type 'help' om demonstratiecommando's te zien. Geen verbinding."
      : "Containershell: gereserveerd voor latere Ingress/WebSocket-integratie; niet beschikbaar.", "comment");
  }
  function chooseTerminalMode(mode) {
    if (!["ebusd", "shell"].includes(mode)) return;
    terminalMode = mode;
    document.querySelectorAll("[data-terminal-mode]").forEach(button => {
      const active = button.dataset.terminalMode === mode;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const locked = mode === "shell";
    $("terminal-input").disabled = locked;
    $("terminal-run").disabled = locked;
    $("terminal-presets").hidden = locked;
    $("terminal-prompt").textContent = locked ? "container$" : "ebusd>";
    $("terminal-description").textContent = locked
      ? "Ontwerp voor een toekomstige interactieve containershell. Hiervoor zijn WebSocket/PTY, expliciete inschakeling en beheerderstoegang nodig. Nu is deze modus volledig uitgeschakeld."
      : window.VaillantLive?.enabled
        ? "Ingelogde Ingress-terminal: uitsluitend toegestane cache-uitlezingen. Cacheversheid is niet bewezen."
        : "Voorbeeld van de ebusd-tekstinterface via localhost TCP. De uitvoer is uitsluitend demonstratiedata.";
    resetTerminalScreen();
  }
  function submitTerminalCommand(command) {
    if (terminalMode !== "ebusd") return;
    const text = command.trim();
    if (!text) return;
    terminalHistory.push(text);
    terminalHistoryIndex = terminalHistory.length;
    if (text === "clear") { resetTerminalScreen(); return; }
    addTerminalLine("ebusd> " + text, "command");
    if (text === "history") {
      addTerminalLine(terminalHistory.map((line, idx) => String(idx + 1) + "  " + line).join("\n"));
    } else if (window.VaillantLive?.enabled) {
      // A narrow allowlisted cache-reading API; never evaluate typed text or
      // execute commands in a container shell.
      window.VaillantLive.readCommand(text)
        .then(reply => addTerminalLine(reply, "reply"))
        .catch(error => addTerminalLine("GEWEIGERD: " + error.message, "reply"));
    } else {
      addTerminalLine(Object.prototype.hasOwnProperty.call(TERMINAL_EXAMPLES, text)
        ? TERMINAL_EXAMPLES[text]
        : "NIET UITGEVOERD: dit is alleen een UI-demo. Gebruik 'help' voor voorbeeldcommando's.", "reply");
    }
    $("terminal-input").value = "";
  }
  document.querySelectorAll("[data-terminal-mode]").forEach(button =>
    button.addEventListener("click", () => chooseTerminalMode(button.dataset.terminalMode)));
  document.querySelectorAll("[data-terminal-command]").forEach(button =>
    button.addEventListener("click", () => submitTerminalCommand(button.dataset.terminalCommand)));
  $("terminal-form").addEventListener("submit", event => {
    event.preventDefault();
    submitTerminalCommand($("terminal-input").value);
  });
  $("terminal-input").addEventListener("keydown", event => {
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      terminalHistoryIndex = bounded(terminalHistoryIndex + (event.key === "ArrowUp" ? -1 : 1), 0, terminalHistory.length);
      $("terminal-input").value = terminalHistory[terminalHistoryIndex] || "";
    }
  });
  $("terminal-clear").addEventListener("click", resetTerminalScreen);
  resetTerminalScreen();
  window.VaillantTerminalRefresh = () => chooseTerminalMode(terminalMode);
  window.VaillantCurveDemo.init({
    getState: () => state,
    getRoomDemand: () => calculate().demand,
    setOutdoor: value => { state.outdoor = value; render(); },
    record
  });

  render();
  record("Demo", "UI-prototype geladen · geen backendverbinding");
  const hash = decodeURIComponent(location.hash.slice(1));
  navigate(TAB_META[hash] ? hash : "overview");
})();
