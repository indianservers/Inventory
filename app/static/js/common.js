document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("table.datatable").forEach((table) => {
    const wrapper = table.closest(".panel") || table.parentElement;
    const controls = document.createElement("div");
    controls.className = "table-toolbar";
    controls.innerHTML = `<button class="btn btn-sm btn-outline-secondary column-chooser-toggle" type="button" title="Choose columns"><i class="bi bi-gear"></i></button><div class="column-chooser-popover" hidden></div>`;
    wrapper?.insertBefore(controls, table);
    const tableId = table.id || `datatable-${[...document.querySelectorAll("table.datatable")].indexOf(table)}`;
    const pageLengthKey = `vyapara_page_length_${tableId}`;
    const dt = new DataTable(table, {pageLength: Number(localStorage.getItem(pageLengthKey) || 10), lengthMenu: [10, 25, 50, 100], layout: {topStart: "pageLength", topEnd: "search", bottomStart: "info", bottomEnd: "paging"}});
    dt.on("length", (_event, _settings, len) => localStorage.setItem(pageLengthKey, len));
    initColumnChooser(table, dt, controls);
  });
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("click", (event) => {
      if (!confirm(el.dataset.confirm || "Are you sure?")) event.preventDefault();
    });
  });
  document.querySelectorAll(".sidebar a").forEach((link) => {
    if (link.href === window.location.href || (link.pathname !== "/" && window.location.pathname.startsWith(link.pathname))) {
      link.classList.add("active");
    }
  });
  initSidebarState();
  initFavorites();
  initBulkToolbar();
  initStatusBadgeIcons();
  initInlineValidation();
  initScrollTopButton();
  initOfflineBanner();
  initPartyHoverCards();
  initCopyReferenceButtons();
  initDatePresetChips();
  initIndianNumberInputs();
  initContextHelpTooltips();
  initRowContextMenu();
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      document.querySelector(".global-search")?.focus();
    }
  });
  document.querySelector("#theme-toggle")?.addEventListener("click", () => {
    const next = document.body.dataset.theme === "dark" ? "light" : "dark";
    document.cookie = `theme=${next};path=/;max-age=31536000`;
    document.body.dataset.theme = next;
  });
  document.querySelector("#density-toggle")?.addEventListener("click", () => {
    const next = document.body.dataset.density === "compact" ? "comfortable" : "compact";
    document.cookie = `density=${next};path=/;max-age=31536000`;
    document.body.dataset.density = next;
  });
  document.querySelectorAll("form").forEach((form) => {
    let dirty = false;
    form.addEventListener("input", () => dirty = true);
    form.addEventListener("submit", () => dirty = false);
    window.addEventListener("beforeunload", (event) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  });
});

function initScrollTopButton() {
  const button = document.querySelector("#scrollTopButton");
  if (!button) return;
  const update = () => button.classList.toggle("show", window.scrollY > 300);
  button.addEventListener("click", () => window.scrollTo({top: 0, behavior: "smooth"}));
  window.addEventListener("scroll", update, {passive: true});
  update();
}

function initOfflineBanner() {
  const show = () => {
    if (document.querySelector("#offlineStateBanner")) return;
    const banner = document.createElement("div");
    banner.id = "offlineStateBanner";
    banner.className = "offline-state-banner";
    banner.setAttribute("role", "status");
    banner.textContent = "You're offline — changes will sync when reconnected.";
    document.body.prepend(banner);
  };
  const hide = () => document.querySelector("#offlineStateBanner")?.remove();
  window.addEventListener("offline", show);
  window.addEventListener("online", hide);
  if (navigator.onLine === false) show();
}

function initPartyHoverCards() {
  const links = document.querySelectorAll("[data-party-hover]");
  if (!links.length) return;
  const card = document.createElement("div");
  card.className = "party-hover-card";
  card.hidden = true;
  document.body.appendChild(card);
  let timer;
  const show = async (link) => {
    clearTimeout(timer);
    const rect = link.getBoundingClientRect();
    card.style.left = `${Math.min(rect.left + window.scrollX, window.scrollX + window.innerWidth - 280)}px`;
    card.style.top = `${rect.bottom + window.scrollY + 8}px`;
    card.hidden = false;
    card.innerHTML = `<div class="text-muted">Loading party details...</div>`;
    const res = await fetch(`/parties/hover-card/${link.dataset.partyType}/${link.dataset.partyId}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return card.innerHTML = `<strong>Unable to load details</strong>`;
    card.innerHTML = `
      <strong>${escapeHtml(data.name)}</strong>
      <div><span>Outstanding</span><b>${Number(data.outstanding || 0).toFixed(2)}</b></div>
      <div><span>Credit limit</span><b>${Number(data.credit_limit || 0).toFixed(2)}</b></div>
      <div><span>Last transaction</span><b>${escapeHtml(data.last_transaction_date)}</b></div>
      <div><span>Phone</span><b>${escapeHtml(data.phone)}</b></div>
      ${(data.tags || []).length ? `<p>${data.tags.map((tag) => `<em class="party-tag tag-${tag.toLowerCase().replace(/\s+/g, "-")}">${escapeHtml(tag)}</em>`).join("")}</p>` : ""}
    `;
  };
  const hide = () => timer = setTimeout(() => { card.hidden = true; }, 150);
  links.forEach((link) => {
    link.addEventListener("mouseenter", () => show(link));
    link.addEventListener("mouseleave", hide);
    link.addEventListener("focus", () => show(link));
    link.addEventListener("blur", hide);
  });
  card.addEventListener("mouseenter", () => clearTimeout(timer));
  card.addEventListener("mouseleave", hide);
}

function initCopyReferenceButtons() {
  document.querySelectorAll("[data-copy-ref]").forEach((ref) => {
    if (ref.querySelector(".copy-ref-button")) return;
    const button = document.createElement("button");
    button.className = "copy-ref-button";
    button.type = "button";
    button.title = "Copy reference";
    button.innerHTML = `<i class="bi bi-clipboard"></i>`;
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const value = ref.dataset.copyRef || ref.textContent.trim();
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
      else {
        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      const icon = button.querySelector("i");
      icon.className = "bi bi-check";
      setTimeout(() => icon.className = "bi bi-clipboard", 2000);
    });
    ref.appendChild(button);
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function initDatePresetChips() {
  document.querySelectorAll("form").forEach((form) => {
    const from = form.querySelector('input[type="date"][name="date_from"], input[type="date"][name$="_from"]');
    const to = form.querySelector('input[type="date"][name="date_to"], input[type="date"][name$="_to"]');
    if (!from || !to || form.querySelector(".date-preset-chips")) return;
    const chips = document.createElement("div");
    chips.className = "date-preset-chips";
    chips.innerHTML = ["Today", "Week", "Month", "Quarter", "Year"].map((label) => `<button class="date-preset-chip" type="button" data-date-preset="${label.toLowerCase()}">${label}</button>`).join("");
    from.closest(".row,.form-grid,form")?.insertBefore(chips, from.closest("[class^='col-'],div") || from);
    chips.addEventListener("click", (event) => {
      const button = event.target.closest("[data-date-preset]");
      if (!button) return;
      const range = presetDateRange(button.dataset.datePreset);
      from.value = range.from;
      to.value = range.to;
      from.dispatchEvent(new Event("change", {bubbles: true}));
      to.dispatchEvent(new Event("change", {bubbles: true}));
    });
  });
}

function presetDateRange(preset) {
  const now = new Date();
  const start = new Date(now);
  const end = new Date(now);
  if (preset === "week") start.setDate(now.getDate() - now.getDay());
  if (preset === "month") start.setDate(1);
  if (preset === "quarter") {
    start.setMonth(Math.floor(now.getMonth() / 3) * 3, 1);
  }
  if (preset === "year") start.setMonth(0, 1);
  return {from: dateInputValue(start), to: dateInputValue(end)};
}

function dateInputValue(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function initIndianNumberInputs() {
  const selector = ['amount','total','balance','paid','quantity','qty','rate','price','charges','discount','tax','stock'].map((part) => `input[name*="${part}"]`).join(",");
  const prepare = (input) => {
    if (input.type === "hidden" || input.readOnly || input.dataset.noFormat === "true") return;
    if (input.type === "number") input.type = "text";
    input.inputMode = "decimal";
    if (input.dataset.indianFormat === "true") return;
    input.dataset.indianFormat = "true";
    input.addEventListener("input", () => {
      const caretAtEnd = input.selectionStart === input.value.length;
      input.value = formatIndianNumber(input.value);
      if (caretAtEnd) input.setSelectionRange(input.value.length, input.value.length);
    });
    if (input.value) input.value = formatIndianNumber(input.value);
  };
  document.querySelectorAll(selector).forEach(prepare);
  document.addEventListener("focusin", (event) => {
    if (event.target.matches(selector)) prepare(event.target);
  });
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      form.querySelectorAll(selector).forEach((input) => input.value = rawNumber(input.value));
    });
  });
}

function rawNumber(value) {
  return String(value ?? "").replace(/,/g, "");
}

function parseFormattedNumber(value) {
  return Number(rawNumber(value) || 0);
}

function formatIndianNumber(value) {
  const clean = rawNumber(value).replace(/[^\d.-]/g, "");
  if (!clean || clean === "-" || clean === ".") return clean;
  const negative = clean.startsWith("-");
  const [wholeRaw, decimal] = clean.replace("-", "").split(".");
  let whole = wholeRaw.replace(/^0+(?=\d)/, "");
  if (whole.length > 3) {
    const lastThree = whole.slice(-3);
    const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    whole = `${rest},${lastThree}`;
  }
  return `${negative ? "-" : ""}${whole}${decimal !== undefined ? `.${decimal.slice(0, 6)}` : ""}`;
}

function initContextHelpTooltips() {
  const help = {
    "gst type": "Defines how GST applies to this transaction or party for tax reporting.",
    "gst/vat/trn": "Tax registration number used for GST, VAT, or TRN compliance.",
    "tds section": "Income-tax section that controls the TDS rate for supplier payments.",
    "hsn/sac": "Classification code used to determine GST treatment for goods or services.",
    "hsn code": "Classification code used to determine GST treatment for goods.",
    "costing method": "Inventory valuation method used to calculate item cost and profit.",
    "valuation method": "Inventory valuation method used to calculate item cost and profit."
  };
  document.querySelectorAll(".form-label").forEach((label) => {
    const text = label.textContent.trim().toLowerCase();
    const key = Object.keys(help).find((name) => text.includes(name));
    if (!key || label.querySelector(".field-help")) return;
    label.insertAdjacentHTML("beforeend", ` <i class="bi bi-question-circle field-help" tabindex="0" data-bs-toggle="tooltip" data-bs-title="${help[key]}"></i>`);
  });
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => new bootstrap.Tooltip(el));
}

function initRowContextMenu() {
  const rows = document.querySelectorAll("[data-context-menu]");
  if (!rows.length) return;
  const menu = document.createElement("div");
  menu.className = "row-context-menu";
  menu.hidden = true;
  menu.innerHTML = `
    <button type="button" data-row-action="open"><i class="bi bi-box-arrow-up-right"></i> Open</button>
    <button type="button" data-row-action="new-tab"><i class="bi bi-window"></i> Open in new tab</button>
    <button type="button" data-row-action="copy"><i class="bi bi-clipboard"></i> Copy invoice #</button>
    <button type="button" data-row-action="paid"><i class="bi bi-check-circle"></i> Mark as paid</button>
  `;
  document.body.appendChild(menu);
  let activeRow = null;
  rows.forEach((row) => {
    row.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      activeRow = row;
      menu.style.left = `${event.pageX}px`;
      menu.style.top = `${event.pageY}px`;
      menu.hidden = false;
    });
  });
  menu.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-row-action]")?.dataset.rowAction;
    if (!action || !activeRow) return;
    if (action === "open") window.location.href = activeRow.dataset.rowOpen;
    if (action === "new-tab") window.open(activeRow.dataset.rowOpen, "_blank");
    if (action === "copy") await navigator.clipboard.writeText(activeRow.dataset.rowRef || "");
    if (action === "paid") await markRowPaid(activeRow);
    menu.hidden = true;
  });
  document.addEventListener("click", () => menu.hidden = true);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") menu.hidden = true; });
}

async function markRowPaid(row) {
  const balance = Number(row.dataset.rowBalance || 0);
  if (!row.dataset.rowPayUrl || balance <= 0) return;
  const body = new URLSearchParams({
    payment_date: dateInputValue(new Date()),
    amount: String(balance),
    payment_mode: "Cash",
    reference_no: "Context menu",
    notes: "Marked paid from invoice list",
  });
  const headers = csrfHeaders();
  headers["Content-Type"] = "application/x-www-form-urlencoded";
  await fetch(row.dataset.rowPayUrl, {method: "POST", headers, body});
  window.location.reload();
}

function initSidebarState() {
  const details = [...document.querySelectorAll(".nav-accordion details")];
  const saved = JSON.parse(sessionStorage.getItem("vyapara_sidebar_open") || "[]");
  details.forEach((detail, index) => {
    if (saved.length) detail.open = saved.includes(index);
    detail.addEventListener("toggle", () => {
      const open = details.map((node, idx) => node.open ? idx : null).filter((idx) => idx !== null);
      sessionStorage.setItem("vyapara_sidebar_open", JSON.stringify(open));
    });
  });
}

function initFavorites() {
  const host = document.querySelector("#favoriteLinks");
  const links = [...document.querySelectorAll(".nav-accordion a")];
  if (!host) return;
  const key = "vyapara_sidebar_favorites";
  const read = () => JSON.parse(localStorage.getItem(key) || "[]");
  const write = (items) => localStorage.setItem(key, JSON.stringify(items.slice(0, 5)));
  const render = () => {
    const favs = read();
    host.innerHTML = favs.length ? favs.map((item) => `<a href="${item.href}"><i class="bi bi-star-fill"></i>${item.label}</a>`).join("") : `<span class="empty-favorite">Pin up to 5 pages</span>`;
    links.forEach((link) => link.classList.toggle("is-favorite", favs.some((item) => item.href === link.href)));
  };
  links.forEach((link) => {
    const star = document.createElement("button");
    star.className = "favorite-toggle";
    star.type = "button";
    star.title = "Pin favorite";
    star.innerHTML = `<i class="bi bi-star"></i>`;
    star.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const favs = read();
      const exists = favs.some((item) => item.href === link.href);
      const next = exists ? favs.filter((item) => item.href !== link.href) : [{href: link.href, label: link.textContent.trim()}, ...favs];
      write(next);
      render();
    });
    link.appendChild(star);
  });
  render();
}

function initBulkToolbar() {
  const bar = document.createElement("div");
  bar.className = "bulk-floating-toolbar";
  bar.innerHTML = `<strong><span data-bulk-count>0</span> selected</strong><button class="btn btn-sm btn-success" type="button">Mark Paid</button><button class="btn btn-sm btn-outline-secondary" type="button">Print</button><button class="btn btn-sm btn-outline-danger" type="button">Delete</button>`;
  document.body.appendChild(bar);
  const update = () => {
    const selected = document.querySelectorAll(".datatable .row-select:checked");
    bar.classList.toggle("show", selected.length > 0);
    bar.querySelector("[data-bulk-count]").textContent = selected.length;
  };
  document.addEventListener("change", (event) => {
    if (event.target.matches(".bulk-check-all")) {
      const table = event.target.closest("table");
      table?.querySelectorAll(".row-select").forEach((box) => box.checked = event.target.checked);
    }
    if (event.target.matches(".row-select,.bulk-check-all")) update();
  });
}

function initColumnChooser(table, dt, controls) {
  const tableId = table.id || `datatable-${[...document.querySelectorAll("table.datatable")].indexOf(table)}`;
  const key = `vyapara_columns_${tableId}`;
  const popover = controls.querySelector(".column-chooser-popover");
  const saved = JSON.parse(localStorage.getItem(key) || "{}");
  popover.innerHTML = [...table.querySelectorAll("thead th")].map((th, index) => {
    const label = th.textContent.trim() || "Actions";
    return `<label><input type="checkbox" data-column="${index}" ${saved[index] === false ? "" : "checked"}> ${label}</label>`;
  }).join("");
  Object.entries(saved).forEach(([index, visible]) => dt.column(Number(index)).visible(visible !== false));
  controls.querySelector(".column-chooser-toggle").addEventListener("click", () => popover.hidden = !popover.hidden);
  popover.addEventListener("change", (event) => {
    const input = event.target.closest("[data-column]");
    if (!input) return;
    saved[input.dataset.column] = input.checked;
    localStorage.setItem(key, JSON.stringify(saved));
    dt.column(Number(input.dataset.column)).visible(input.checked);
  });
}

function initStatusBadgeIcons() {
  const iconMap = {paid:"check-circle", pending:"clock", unpaid:"clock", partial:"clock-history", cancelled:"x-circle", overdue:"exclamation-circle", active:"check-circle", inactive:"dash-circle", draft:"pencil-square"};
  document.querySelectorAll(".badge,.status-badge").forEach((badge) => {
    if (badge.querySelector("i")) return;
    const text = badge.textContent.trim().toLowerCase();
    const key = Object.keys(iconMap).find((name) => text.includes(name));
    if (key) badge.insertAdjacentHTML("afterbegin", `<i class="bi bi-${iconMap[key]}"></i> `);
  });
}

function initInlineValidation() {
  document.querySelectorAll("form").forEach((form) => {
    form.querySelectorAll("input,select,textarea").forEach((field) => {
      field.addEventListener("blur", () => validateField(field));
      field.addEventListener("input", () => { if (field.classList.contains("is-invalid")) validateField(field); });
    });
  });
}

function validateField(field) {
  if (!field.willValidate) return;
  let feedback = field.parentElement.querySelector(".invalid-feedback[data-inline-validation]");
  if (!field.checkValidity()) {
    field.classList.add("is-invalid");
    if (!feedback) {
      feedback = document.createElement("div");
      feedback.className = "invalid-feedback";
      feedback.dataset.inlineValidation = "true";
      field.insertAdjacentElement("afterend", feedback);
    }
    feedback.textContent = field.validationMessage;
  } else {
    field.classList.remove("is-invalid");
    feedback?.remove();
  }
}

function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  return token ? {"X-CSRFToken": token, "Content-Type": "application/json"} : {"Content-Type": "application/json"};
}
