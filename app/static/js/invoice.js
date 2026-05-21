let invoiceProducts = [];

function optionLabel(product) {
  return `${product.sku} - ${product.name}${product.current_stock <= 0 ? " (Out)" : ""}`;
}

function optionsHtml(products, selectedId = "") {
  return products.map((p) => `<option value="${p.id}" data-price="${p.sales_price}" data-cost="${p.purchase_price}" data-tax="${p.tax_rate}" data-stock="${p.current_stock}" ${String(p.id) === String(selectedId) ? "selected" : ""}>${optionLabel(p)}</option>`).join("");
}

function legacyRowTemplate(products) {
  return `<div class="item-row mb-2">
    <select name="product_id[]" class="form-select product-select" required><option value="">Product</option>${optionsHtml(products)}</select>
    <input name="quantity[]" class="form-control qty" type="number" min="0.001" step="0.001" value="1">
    <input name="rate[]" class="form-control rate" type="number" min="0" step="0.01" value="0">
    <input name="discount[]" class="form-control discount" type="number" min="0" step="0.01" value="0">
    <input name="tax_rate[]" class="form-control tax" type="number" min="0" step="0.01" value="0">
    <input class="form-control line-total" readonly value="0.00">
    <button class="btn btn-outline-danger remove-row" type="button"><i class="bi bi-trash"></i></button>
    <div class="stock-hint small text-muted"></div>
  </div>`;
}

function cartRowTemplate(product) {
  const selectedId = product?.id || "";
  return `<div class="item-row cart-row" draggable="true">
    <button class="drag-handle" type="button" title="Drag item"><i class="bi bi-grip-vertical"></i></button>
    <select name="product_id[]" class="form-select product-select" required><option value="">Product</option>${optionsHtml(invoiceProducts, selectedId)}</select>
    <div class="cart-row-main">
      <strong class="cart-row-title">${product ? product.name : "Select product"}</strong>
      <span class="stock-hint">${product ? `Available: ${product.current_stock}` : ""}</span>
    </div>
    <label>Qty<input name="quantity[]" class="form-control qty" type="number" min="0.001" step="0.001" value="1"></label>
    <label>Rate<input name="rate[]" class="form-control rate" type="number" min="0" step="0.01" value="${product ? product.sales_price : 0}"></label>
    <label>Disc %<input name="discount[]" class="form-control discount" type="number" min="0" step="0.01" value="0"></label>
    <label>Tax %<input name="tax_rate[]" class="form-control tax" type="number" min="0" step="0.01" value="${product ? product.tax_rate : 0}"></label>
    <label>Total<input class="form-control line-total" readonly value="0.00"></label>
    <button class="btn btn-outline-danger remove-row" type="button" title="Remove"><i class="bi bi-trash"></i></button>
  </div>`;
}

async function initInvoiceForm(mode) {
  const holder = document.querySelector("#items");
  if (!holder) return;
  invoiceProducts = await fetch("/api/products").then((r) => r.json());

  if (document.querySelector(".invoice-pos-shell")) {
    initPosInvoiceForm(mode, holder);
    return;
  }

  document.querySelector("#add-row").addEventListener("click", () => {
    holder.insertAdjacentHTML("beforeend", legacyRowTemplate(invoiceProducts));
  });
  if (!holder.children.length) document.querySelector("#add-row").click();
  wireLineItemEvents(mode, holder);
  wireTotals();
}

function initPosInvoiceForm(mode, holder) {
  const grid = document.querySelector("#product-grid");
  const search = document.querySelector("#product-search");
  const clearSearch = document.querySelector("#clear-search");
  const clearCart = document.querySelector("#clear-cart");

  document.querySelector("#add-row").addEventListener("click", () => {
    holder.insertAdjacentHTML("beforeend", cartRowTemplate(null));
    updateCartState();
  });

  clearCart?.addEventListener("click", () => {
    holder.innerHTML = "";
    calculateInvoice();
    updateCartState();
  });

  clearSearch?.addEventListener("click", () => {
    search.value = "";
    filterProductTiles();
    search.focus();
  });

  search?.addEventListener("input", filterProductTiles);
  document.querySelectorAll(".category-chip").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".category-chip").forEach((chip) => chip.classList.remove("active"));
      button.classList.add("active");
      filterProductTiles();
    });
  });

  grid?.addEventListener("click", (event) => {
    const tile = event.target.closest(".product-tile");
    if (tile) addProductToCart(tile.dataset.productId);
  });
  grid?.addEventListener("dragstart", (event) => {
    const tile = event.target.closest(".product-tile");
    if (!tile) return;
    event.dataTransfer.setData("text/product-id", tile.dataset.productId);
    event.dataTransfer.effectAllowed = "copy";
  });

  holder.addEventListener("dragover", (event) => {
    event.preventDefault();
    holder.classList.add("drag-over");
    const draggingRow = document.querySelector(".cart-row.dragging");
    if (!draggingRow) return;
    const afterElement = getDragAfterElement(holder, event.clientY);
    if (afterElement == null) holder.appendChild(draggingRow);
    else holder.insertBefore(draggingRow, afterElement);
  });
  holder.addEventListener("dragleave", (event) => {
    if (!holder.contains(event.relatedTarget)) holder.classList.remove("drag-over");
  });
  holder.addEventListener("drop", (event) => {
    event.preventDefault();
    holder.classList.remove("drag-over");
    const productId = event.dataTransfer.getData("text/product-id");
    if (productId) addProductToCart(productId);
  });
  holder.addEventListener("dragstart", (event) => {
    const row = event.target.closest(".cart-row");
    if (!row) return;
    row.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
  });
  holder.addEventListener("dragend", (event) => {
    event.target.closest(".cart-row")?.classList.remove("dragging");
    calculateInvoice();
  });

  wireLineItemEvents(mode, holder);
  wireTotals();
  holder.querySelectorAll(".cart-row").forEach((row) => syncRowFromSelect(row, mode, false));
  updateCartState();
}

function wireLineItemEvents(mode, holder) {
  holder.addEventListener("change", (e) => {
    if (e.target.classList.contains("product-select")) {
      const row = e.target.closest(".item-row");
      syncRowFromSelect(row, mode, true);
      calculateInvoice();
      updateCartState();
    }
  });
  holder.addEventListener("input", () => {
    calculateInvoice();
    updateCartState();
  });
  holder.addEventListener("click", (e) => {
    if (e.target.closest(".remove-row")) {
      e.target.closest(".item-row").remove();
      calculateInvoice();
      updateCartState();
    }
  });
}

function wireTotals() {
  document.querySelectorAll("#paid_amount,#shipping_charges,#other_charges,#round_off").forEach((el) => el?.addEventListener("input", calculateInvoice));
  document.querySelector("#pay-full")?.addEventListener("click", () => {
    const grand = document.querySelector("#grand_total")?.value || 0;
    document.querySelector("#paid_amount").value = grand;
    calculateInvoice();
  });
}

function addProductToCart(productId) {
  const holder = document.querySelector("#items");
  const product = invoiceProducts.find((item) => String(item.id) === String(productId));
  if (!holder || !product) return;

  const existing = [...holder.querySelectorAll(".product-select")].find((select) => String(select.value) === String(productId));
  if (existing) {
    const row = existing.closest(".item-row");
    const qty = row.querySelector(".qty");
    qty.value = (Number(qty.value || 0) + 1).toFixed(3).replace(/\.?0+$/, "");
    row.classList.add("row-pulse");
    setTimeout(() => row.classList.remove("row-pulse"), 420);
  } else {
    holder.insertAdjacentHTML("beforeend", cartRowTemplate(product));
  }
  calculateInvoice();
  updateCartState();
}

function syncRowFromSelect(row, mode, applyPricing = true) {
  const select = row.querySelector(".product-select");
  const opt = select.selectedOptions[0];
  const product = invoiceProducts.find((item) => String(item.id) === String(select.value));
  const price = mode === "purchase" ? opt?.dataset.cost : opt?.dataset.price;

  if (applyPricing && price !== undefined) row.querySelector(".rate").value = price || 0;
  if (applyPricing && opt?.dataset.tax !== undefined) row.querySelector(".tax").value = opt.dataset.tax || 0;
  row.querySelector(".stock-hint").textContent = opt?.value ? `Available: ${opt.dataset.stock || 0}` : "";
  const title = row.querySelector(".cart-row-title");
  if (title) title.textContent = product ? product.name : "Select product";
}

function filterProductTiles() {
  const query = (document.querySelector("#product-search")?.value || "").trim().toLowerCase();
  const activeCategory = document.querySelector(".category-chip.active")?.dataset.category || "all";
  document.querySelectorAll(".product-tile").forEach((tile) => {
    const matchesQuery = !query || tile.dataset.search.includes(query);
    const matchesCategory = activeCategory === "all" || tile.dataset.category === activeCategory;
    tile.hidden = !(matchesQuery && matchesCategory);
  });
}

function getDragAfterElement(container, y) {
  const elements = [...container.querySelectorAll(".cart-row:not(.dragging)")];
  return elements.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) return { offset, element: child };
    return closest;
  }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function updateCartState() {
  const emptyState = document.querySelector("#cart-empty-state");
  const holder = document.querySelector("#items");
  if (emptyState && holder) emptyState.hidden = holder.children.length > 0;
}

function calculateInvoice() {
  let subtotal = 0, discountTotal = 0, taxTotal = 0;
  document.querySelectorAll(".item-row").forEach((row) => {
    const q = Number(row.querySelector(".qty").value || 0);
    const r = Number(row.querySelector(".rate").value || 0);
    const d = Number(row.querySelector(".discount").value || 0);
    const t = Number(row.querySelector(".tax").value || 0);
    const stock = Number(row.querySelector(".product-select").selectedOptions[0]?.dataset.stock || 0);
    const gross = q * r;
    const discount = gross * d / 100;
    const tax = (gross - discount) * t / 100;
    const total = gross - discount + tax;
    subtotal += gross; discountTotal += discount; taxTotal += tax;
    row.querySelector(".line-total").value = total.toFixed(2);
    row.classList.toggle("table-warning", stock > 0 && q > stock);
    row.querySelector(".stock-hint").classList.toggle("text-danger", stock > 0 && q > stock);
  });
  const shipping = Number(document.querySelector("#shipping_charges")?.value || 0);
  const other = Number(document.querySelector("#other_charges")?.value || 0);
  const roundOff = Number(document.querySelector("#round_off")?.value || 0);
  const paid = Number(document.querySelector("#paid_amount")?.value || 0);
  const grand = subtotal - discountTotal + taxTotal + shipping + other + roundOff;
  setValue("#subtotal", subtotal.toFixed(2));
  setValue("#discount_total", discountTotal.toFixed(2));
  setValue("#tax_total", taxTotal.toFixed(2));
  setValue("#grand_total", grand.toFixed(2));
  setValue("#balance_amount", (grand - paid).toFixed(2));
  setValue("#payment_status", paid <= 0 ? "Unpaid" : (paid >= grand ? "Paid" : "Partial"));
}

function setValue(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.value = value;
}
