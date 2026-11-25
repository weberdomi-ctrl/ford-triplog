const elementName = "ford-triplog-logbook";

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function field(form, name, label, type, value = "") {
  const wrapper = element("label", label);
  const input = element("input");
  input.name = name;
  input.type = type;
  input.value = value ?? "";
  if (type === "number") {
    input.min = "0";
    input.step = "any";
  }
  wrapper.append(input);
  form.append(wrapper);
  return input;
}

class FordTriplogLogbook extends HTMLElement {
  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this.main) this.start();
  }

  set narrow(value) {
    this._narrow = value;
    if (this.menu) this.menu.narrow = value;
  }

  connectedCallback() {
    if (this._hass && !this.main) this.start();
  }

  start() {
    this.lang = this._hass.language?.startsWith("de") ? "de" : "en";
    const root = this.attachShadow({ mode: "open" });
    const style = element("style");
    style.textContent = `
      :host { display: block; min-height: 100%; color: var(--primary-text-color);
        background: var(--lovelace-background, var(--primary-background-color)); }
      main { margin: auto; max-width: 54rem; padding: 1rem; }
      header, .filters, .actions { display: flex; flex-wrap: wrap; align-items: center; gap: .8rem; }
      h1 { font-size: 1.6rem; margin: .5rem 0; }
      h2 { font-size: 1.15rem; margin: 0 0 .5rem; }
      article, form { margin: .8rem 0; padding: 1rem; border-radius: var(--ha-card-border-radius, 12px);
        background: var(--card-background-color); border: 1px solid var(--divider-color); }
      form { display: grid; gap: .75rem; }
      label { display: grid; gap: .25rem; }
      input, select, button { box-sizing: border-box; font: inherit; color: inherit;
        border: 1px solid var(--divider-color); border-radius: 6px; padding: .5rem;
        background: var(--card-background-color); }
      button { cursor: pointer; } button:disabled { cursor: default; opacity: .6; }
      .primary { color: var(--text-primary-color, white); background: var(--primary-color); }
      p { white-space: pre-wrap; margin: .4rem 0; }
      [role=alert] { color: var(--error-color); }
    `;
    this.main = element("main");
    const header = element("header");
    this.menu = element("ha-menu-button");
    this.menu.hass = this._hass;
    this.menu.narrow = this._narrow;
    header.append(this.menu, element("h1", "Triplog"));

    const filters = element("div");
    filters.className = "filters";
    const vehicleLabel = element("label", this.t("Vehicle", "Fahrzeug"));
    this.vehicle = element("select");
    vehicleLabel.append(this.vehicle);
    const dayLabel = element("label", this.t("Date", "Datum"));
    this.day = element("input");
    this.day.type = "date";
    dayLabel.append(this.day);
    this.vehicle.addEventListener("change", () => this.load());
    this.day.addEventListener("change", () => { if (this.day.value) this.load(); });
    this.add = this.button(this.t("Add charge", "Ladung nachtragen"), () => this.addCharge());
    this.add.disabled = true;
    filters.append(vehicleLabel, dayLabel, this.button(this.t("Refresh", "Aktualisieren"), () => this.load()), this.add);

    this.status = element("p");
    this.status.setAttribute("role", "status");
    this.error = element("p");
    this.error.setAttribute("role", "alert");
    this.editor = element("section");
    this.rows = element("section");
    this.main.append(header, filters, this.status, this.error, this.editor, this.rows);
    root.append(style, this.main);
    this.load();
  }

  t(english, german) {
    return this.lang === "de" ? german : english;
  }

  button(label, action) {
    const button = element("button", label);
    button.type = "button";
    button.addEventListener("click", action);
    return button;
  }

  async load() {
    const request = Symbol();
    this.request = request;
    this.status.textContent = this.t("Loading…", "Wird geladen…");
    this.error.textContent = "";
    this.editor.replaceChildren();
    this.rows.replaceChildren();
    this.add.disabled = true;
    const query = { type: "ford_triplog/logbook" };
    if (this.vehicle.value) query.entry_id = this.vehicle.value;
    if (this.day.value) query.date = this.day.value;

    try {
      const data = await this._hass.callWS(query);
      if (request !== this.request) return;
      this.vehicle.replaceChildren();
      for (const [id, name] of Object.entries(data.vehicles)) {
        const option = element("option", name);
        option.value = id;
        this.vehicle.append(option);
      }
      this.vehicle.value = data.entry_id ?? "";
      this.day.value = data.date;
      this.add.disabled = !data.entry_id;
      this.status.textContent = data.rows.length ? "" : this.t("No entries for this date.", "Keine Einträge an diesem Tag.");
      for (const row of data.rows) this.rows.append(this.renderRow(row));
    } catch (error) {
      if (request !== this.request) return;
      this.status.textContent = "";
      this.error.textContent = error.message ?? String(error);
      if (error.code === "not_found") this.vehicle.replaceChildren();
    }
  }

  renderRow(row) {
    const card = element("article");
    const labels = {
      trip: this.t("Drive", "Fahrt"),
      charge: this.t("Charge", "Ladung"),
      pause: this.t("Stop", "Pause"),
    };
    const timeZone = this._hass.config.time_zone;
    const time = new Intl.DateTimeFormat(this.lang, { timeStyle: "short", timeZone }).format(new Date(row.start_time));
    card.append(element("h2", `${time} · ${labels[row.type]}`));
    const details = row.details ?? {};
    const parts = [
      details.title,
      details.category,
      details.location || row.location || row.detected_location,
      row.distance_km == null ? null : `${row.distance_km} km`,
      row.energy_kwh == null ? null : `${row.energy_kwh} kWh`,
      row.duration_seconds == null ? null : `${Math.round(row.duration_seconds / 60)} min`,
      (details.cost_total ?? row.cost_total) == null ? null
        : `${details.cost_total ?? row.cost_total} ${details.currency ?? row.currency ?? ""}`,
    ].filter(Boolean);
    if (parts.length) card.append(element("p", parts.join(" · ")));
    if (details.note || row.note) card.append(element("p", details.note || row.note));
    if (row.charge_id || row.pause_id) {
      card.append(this.button(this.t("Edit", "Bearbeiten"), () => this.editRow(row, card)));
    }
    return card;
  }

  form(container, title, save) {
    const form = element("form");
    form.append(element("h2", title));
    const error = element("p");
    error.setAttribute("role", "alert");
    const actions = element("div");
    actions.className = "actions";
    const submit = element("button", this.t("Save", "Speichern"));
    submit.className = "primary";
    const cancel = this.button(this.t("Cancel", "Abbrechen"), () => form.remove());
    actions.append(submit, cancel);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      cancel.disabled = true;
      error.textContent = "";
      try {
        await save(new FormData(form));
        await this.load();
      } catch (reason) {
        error.textContent = reason.message ?? String(reason);
        submit.disabled = false;
        cancel.disabled = false;
      }
    });
    container.querySelector("form")?.remove();
    container.append(form);
    return { form, finish: () => {
      form.append(actions, error);
      form.querySelector("input")?.focus();
    } };
  }

  editRow(row, card) {
    const entry_id = this.vehicle.value;
    const details = row.details ?? row;
    const data = { entry_id };
    const { form, finish } = this.form(card, this.t("Edit entry", "Eintrag bearbeiten"), async (values) => {
      const total = values.get("cost_total");
      const currency = values.get("currency").trim().toUpperCase();
      if (total !== "" && !/^[A-Z]{3}$/.test(currency)) {
        throw new Error(this.t("Enter a three-letter currency.", "Währung mit drei Buchstaben eingeben."));
      }
      if (row.pause_id) {
        await this._hass.callService("ford_triplog", "edit_pause", {
          ...data, journey_id: row.journey_id, pause_id: row.pause_id,
          title: values.get("title"), category: values.get("category"),
          location: values.get("location"), note: values.get("note"),
          cost_total: total === "" ? null : Number(total), currency: currency || null,
        });
      } else {
        await this._hass.callWS({
          type: "ford_triplog/logbook/edit_charge", ...data, charge_id: row.charge_id,
          location: values.get("location"), note: values.get("note"),
          ...(total !== String(row.cost_total ?? "") || currency !== (row.currency ?? "")
            ? { cost_total: total === "" ? null : Number(total), currency: currency || null }
            : {}),
        });
      }
    });
    if (row.pause_id) {
      field(form, "title", this.t("Title", "Titel"), "text", details.title);
      field(form, "category", this.t("Category", "Kategorie"), "text", details.category);
    }
    const location = field(form, "location", this.t("Location", "Ort"), "text", details.location);
    location.maxLength = 200;
    location.placeholder = row.detected_location ?? "";
    field(form, "note", this.t("Note", "Notiz"), "text", details.note).maxLength = 2000;
    field(form, "cost_total", this.t("Total cost", "Gesamtkosten"), "number", details.cost_total);
    field(form, "currency", this.t("Currency", "Währung"), "text", details.currency).maxLength = 3;
    finish();
  }

  addCharge() {
    const entry_id = this.vehicle.value;
    const random = crypto.getRandomValues(new Uint8Array(16));
    const charge_id = "manual_" + Array.from(random, (byte) => byte.toString(16).padStart(2, "0")).join("");
    const selectedDay = this.day.value;
    const zone = this._hass.config.time_zone;
    const { form, finish } = this.form(this.editor, this.t("Add a completed charge", "Abgeschlossene Ladung nachtragen"), async (values) => {
      const total = values.get("cost_total");
      const currency = values.get("currency").trim().toUpperCase();
      if (total !== "" && !/^[A-Z]{3}$/.test(currency)) {
        throw new Error(this.t("Enter a three-letter currency.", "Währung mit drei Buchstaben eingeben."));
      }
      await this._hass.callWS({
        type: "ford_triplog/logbook/add_charge",
        entry_id, charge_id,
        start_time: values.get("start_time"), end_time: values.get("end_time"),
        energy_kwh: Number(values.get("energy_kwh")),
        location: values.get("location"), note: values.get("note"),
        ...(total === "" ? {} : { cost_total: Number(total), currency }),
      });
      this.day.value = values.get("start_time").slice(0, 10);
    });
    form.append(element("p", `${this.t("Time zone", "Zeitzone")} · ${zone}`));
    field(form, "start_time", this.t("Start", "Beginn"), "datetime-local", `${selectedDay}T12:00`).required = true;
    field(form, "end_time", this.t("End", "Ende"), "datetime-local", `${selectedDay}T13:00`).required = true;
    field(form, "energy_kwh", this.t("Billed energy (kWh)", "Verrechnete Energie (kWh)"), "number").required = true;
    field(form, "location", this.t("Location", "Ort"), "text").maxLength = 200;
    field(form, "note", this.t("Note", "Notiz"), "text").maxLength = 2000;
    field(form, "cost_total", this.t("Total cost", "Gesamtkosten"), "number");
    field(form, "currency", this.t("Currency", "Währung"), "text", this._hass.config.currency).maxLength = 3;
    finish();
  }
}

if (!customElements.get(elementName)) customElements.define(elementName, FordTriplogLogbook);
