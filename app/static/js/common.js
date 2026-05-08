document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("table.datatable").forEach((table) => new DataTable(table, {layout: {topStart: "pageLength", topEnd: "search", bottomStart: "info", bottomEnd: "paging"}}));
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

function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  return token ? {"X-CSRFToken": token, "Content-Type": "application/json"} : {"Content-Type": "application/json"};
}
