const cart = [];
let paymentMode = "Cash";
let scanBuffer = "";
let lastKey = 0;
let lastReceiptUrl = "";

function money(n) { return Number(n || 0); }
function csrfHeaders(extra = {}) {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  return Object.assign({"X-CSRFToken": token}, extra);
}
function showToast(message, type = "primary") {
  const host = document.querySelector("#posToastHost");
  if (!host) return alert(message);
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type} border-0`;
  el.role = "alert";
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  host.appendChild(el);
  const toast = new bootstrap.Toast(el, {delay: 3500});
  toast.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}
function lineBase(i) { return money(i.qty) * money(i.rate); }
function lineNet(i) { return lineBase(i) * (1 - money(i.discount) / 100); }
function lineTax(i) { return lineNet(i) * money(i.tax_rate) / 100; }
function totals() {
  const subtotal = cart.reduce((s, i) => s + lineNet(i), 0);
  const tax = cart.reduce((s, i) => s + lineTax(i), 0);
  const discount = Math.min(money(document.querySelector("#pos-discount").value), subtotal + tax);
  const total = Math.max(subtotal + tax - discount, 0);
  return {subtotal, tax, discount, total};
}
function updatePaymentHints() {
  const t = totals();
  const cash = money(document.querySelector("#cash-tendered").value);
  const card = money(document.querySelector("#card-amount").value);
  const upi = money(document.querySelector("#upi-amount").value);
  const wallet = money(document.querySelector("#wallet-amount").value);
  const received = paymentMode === "Credit" ? 0 : paymentMode === "Split" ? cash + card + upi + wallet : paymentMode === "Cash" ? cash || t.total : paymentMode === "Card" ? card || t.total : paymentMode === "UPI" ? upi || t.total : paymentMode === "Wallet" ? wallet || t.total : 0;
  document.querySelector("#payment-received").value = received.toFixed(2);
  document.querySelector("#change-due").value = Math.max(received - t.total, 0).toFixed(2);
}
function renderCart() {
  const holder = document.querySelector("#pos-cart");
  if (!holder) return;
  holder.innerHTML = cart.length ? cart.map((i, idx) => `
    <div class="cart-row" style="grid-template-columns:1fr 92px 90px 34px">
      <div>
        <strong>${i.name}</strong>
        <div class="stock-hint">${i.sku || ""} · Stock ${i.stock ?? ""}</div>
        <div class="d-flex gap-1 mt-1">
          <input class="form-control form-control-sm" value="${money(i.rate).toFixed(2)}" onchange="setRate(${idx},this.value)" aria-label="Rate">
          <input class="form-control form-control-sm" value="${money(i.discount)}" onchange="setDiscount(${idx},this.value)" aria-label="Discount percent" title="Line discount %">
        </div>
      </div>
      <div class="input-group input-group-sm">
        <button class="btn btn-outline-secondary" onclick="stepQty(${idx},-1)" type="button">-</button>
        <input class="form-control" value="${i.qty}" onchange="setQty(${idx},this.value)" aria-label="Quantity">
        <button class="btn btn-outline-secondary" onclick="stepQty(${idx},1)" type="button">+</button>
      </div>
      <strong class="text-end">${(lineNet(i) + lineTax(i)).toFixed(2)}</strong>
      <button class="btn btn-sm btn-outline-danger" onclick="removeItem(${idx})" type="button">&times;</button>
    </div>`).join("") : `<div class="text-muted text-center py-5">Cart is empty. Scan or tap products to add.</div>`;
  const t = totals();
  document.querySelector("#pos-subtotal").value = t.subtotal.toFixed(2);
  document.querySelector("#pos-tax").value = t.tax.toFixed(2);
  document.querySelector("#pos-total").value = t.total.toFixed(2);
  updatePaymentHints();
}
function addProduct(tile) {
  const id = tile.dataset.id;
  const existing = cart.find(i => String(i.product_id) === String(id));
  if (existing) existing.qty += 1;
  else cart.push({product_id:id, sku:tile.dataset.sku, name:tile.dataset.name, qty:1, rate:money(tile.dataset.rate), discount:0, tax_rate:money(tile.dataset.tax), stock:money(tile.dataset.stock)});
  renderCart();
}
function stepQty(i, delta) { cart[i].qty = Math.max(1, money(cart[i].qty) + delta); renderCart(); }
function setQty(i, value) { cart[i].qty = Math.max(1, money(value)); renderCart(); }
function setRate(i, value) { cart[i].rate = Math.max(0, money(value)); renderCart(); }
function setDiscount(i, value) { cart[i].discount = Math.min(100, Math.max(0, money(value))); renderCart(); }
function removeItem(i) { cart.splice(i, 1); renderCart(); }
function filterProducts() {
  const q = document.querySelector("#pos-search").value.toLowerCase();
  const category = document.querySelector(".category-chip.active")?.dataset.category || "all";
  document.querySelectorAll(".pos-product").forEach(tile => {
    tile.hidden = !((category === "all" || tile.dataset.category === category) && (!q || tile.dataset.search.includes(q) || tile.dataset.barcode === q));
  });
}
async function holdCart() {
  if (!cart.length) return showToast("Cart is empty.", "warning");
  const name = prompt("Hold bill note or customer name");
  if (!name) return;
  const shell = document.querySelector(".pos-shell");
  const res = await fetch("/pos/hold", {method:"POST", headers:csrfHeaders({"Content-Type":"application/json"}), body: JSON.stringify({customer_id:document.querySelector("#pos-customer").value, warehouse_id:shell.dataset.warehouseId, items:cart, notes:name})});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showToast(data.error || "Hold failed", "danger");
  showToast(`Held as ${data.hold_no}`, "success");
  cart.length = 0; renderCart();
}
async function showRecall() {
  const list = document.querySelector("#heldBillsList");
  list.innerHTML = `<div class="text-muted py-4 text-center">Loading held bills...</div>`;
  const modal = new bootstrap.Modal(document.querySelector("#recallModal"));
  modal.show();
  const res = await fetch("/pos/held.json");
  const data = await res.json().catch(() => ({data: []}));
  list.innerHTML = data.data.length ? data.data.map(row => `<button class="list-group-item list-group-item-action d-flex justify-content-between align-items-center recall-held" data-id="${row.id}" type="button"><span><strong>${row.hold_no}</strong><br><small>${row.customer} · ${row.notes || ""}</small></span><i class="bi bi-arrow-counterclockwise"></i></button>`).join("") : `<div class="text-muted py-4 text-center">No held bills found.</div>`;
}
async function recallHeld(id) {
  const res = await fetch(`/pos/held/${id}/json`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showToast(data.error || "Recall failed", "danger");
  cart.splice(0, cart.length, ...(data.items || []));
  if (data.customer_id) document.querySelector("#pos-customer").value = data.customer_id;
  renderCart();
  bootstrap.Modal.getInstance(document.querySelector("#recallModal"))?.hide();
  showToast("Held bill recalled.", "success");
}
async function chargeCart() {
  if (!cart.length) return showToast("Cart is empty.", "warning");
  const t = totals();
  const received = money(document.querySelector("#payment-received").value);
  if (paymentMode !== "Credit" && received < t.total) return showToast("Payment received is less than bill total.", "warning");
  const shell = document.querySelector(".pos-shell");
  const res = await fetch("/pos/sale", {method:"POST", headers:csrfHeaders({"Content-Type":"application/json"}), body: JSON.stringify({customer_id:document.querySelector("#pos-customer").value, warehouse_id:shell.dataset.warehouseId, items:cart, payment_mode:paymentMode, cash_tendered:document.querySelector("#cash-tendered").value, card_amount:document.querySelector("#card-amount").value, upi_amount:document.querySelector("#upi-amount").value, wallet_amount:document.querySelector("#wallet-amount").value, reference_no:document.querySelector("#reference-no").value, coupon_code:document.querySelector("#coupon-code").value, discount_total:document.querySelector("#pos-discount").value, delivery_bill:document.querySelector("#delivery-bill").checked})});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showToast(data.error || "Sale failed", "danger");
  document.querySelector("#receiptBody").innerHTML = `<p><strong>${data.invoice_no}</strong></p><p>Total: ${money(data.grand_total).toFixed(2)}<br>Change: ${money(data.change_due).toFixed(2)}</p>`;
  lastReceiptUrl = `/pos/receipt/${data.sale_id}`;
  document.querySelector("#printReceipt").href = lastReceiptUrl;
  new bootstrap.Modal(document.querySelector("#receiptModal")).show();
  cart.length = 0;
  ["#cash-tendered", "#card-amount", "#upi-amount", "#wallet-amount", "#reference-no", "#coupon-code", "#pos-discount"].forEach(sel => document.querySelector(sel).value = sel === "#pos-discount" ? "0" : "");
  renderCart();
  showToast("Sale completed.", "success");
}
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".pos-product").forEach(tile => tile.addEventListener("click", () => addProduct(tile)));
  document.querySelector("#pos-search").addEventListener("input", filterProducts);
  document.querySelector("#pos-search").addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      const exact = [...document.querySelectorAll(".pos-product")].find(t => t.dataset.barcode === e.target.value || t.dataset.sku?.toLowerCase() === e.target.value.toLowerCase());
      const tile = exact || [...document.querySelectorAll(".pos-product")].find(t => !t.hidden);
      if (tile) addProduct(tile);
      else showToast("No product found.", "warning");
      e.target.value = ""; filterProducts();
    }
  });
  document.querySelector("#pos-clear").addEventListener("click", () => { document.querySelector("#pos-search").value = ""; filterProducts(); document.querySelector("#pos-search").focus(); });
  document.querySelectorAll(".category-chip").forEach(btn => btn.addEventListener("click", () => { document.querySelectorAll(".category-chip").forEach(b => b.classList.remove("active")); btn.classList.add("active"); filterProducts(); }));
  document.querySelectorAll(".pay-mode").forEach(btn => btn.addEventListener("click", () => { document.querySelectorAll(".pay-mode").forEach(b => b.classList.remove("active")); btn.classList.add("active"); paymentMode = btn.dataset.mode; updatePaymentHints(); }));
  document.querySelectorAll("[data-pos-mode]").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll("[data-pos-mode]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    shell.classList.toggle("restaurant-mode", btn.dataset.posMode === "restaurant");
    showToast(`${btn.textContent.trim()} mode ready`, "info");
  }));
  ["#pos-discount", "#cash-tendered", "#card-amount", "#upi-amount", "#wallet-amount"].forEach(sel => document.querySelector(sel).addEventListener("input", renderCart));
  document.querySelector("#hold-cart").addEventListener("click", holdCart);
  document.querySelector("#recall-cart").addEventListener("click", showRecall);
  document.querySelector("#heldBillsList").addEventListener("click", e => { const btn = e.target.closest(".recall-held"); if (btn) recallHeld(btn.dataset.id); });
  document.querySelector("#cancel-cart").addEventListener("click", () => { if (!cart.length) return; if (prompt("Cancel bill reason")) { cart.length = 0; renderCart(); showToast("Bill cancelled.", "warning"); } });
  document.querySelector("#charge-btn").addEventListener("click", chargeCart);
  document.addEventListener("keydown", e => {
    if (e.key === "F2") { e.preventDefault(); document.querySelector("#pos-search").focus(); }
    if (e.key === "F3") { e.preventDefault(); document.querySelector("#pos-customer").focus(); }
    if (e.key === "F4") { e.preventDefault(); holdCart(); }
    if (e.key === "F5") { e.preventDefault(); showRecall(); }
    if (e.key === "F6") { e.preventDefault(); document.querySelector("#pos-discount").focus(); }
    if (e.key === "F7") { e.preventDefault(); document.querySelector("#charge-btn").focus(); }
    if (e.key === "F8") { e.preventDefault(); if (lastReceiptUrl) window.open(lastReceiptUrl, "_blank"); else showToast("No receipt to print yet.", "warning"); }
    if (e.key === "F9") { e.preventDefault(); document.querySelector("[data-bs-target='#cashMovementModal']")?.click(); }
    if (e.key === "F10") { e.preventDefault(); document.querySelector("[data-bs-target='#closeSessionModal']")?.click(); }
    const now = Date.now();
    if (e.key.length === 1 && document.activeElement !== document.querySelector("#pos-search")) scanBuffer = (now - lastKey < 50 ? scanBuffer : "") + e.key;
    if (e.key === "Enter" && scanBuffer.length > 3) {
      const tile = [...document.querySelectorAll(".pos-product")].find(t => t.dataset.barcode === scanBuffer);
      if (tile) addProduct(tile);
      scanBuffer = "";
    }
    lastKey = now;
  });
  renderCart();
});
