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
      main { margin: auto; max-width: 76rem; padding: 1rem; }
      .filter-card { display: block; padding: 1rem; margin: .75rem 0; }
      .filters { align-items: end; }
      .timeline { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
        gap: .75rem; align-items: start; }
      .entry-card { display: block; padding: 1rem; min-width: 0; }
      .entry-title { display: flex; align-items: center; gap: .55rem; }
      .entry-title ha-icon { color: var(--primary-color); --mdc-icon-size: 20px; }
      .entry-location { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
      header, .filters, .actions { display: flex; flex-wrap: wrap; align-items: center; gap: .8rem; }
      h1 { font-size: 1.6rem; margin: .5rem 0; }
      h2 { font-size: 1.15rem; margin: 0 0 .5rem; }
      form { margin: .8rem 0; padding: 1rem; border-radius: var(--ha-card-border-radius, 12px);
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
      p:empty { display: none; }
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

    this.status = element("p");
    this.status.setAttribute("role", "status");
    this.error = element("p");
    this.error.setAttribute("role", "alert");
    filters.append(vehicleLabel, dayLabel, this.button(this.t("Refresh", "Aktualisieren"), () => this.load()));
    const filterCard = element("ha-card");
    filterCard.className = "filter-card";
    filterCard.append(filters);
    this.rows = element("section");
    this.rows.className = "timeline";
    this.main.append(header, filterCard, this.status, this.error, this.rows);
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
    this.rows.replaceChildren();
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
    const card = element("ha-card");
    card.className = "entry-card";
    const labels = {
      trip: this.t("Drive", "Fahrt"),
      charge: this.t("Charge", "Ladung"),
      pause: this.t("Stop", "Pause"),
    };
    const timeZone = this._hass.config.time_zone;
    const time = new Intl.DateTimeFormat(this.lang, { timeStyle: "short", timeZone }).format(new Date(row.start_time));
    const heading = element("h2");
    heading.className = "entry-title";
    const icon = element("ha-icon");
    icon.setAttribute("icon", { trip: "mdi:car", charge: "mdi:ev-station", pause: "mdi:pause-circle-outline" }[row.type]);
    heading.append(icon, document.createTextNode(`${time} · ${labels[row.type]}`));
    card.append(heading);
    const details = row.details ?? {};
    const parts = [
      details.title,
      details.category,
      row.distance_km == null ? null : `${row.distance_km} km`,
      row.energy_kwh == null ? null : `${row.energy_kwh} kWh`,
      row.duration_seconds == null ? null : this.duration(row.duration_seconds),
      (details.cost_total ?? row.cost_total) == null ? null
        : `${details.cost_total ?? row.cost_total} ${details.currency ?? row.currency ?? ""}`,
    ].filter(Boolean);
    if (parts.length) card.append(element("p", parts.join(" · ")));
    const location = details.location || row.location || row.detected_location;
    if (location) {
      const line = element("p", location);
      line.className = "entry-location";
      line.title = location;
      card.append(line);
    }
    for (const receipt of row.receipts ?? []) {
      card.append(this.button(receipt.name, () => this.downloadReceipt(receipt)));
    }
    if (details.note || row.note) card.append(element("p", details.note || row.note));
    if (row.charge_id || row.pause_id) {
      const label = row.charge_id ? this.t("Costs and receipts", "Kosten und Belege") : this.t("Edit", "Bearbeiten");
      card.append(this.button(label, () => this.editRow(row, card)));
    }
    return card;
  }

  duration(seconds) {
    const minutes = Math.round(seconds / 60);
    const hours = Math.floor(minutes / 60);
    return hours ? `${hours} ${this.t("hr", "Std.")} ${minutes % 60} min` : `${minutes} min`;
  }

  async downloadReceipt(receipt) {
    try {
      const response = await this._hass.fetchWithAuth(`/api/ford_triplog/receipts/${encodeURIComponent(receipt.id)}`);
      if (!response.ok) throw new Error(this.t("Could not open receipt.", "Beleg konnte nicht geöffnet werden."));
      const url = URL.createObjectURL(await response.blob());
      const link = element("a");
      link.href = url;
      link.download = receipt.name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) {
      this.error.textContent = error.message ?? String(error);
    }
  }

  async attachReceipt(entry_id, charge_id, file) {
    const body = new FormData();
    body.append("file", file);
    const response = await this._hass.fetchWithAuth("/api/file_upload", { method: "POST", body });
    if (!response.ok) throw new Error(this.t("Receipt upload failed.", "Beleg konnte nicht hochgeladen werden."));
    const { file_id } = await response.json();
    await this._hass.callWS({ type: "ford_triplog/logbook/attach_receipt", entry_id, charge_id, file_id });
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
        const file = values.get("receipt");
        if (total !== String(row.cost_total ?? "") || currency !== (row.currency ?? "")) {
          await this._hass.callWS({
            type: "ford_triplog/logbook/edit_charge", ...data, charge_id: row.charge_id,
            cost_total: total === "" ? null : Number(total), currency: currency || null,
          });
          row.cost_total = total === "" ? null : Number(total);
          row.currency = currency;
        }
        if (file?.size) await this.attachReceipt(entry_id, row.charge_id, file);
      }
    });
    if (row.pause_id) {
      field(form, "title", this.t("Title", "Titel"), "text", details.title);
      field(form, "category", this.t("Category", "Kategorie"), "text", details.category);
      const location = field(form, "location", this.t("Location", "Ort"), "text", details.location);
      location.maxLength = 200;
      location.placeholder = row.detected_location ?? "";
      field(form, "note", this.t("Note", "Notiz"), "text", details.note).maxLength = 2000;
    } else {
      field(form, "receipt", this.t("Attach receipt", "Beleg anhängen"), "file").accept = ".pdf,.jpg,.jpeg,.png,.webp";
    }
    field(form, "cost_total", this.t("Total cost", "Gesamtkosten"), "number", details.cost_total);
    field(form, "currency", this.t("Currency", "Währung"), "text", details.currency).maxLength = 3;
    finish();
  }
}

if (!customElements.get(elementName)) customElements.define(elementName, FordTriplogLogbook);
