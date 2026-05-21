const POS = {
  cart: [],
  paymentMode: "Cash",
  paymentRows: [],
  lastReceiptUrl: "",
  submitting: false,
  activeLine: null,
  heldRows: [],
};

const qs = (sel, root = document) => root.querySelector(sel);
const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];
const money = (value) => Number(value || 0);
const fmt = (value) => money(value).toFixed(2);
const uid = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

function csrfHeaders(extra = {}) {
  return Object.assign({"X-CSRFToken": qs('meta[name="csrf-token"]')?.content || ""}, extra);
}

function toast(message, type = "primary") {
  const host = qs("#posToastHost");
  if (!host) return alert(message);
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type} border-0`;
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(message)}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  host.appendChild(el);
  const instance = new bootstrap.Toast(el, {delay: 3200});
  instance.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

function terminal() { return qs(".pos-terminal"); }
function cartStorageKey() {
  return `vyapara_pos_cart_${terminal()?.dataset.sessionId || "default"}`;
}
function saveCartState() {
  try {
    localStorage.setItem(cartStorageKey(), JSON.stringify({
      cart: POS.cart,
      customer_id: qs("#posCustomer")?.value || "",
      bill_discount: qs("#billDiscount")?.value || "0",
      coupon_code: qs("#couponCode")?.value || "",
      cart_notes: qs("#cartNotes")?.value || "",
      saved_at: new Date().toISOString(),
    }));
  } catch (error) {
    console.warn("Unable to save POS cart", error);
  }
}
function clearCartState() {
  try { localStorage.removeItem(cartStorageKey()); } catch (error) { console.warn("Unable to clear POS cart", error); }
}
function restoreCartState() {
  try {
    const raw = localStorage.getItem(cartStorageKey());
    if (!raw) return;
    const saved = JSON.parse(raw);
    POS.cart = Array.isArray(saved.cart) ? saved.cart : [];
    if (saved.customer_id && qs("#posCustomer")) qs("#posCustomer").value = saved.customer_id;
    if (qs("#billDiscount")) qs("#billDiscount").value = saved.bill_discount || "0";
    if (qs("#couponCode")) qs("#couponCode").value = saved.coupon_code || "";
    if (qs("#cartNotes")) qs("#cartNotes").value = saved.cart_notes || "";
    if (POS.cart.length) toast("Cart restored from this POS session", "info");
  } catch (error) {
    console.warn("Unable to restore POS cart", error);
    clearCartState();
  }
}
function productsFromDom() {
  return qsa(".pos-product").map(tile => productFromTile(tile));
}
function productFromTile(tile) {
  return {
    id: Number(tile.dataset.id),
    name: tile.dataset.name,
    sku: tile.dataset.sku,
    barcode: tile.dataset.barcode,
    category: tile.dataset.category,
    rate: money(tile.dataset.rate),
    tax_rate: money(tile.dataset.tax),
    tax_name: tile.dataset.taxName || "",
    stock: money(tile.dataset.stock),
    track_inventory: tile.dataset.trackInventory === "1",
    batch_tracking: tile.dataset.batch === "1",
    serial_tracking: tile.dataset.serial === "1",
    expiry_tracking: tile.dataset.expiry === "1",
    decimal_allowed: tile.dataset.decimal === "1",
    low_stock: tile.classList.contains("low"),
    batches: [],
    serials: [],
  };
}

function lineBase(item) { return money(item.qty) * money(item.rate); }
function lineDiscountAmount(item) { return lineBase(item) * money(item.discount) / 100; }
function lineTaxable(item) { return Math.max(lineBase(item) - lineDiscountAmount(item), 0); }
function lineTax(item) { return lineTaxable(item) * money(item.tax_rate) / 100; }
function lineTotal(item) { return lineTaxable(item) + lineTax(item); }

function totals() {
  const rawSubtotal = POS.cart.reduce((sum, item) => sum + lineBase(item), 0);
  const lineDiscount = POS.cart.reduce((sum, item) => sum + lineDiscountAmount(item), 0);
  const taxableBeforeBill = POS.cart.reduce((sum, item) => sum + lineTaxable(item), 0);
  const billDiscount = Math.min(money(qs("#billDiscount")?.value), taxableBeforeBill);
  const couponDiscount = money(qs("#couponCode")?.dataset.discount || 0);
  const taxable = Math.max(taxableBeforeBill - billDiscount - couponDiscount, 0);
  const taxBeforeScale = POS.cart.reduce((sum, item) => sum + lineTax(item), 0);
  const tax = taxableBeforeBill ? taxBeforeScale * (taxable / taxableBeforeBill) : 0;
  const unrounded = taxable + tax;
  const rounded = Math.round(unrounded);
  const roundOff = rounded - unrounded;
  return {rawSubtotal, lineDiscount, billDiscount, couponDiscount, taxable, tax, roundOff, grandTotal: Math.max(rounded, 0)};
}

function validateLine(item) {
  if (item.track_inventory && money(item.stock) <= 0) return `${item.name} is out of stock`;
  if (item.track_inventory && money(item.qty) > money(item.stock)) return `Only ${item.stock} available for ${item.name}`;
  if (!item.decimal_allowed && !Number.isInteger(money(item.qty))) return `${item.name} does not allow decimal quantity`;
  if (item.serial_tracking && money(item.qty) !== 1) return `${item.name} requires one serial per line`;
  return "";
}

function addProduct(product, options = {}) {
  if (product.track_inventory && product.stock <= 0) return toast(`${product.name} is out of stock`, "warning");
  const hasSelectableBatches = product.batch_tracking && Array.isArray(product.batches) && product.batches.length > 0;
  const hasSelectableSerials = product.serial_tracking && Array.isArray(product.serials) && product.serials.length > 0;
  const needsDetail = hasSelectableBatches || hasSelectableSerials || options.forceQuantity;
  if (needsDetail) return openLineDetail(product);
  const existing = POS.cart.find(item => item.product_id === product.id && !item.batch_id && !item.serial_id);
  if (existing) existing.qty = money(existing.qty) + 1;
  else POS.cart.push({...product, product_id: product.id, qty: 1, discount: 0, note: "", request_line_id: uid()});
  renderCart();
}

function removeProduct(product) {
  const idx = POS.cart.findIndex(item => item.product_id === product.id && !item.batch_id && !item.serial_id);
  if (idx < 0) return toast(`${product.name} is not in the cart`, "warning");
  const item = POS.cart[idx];
  const nextQty = money(item.qty) - 1;
  if (nextQty <= 0) POS.cart.splice(idx, 1);
  else item.qty = item.decimal_allowed ? Math.max(0.001, nextQty) : Math.max(1, Math.round(nextQty));
  renderCart();
}

function cartQtyForProduct(productId) {
  return POS.cart
    .filter(item => Number(item.product_id) === Number(productId))
    .reduce((sum, item) => sum + money(item.qty), 0);
}

function updateProductTileCounts() {
  qsa(".pos-product").forEach(tile => {
    const qty = cartQtyForProduct(tile.dataset.id);
    const count = qs("[data-product-count]", tile);
    const minus = qs("[data-product-minus]", tile);
    if (count) count.textContent = fmt(qty).replace(/\.00$/, "");
    tile.classList.toggle("in-cart", qty > 0);
    if (minus) minus.disabled = qty <= 0;
  });
}

function renderCart() {
  const holder = qs("#cartItems");
  const empty = qs("#cartEmpty");
  empty.hidden = POS.cart.length > 0;
  holder.innerHTML = POS.cart.map((item, idx) => `
    <article class="cart-line ${validateLine(item) ? 'border-warning' : ''}">
      <div class="cart-line-top">
        <div class="cart-line-title">
          <strong>${esc(item.name)}</strong>
          <small>${esc(item.sku || '')}${item.batch_no ? ' · Batch ' + esc(item.batch_no) : ''}${item.serial_no ? ' · Serial ' + esc(item.serial_no) : ''}</small>
        </div>
        <strong>₹${fmt(lineTotal(item))}</strong>
      </div>
      <div class="cart-line-controls">
        <label>Qty
          <span class="qty-control">
            <button class="btn btn-outline-secondary" type="button" data-step="${idx}" data-delta="-1">-</button>
            <input class="form-control" value="${esc(item.qty)}" data-qty="${idx}">
            <button class="btn btn-outline-secondary" type="button" data-step="${idx}" data-delta="1">+</button>
          </span>
        </label>
        <label>Rate<input class="form-control" value="${fmt(item.rate)}" data-rate="${idx}" ${item.restrict_price_edit ? 'readonly' : ''}></label>
        <label>Disc %<input class="form-control" value="${fmt(item.discount)}" data-discount="${idx}"></label>
        <button class="btn btn-outline-danger" type="button" data-remove="${idx}"><i class="bi bi-x-lg"></i></button>
      </div>
      <div class="line-note">${validateLine(item) ? `<span class="text-warning">${esc(validateLine(item))}</span>` : `<button class="btn btn-link p-0" type="button" data-detail="${idx}">${item.batch_no || item.serial_no ? "Batch / serial / note" : "Details / note"}</button>`}</div>
    </article>
  `).join("");
  updateSummary();
  updateProductTileCounts();
  saveCartState();
}

function updateSummary() {
  const t = totals();
  qs("#subtotalValue").textContent = fmt(t.rawSubtotal);
  qs("#lineDiscountValue").textContent = fmt(t.lineDiscount);
  qs("#couponDiscountValue").textContent = fmt(t.couponDiscount);
  qs("#taxableValue").textContent = fmt(t.taxable);
  qs("#taxValue").textContent = fmt(t.tax);
  qs("#roundOffValue").textContent = fmt(t.roundOff);
  qs("#grandTotalValue").textContent = fmt(t.grandTotal);
  qs("#checkoutPayable").textContent = `₹${fmt(t.grandTotal)}`;
  qs("#totalItems").textContent = POS.cart.length;
  qs("#totalQty").textContent = fmt(POS.cart.reduce((sum, item) => sum + money(item.qty), 0)).replace(/\.00$/, "");
  updatePaymentModal();
}

function bindCartEvents() {
  qs("#cartItems").addEventListener("click", event => {
    const step = event.target.closest("[data-step]");
    const remove = event.target.closest("[data-remove]");
    const detail = event.target.closest("[data-detail]");
    if (step) {
      const item = POS.cart[Number(step.dataset.step)];
      const next = money(item.qty) + Number(step.dataset.delta);
      item.qty = item.decimal_allowed ? Math.max(0.001, next) : Math.max(1, Math.round(next));
      renderCart();
    }
    if (remove) {
      POS.cart.splice(Number(remove.dataset.remove), 1);
      renderCart();
    }
    if (detail) openLineDetail(POS.cart[Number(detail.dataset.detail)], Number(detail.dataset.detail));
  });
  qs("#cartItems").addEventListener("change", event => {
    const qty = event.target.closest("[data-qty]");
    const rate = event.target.closest("[data-rate]");
    const discount = event.target.closest("[data-discount]");
    if (qty) {
      const item = POS.cart[Number(qty.dataset.qty)];
      item.qty = item.decimal_allowed ? Math.max(0.001, money(qty.value)) : Math.max(1, Math.round(money(qty.value)));
    }
    if (rate) {
      const item = POS.cart[Number(rate.dataset.rate)];
      if (item.restrict_price_edit) return toast("Price edit is restricted for this item", "warning");
      item.rate = Math.max(0, money(rate.value));
    }
    if (discount) {
      const item = POS.cart[Number(discount.dataset.discount)];
      item.discount = Math.min(50, Math.max(0, money(discount.value)));
      if (money(discount.value) > 50) toast("Discount capped at 50% without supervisor override", "warning");
    }
    renderCart();
  });
}

function filterProducts() {
  const query = qs("#posSearch").value.trim().toLowerCase();
  const category = qs(".category-ribbon .active")?.dataset.category || "all";
  let visible = 0;
  qsa(".pos-product").forEach(tile => {
    const match = (!query || tile.dataset.search.includes(query) || tile.dataset.barcode === query || tile.dataset.sku.toLowerCase() === query) && (category === "all" || tile.dataset.category === category);
    tile.hidden = !match;
    if (match) visible += 1;
  });
  qs("#visibleProductCount").textContent = `${visible} item${visible === 1 ? "" : "s"}`;
}

async function searchProducts(query) {
  const url = `${terminal().dataset.searchUrl}?q=${encodeURIComponent(query)}&warehouse_id=${encodeURIComponent(terminal().dataset.warehouseId || "")}`;
  const res = await fetch(url);
  const data = await res.json().catch(() => ({data: []}));
  return data.data || [];
}

async function handleSearchEnter() {
  const value = qs("#posSearch").value.trim();
  if (!value) return;
  let exactTile = qsa(".pos-product").find(tile => tile.dataset.barcode === value || tile.dataset.sku.toLowerCase() === value.toLowerCase());
  if (exactTile) {
    addProduct(productFromTile(exactTile));
    qs("#posSearch").value = "";
    filterProducts();
    return;
  }
  const matches = await searchProducts(value);
  if (matches.length === 1) {
    addProduct(normalizeProduct(matches[0]));
    qs("#posSearch").value = "";
    filterProducts();
  } else if (matches.length > 1) {
    openProductSelect(matches.map(normalizeProduct));
  } else {
    toast("No matching product, SKU, barcode, batch or serial found", "warning");
  }
}

function normalizeProduct(product) {
  return {
    id: Number(product.id),
    product_id: Number(product.id),
    name: product.name,
    sku: product.sku,
    barcode: product.barcode,
    category: product.category,
    rate: money(product.rate),
    tax_rate: money(product.tax_rate),
    stock: money(product.stock),
    track_inventory: !!product.track_inventory,
    batch_tracking: !!product.batch_tracking,
    serial_tracking: !!product.serial_tracking,
    expiry_tracking: !!product.expiry_tracking,
    decimal_allowed: !!product.decimal_allowed,
    low_stock: !!product.low_stock,
    batches: product.batches || [],
    serials: product.serials || [],
  };
}

function openProductSelect(products) {
  const list = qs("#productSelectList");
  list.innerHTML = products.map((product, idx) => `
    <button class="held-card w-100 text-start product-choice" data-choice="${idx}" type="button">
      <span><strong>${esc(product.name)}</strong><br><small>${esc(product.sku)} · Stock ${esc(product.stock)}</small></span>
      <strong>₹${fmt(product.rate)}</strong>
    </button>
  `).join("");
  list.dataset.products = JSON.stringify(products);
  new bootstrap.Modal(qs("#productSelectModal")).show();
}

function openLineDetail(product, index = null) {
  POS.activeLine = {product, index};
  qs("#lineDetailTitle").textContent = product.name;
  qs("#detailQty").value = product.qty || 1;
  qs(".batch-field").hidden = !product.batch_tracking;
  qs(".serial-field").hidden = !product.serial_tracking;
  qs("#detailBatch").innerHTML = `<option value="">Select batch</option>${(product.batches || []).map(batch => `<option value="${batch.id}" data-no="${esc(batch.batch_no)}" data-stock="${batch.quantity}">${esc(batch.batch_no)} · ${esc(batch.quantity)} · Exp ${esc(batch.expiry_date || '-')}</option>`).join("")}`;
  qs("#detailSerial").innerHTML = `<option value="">Select serial</option>${(product.serials || []).map(serial => `<option value="${serial.id}" data-no="${esc(serial.serial_no)}">${esc(serial.serial_no)}</option>`).join("")}`;
  qs("#detailNote").value = product.note || "";
  new bootstrap.Modal(qs("#lineDetailModal")).show();
}

function saveLineDetail() {
  const {product, index} = POS.activeLine || {};
  if (!product) return;
  const next = {...product, product_id: product.product_id || product.id, qty: money(qs("#detailQty").value) || 1, discount: product.discount || 0, note: qs("#detailNote").value, request_line_id: product.request_line_id || uid()};
  const batchOption = qs("#detailBatch").selectedOptions[0];
  const serialOption = qs("#detailSerial").selectedOptions[0];
  if (next.batch_tracking && !qs("#detailBatch").value) return toast("Select a batch for this item", "warning");
  if (next.serial_tracking && !qs("#detailSerial").value) return toast("Select a serial number for this item", "warning");
  if (batchOption) { next.batch_id = qs("#detailBatch").value; next.batch_no = batchOption.dataset.no; next.stock = money(batchOption.dataset.stock || next.stock); }
  if (serialOption) { next.serial_id = qs("#detailSerial").value; next.serial_no = serialOption.dataset.no; next.qty = 1; }
  if (validateLine(next)) return toast(validateLine(next), "warning");
  if (index === null) POS.cart.push(next);
  else POS.cart[index] = next;
  bootstrap.Modal.getInstance(qs("#lineDetailModal"))?.hide();
  renderCart();
}

function buildPaymentRows(mode = POS.paymentMode) {
  const total = totals().grandTotal;
  if (mode === "Split") POS.paymentRows = [{mode:"Cash", amount: total, reference:""}];
  else if (mode === "Credit") POS.paymentRows = [{mode:"Credit", amount: 0, reference:""}];
  else POS.paymentRows = [{mode, amount: total, reference:""}];
  renderPaymentRows();
}

function renderPaymentRows() {
  qs("#paymentRows").innerHTML = POS.paymentRows.map((row, idx) => `
    <div class="payment-row">
      <select class="form-select" data-pay-mode="${idx}">
        ${["Cash","Card","UPI","Wallet","Credit"].map(mode => `<option ${mode === row.mode ? "selected" : ""}>${mode}</option>`).join("")}
      </select>
      <input class="form-control" type="number" min="0" step="0.01" value="${fmt(row.amount)}" data-pay-amount="${idx}">
      <button class="btn btn-outline-danger" type="button" data-pay-remove="${idx}"><i class="bi bi-x"></i></button>
    </div>
  `).join("");
  updatePaymentModal();
}

function updatePaymentModal() {
  if (!qs("#payGrandTotal")) return;
  const total = totals().grandTotal;
  const received = POS.paymentRows.reduce((sum, row) => row.mode === "Credit" ? sum : sum + money(row.amount), 0);
  qs("#payGrandTotal").textContent = `₹${fmt(total)}`;
  qs("#amountReceived").textContent = fmt(received);
  qs("#balanceDue").textContent = fmt(Math.max(total - received, 0));
  qs("#paymentChangeDue").textContent = fmt(Math.max(received - total, 0));
  const selected = qs("#posCustomer").selectedOptions[0];
  const isWalkin = qs("#posCustomer").value === terminal().dataset.walkinId;
  const credit = money(selected?.dataset.credit);
  const outstanding = money(selected?.dataset.outstanding);
  qs("#creditWarning").textContent = POS.paymentMode === "Credit" && isWalkin ? "Customer required for credit sale" : POS.paymentMode === "Credit" && credit && outstanding + total > credit ? "Credit limit warning" : "";
}

function paymentPayload() {
  const total = totals().grandTotal;
  const cash = POS.paymentRows.filter(r => r.mode === "Cash").reduce((s, r) => s + money(r.amount), 0);
  const card = POS.paymentRows.filter(r => r.mode === "Card").reduce((s, r) => s + money(r.amount), 0);
  const upi = POS.paymentRows.filter(r => r.mode === "UPI").reduce((s, r) => s + money(r.amount), 0);
  const wallet = POS.paymentRows.filter(r => r.mode === "Wallet").reduce((s, r) => s + money(r.amount), 0);
  const hasCredit = POS.paymentRows.some(r => r.mode === "Credit");
  return {
    payment_mode: POS.paymentMode === "Split" ? "Split" : hasCredit ? "Credit" : POS.paymentMode,
    cash_tendered: cash,
    card_amount: card,
    upi_amount: upi,
    wallet_amount: wallet,
    reference_no: qs("#paymentReference").value,
    paid_total: cash + card + upi + wallet,
    total,
  };
}

async function completeSale(after = "done") {
  if (POS.submitting) return;
  if (!POS.cart.length) return toast("Cart is empty", "warning");
  for (const item of POS.cart) {
    const error = validateLine(item);
    if (error) return toast(error, "warning");
  }
  const pay = paymentPayload();
  const isCredit = pay.payment_mode === "Credit";
  if (isCredit && qs("#posCustomer").value === terminal().dataset.walkinId) return toast("Select a customer for credit sale", "warning");
  if (!isCredit && pay.paid_total < pay.total) return toast("Payment total is less than the bill total", "warning");
  POS.submitting = true;
  qsa(".complete-sale").forEach(btn => { btn.disabled = true; btn.textContent = "Completing..."; });
  const body = {
    request_id: uid(),
    customer_id: qs("#posCustomer").value,
    warehouse_id: terminal().dataset.warehouseId,
    items: POS.cart.map(item => ({product_id:item.product_id, qty:item.qty, rate:item.rate, discount:item.discount, tax_rate:item.tax_rate, batch_id:item.batch_id, serial_id:item.serial_id, note:item.note})),
    discount_total: money(qs("#billDiscount").value),
    coupon_code: qs("#couponCode").value,
    delivery_bill: false,
    ...pay,
  };
  const res = await fetch(terminal().dataset.saleUrl, {method:"POST", headers:csrfHeaders({"Content-Type":"application/json"}), body:JSON.stringify(body)});
  const data = await res.json().catch(() => ({}));
  POS.submitting = false;
  qsa(".complete-sale").forEach(btn => { btn.disabled = false; btn.textContent = btn.dataset.after === "done" ? "Complete Sale" : `Complete + ${btn.dataset.after[0].toUpperCase()}${btn.dataset.after.slice(1)}`; });
  if (!res.ok) return toast(data.error || "Sale failed", "danger");
  POS.lastReceiptUrl = `/pos/receipt/${data.sale_id}`;
  POS.cart = [];
  qs("#billDiscount").value = "0";
  qs("#couponCode").value = "";
  qs("#cartNotes").value = "";
  clearCartState();
  renderCart();
  bootstrap.Modal.getInstance(qs("#paymentModal"))?.hide();
  qs("#successText").textContent = `${data.invoice_no} · Total ₹${fmt(data.grand_total)} · Change ₹${fmt(data.change_due)}`;
  qs("#successPrint").href = POS.lastReceiptUrl;
  new bootstrap.Modal(qs("#successModal")).show();
  if (after === "print") window.open(POS.lastReceiptUrl, "_blank");
  if (after === "whatsapp" || after === "email") toast(`${after} receipt requires configured communication provider`, "info");
}

async function holdCart() {
  if (!POS.cart.length) return toast("Cart is empty", "warning");
  const notes = prompt("Hold name/token or note");
  if (notes === null) return;
  const res = await fetch(terminal().dataset.holdUrl, {method:"POST", headers:csrfHeaders({"Content-Type":"application/json"}), body:JSON.stringify({customer_id:qs("#posCustomer").value, warehouse_id:terminal().dataset.warehouseId, notes, items:POS.cart})});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return toast(data.error || "Unable to hold bill", "danger");
  POS.cart = [];
  clearCartState();
  renderCart();
  toast(`Bill held as ${data.hold_no}`, "success");
}

async function showHeldBills() {
  const list = qs("#heldBillsList");
  list.innerHTML = `<div class="text-muted py-4 text-center">Loading held bills...</div>`;
  new bootstrap.Modal(qs("#recallModal")).show();
  const res = await fetch(terminal().dataset.heldUrl);
  const data = await res.json().catch(() => ({data: []}));
  POS.heldRows = data.data || [];
  renderHeldBills();
}

function renderHeldBills() {
  const q = (qs("#heldSearch").value || "").toLowerCase();
  const rows = POS.heldRows.filter(row => `${row.hold_no} ${row.customer} ${row.notes}`.toLowerCase().includes(q));
  qs("#heldBillsList").innerHTML = rows.length ? rows.map(row => `
    <div class="held-card">
      <div><strong>${esc(row.hold_no)}</strong><br><small>${esc(row.customer)} · ${row.item_count} items · ₹${fmt(row.amount)} · ${esc(row.held_by || '')}<br>${esc(row.notes || '')}</small></div>
      <div class="d-flex gap-2">
        <button class="btn btn-primary btn-sm" data-recall="${row.id}" type="button">Recall</button>
        <button class="btn btn-outline-danger btn-sm" data-delete-held="${row.id}" type="button">Delete</button>
      </div>
    </div>
  `).join("") : `<div class="empty-state compact"><i class="bi bi-pause-circle"></i><strong>No held bills</strong><small>Held bills for this session will appear here.</small></div>`;
}

async function recallHeld(id) {
  const res = await fetch(`/pos/held/${id}/json`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return toast(data.error || "Unable to recall bill", "danger");
  POS.cart = (data.items || []).map(item => ({...item, product_id:Number(item.product_id), qty:money(item.qty || item.quantity || 1), rate:money(item.rate), discount:money(item.discount), tax_rate:money(item.tax_rate), request_line_id: uid()}));
  if (data.customer_id) qs("#posCustomer").value = data.customer_id;
  renderCart();
  bootstrap.Modal.getInstance(qs("#recallModal"))?.hide();
  toast("Held bill recalled", "success");
}

async function deleteHeld(id) {
  if (!confirm("Delete this held bill?")) return;
  const res = await fetch(`/pos/held/${id}/delete`, {method:"POST", headers:csrfHeaders()});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return toast(data.error || "Unable to delete held bill", "danger");
  POS.heldRows = POS.heldRows.filter(row => String(row.id) !== String(id));
  renderHeldBills();
  toast("Held bill deleted", "success");
}

function bindStaticEvents() {
  qsa(".pos-product").forEach(tile => {
    tile.addEventListener("click", event => {
      const product = productFromTile(tile);
      if (event.target.closest("[data-product-plus]")) return addProduct(product);
      if (event.target.closest("[data-product-minus]")) return removeProduct(product);
      addProduct(product);
    });
    tile.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        addProduct(productFromTile(tile));
      }
    });
  });
  qs("#posSearch").addEventListener("input", filterProducts);
  qs("#posSearch").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); handleSearchEnter(); } });
  qs("#clearSearch").addEventListener("click", () => { qs("#posSearch").value = ""; filterProducts(); qs("#posSearch").focus(); });
  qsa(".category-ribbon button").forEach(btn => btn.addEventListener("click", () => { qsa(".category-ribbon button").forEach(b => b.classList.remove("active")); btn.classList.add("active"); filterProducts(); }));
  qsa("[data-pos-mode]").forEach(btn => btn.addEventListener("click", () => {
    qsa("[data-pos-mode]").forEach(b => b.classList.remove("active")); btn.classList.add("active");
    qsa("[data-mode-panel]").forEach(panel => panel.hidden = panel.dataset.modePanel !== btn.dataset.posMode);
    terminal().dataset.mode = btn.dataset.posMode;
    toast(`${btn.textContent.trim()} mode enabled`, "info");
  }));
  qs("#billDiscount").addEventListener("input", renderCart);
  qs("#couponCode").addEventListener("change", () => { qs("#couponCode").dataset.discount = "0"; renderCart(); });
  qs("#cartNotes").addEventListener("input", saveCartState);
  qs("#posCustomer").addEventListener("change", () => { updatePaymentModal(); saveCartState(); });
  qs("#topHoldBtn").addEventListener("click", holdCart);
  qs("#bottomHoldBtn").addEventListener("click", holdCart);
  qs("#topRecallBtn").addEventListener("click", showHeldBills);
  qs("#clearCartBtn").addEventListener("click", () => { if (POS.cart.length && confirm("Clear current cart?")) { POS.cart = []; clearCartState(); renderCart(); } });
  qs("#paymentBtn").addEventListener("click", () => { if (!POS.cart.length) return toast("Cart is empty", "warning"); buildPaymentRows("Cash"); new bootstrap.Modal(qs("#paymentModal")).show(); });
  qs("#printLastBtn").addEventListener("click", () => POS.lastReceiptUrl ? window.open(POS.lastReceiptUrl, "_blank") : toast("No receipt to print yet", "warning"));
  qs("#printLastQuick").addEventListener("click", () => qs("#printLastBtn").click());
  qs("#openPaymentQuick").addEventListener("click", () => qs("#paymentBtn").click());
  qs("#focusCustomer").addEventListener("click", () => qs("#posCustomer").focus());
  qs("#discountFocus").addEventListener("click", () => qs("#billDiscount").focus());
  qs("#fullscreenBtn").addEventListener("click", () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.());
  qs("#productSelectList").addEventListener("click", event => {
    const btn = event.target.closest("[data-choice]");
    if (!btn) return;
    const products = JSON.parse(qs("#productSelectList").dataset.products || "[]");
    addProduct(products[Number(btn.dataset.choice)]);
    bootstrap.Modal.getInstance(qs("#productSelectModal"))?.hide();
    qs("#posSearch").value = "";
    filterProducts();
  });
  qs("#saveLineDetail").addEventListener("click", saveLineDetail);
  qs("#heldSearch").addEventListener("input", renderHeldBills);
  qs("#heldBillsList").addEventListener("click", event => {
    const recall = event.target.closest("[data-recall]");
    const del = event.target.closest("[data-delete-held]");
    if (recall) recallHeld(recall.dataset.recall);
    if (del) deleteHeld(del.dataset.deleteHeld);
  });
  qsa("[data-payment-mode]").forEach(btn => btn.addEventListener("click", () => {
    qsa("[data-payment-mode]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    POS.paymentMode = btn.dataset.paymentMode;
    buildPaymentRows(POS.paymentMode);
  }));
  qs("#paymentRows").addEventListener("change", event => {
    const mode = event.target.closest("[data-pay-mode]");
    const amount = event.target.closest("[data-pay-amount]");
    if (mode) POS.paymentRows[Number(mode.dataset.payMode)].mode = mode.value;
    if (amount) POS.paymentRows[Number(amount.dataset.payAmount)].amount = money(amount.value);
    updatePaymentModal();
  });
  qs("#paymentRows").addEventListener("click", event => {
    const remove = event.target.closest("[data-pay-remove]");
    if (remove) { POS.paymentRows.splice(Number(remove.dataset.payRemove), 1); renderPaymentRows(); }
  });
  qs("#addPaymentRow").addEventListener("click", () => { POS.paymentRows.push({mode:"Cash", amount:0, reference:""}); POS.paymentMode = "Split"; renderPaymentRows(); });
  qsa(".complete-sale").forEach(btn => btn.addEventListener("click", () => completeSale(btn.dataset.after)));
  document.addEventListener("keydown", event => {
    if (event.key === "F2") { event.preventDefault(); qs("#posSearch").focus(); }
    if (event.key === "F3") { event.preventDefault(); qs("#posCustomer").focus(); }
    if (event.key === "F4") { event.preventDefault(); holdCart(); }
    if (event.key === "F5") { event.preventDefault(); showHeldBills(); }
    if (event.key === "F6") { event.preventDefault(); qs("#billDiscount").focus(); }
    if (event.key === "F7") { event.preventDefault(); qs("#paymentBtn").click(); }
    if (event.key === "F8") { event.preventDefault(); qs("#printLastBtn").click(); }
    if (event.key === "F9") { event.preventDefault(); qs("[data-bs-target='#cashMovementModal']")?.click(); }
    if (event.key === "F10") { event.preventDefault(); qs("[data-bs-target='#closeSessionModal']")?.click(); }
  });
  window.addEventListener("offline", () => {
    const pill = document.createElement("div");
    pill.className = "offline-pill";
    pill.textContent = "Offline - reconnect before checkout";
    pill.id = "offlinePill";
    document.body.appendChild(pill);
  });
  window.addEventListener("online", () => qs("#offlinePill")?.remove());
}

document.addEventListener("DOMContentLoaded", () => {
  bindCartEvents();
  bindStaticEvents();
  setInterval(() => { qs("#posClock").textContent = new Date().toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}); }, 1000);
  restoreCartState();
  renderCart();
  qs("#posSearch").focus();
});
