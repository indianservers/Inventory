const cart = [];
let paymentMode = "Cash";
let scanBuffer = "";
let lastKey = 0;

function money(n) { return Number(n || 0); }
function renderCart() {
  const holder = document.querySelector("#pos-cart");
  holder.innerHTML = cart.map((i, idx) => `<div class="cart-row" style="grid-template-columns:1fr 78px 86px 32px"><div><strong>${i.name}</strong><div class="stock-hint">${i.rate.toFixed(2)} x ${i.qty}</div></div><div class="input-group input-group-sm"><button class="btn btn-outline-secondary" onclick="stepQty(${idx},-1)">-</button><input class="form-control" value="${i.qty}" onchange="setQty(${idx},this.value)"><button class="btn btn-outline-secondary" onclick="stepQty(${idx},1)">+</button></div><strong class="text-end">${(i.qty * i.rate).toFixed(2)}</strong><button class="btn btn-sm btn-outline-danger" onclick="removeItem(${idx})">&times;</button></div>`).join("");
  const subtotal = cart.reduce((s, i) => s + i.qty * i.rate, 0);
  const discount = money(document.querySelector("#pos-discount").value);
  const tax = cart.reduce((s, i) => s + ((i.qty * i.rate) * i.tax_rate / 100), 0);
  document.querySelector("#pos-subtotal").value = subtotal.toFixed(2);
  document.querySelector("#pos-tax").value = tax.toFixed(2);
  document.querySelector("#pos-total").value = (subtotal + tax - discount).toFixed(2);
}
function addProduct(tile) {
  const id = tile.dataset.id;
  const existing = cart.find(i => i.product_id === id);
  if (existing) existing.qty += 1;
  else cart.push({product_id:id, name:tile.dataset.name, qty:1, rate:money(tile.dataset.rate), discount:0, tax_rate:money(tile.dataset.tax)});
  renderCart();
}
function stepQty(i, delta) { cart[i].qty = Math.max(1, money(cart[i].qty) + delta); renderCart(); }
function setQty(i, value) { cart[i].qty = Math.max(1, money(value)); renderCart(); }
function removeItem(i) { cart.splice(i, 1); renderCart(); }
function filterProducts() {
  const q = document.querySelector("#pos-search").value.toLowerCase();
  const category = document.querySelector(".category-chip.active")?.dataset.category || "all";
  document.querySelectorAll(".pos-product").forEach(tile => tile.hidden = !((category === "all" || tile.dataset.category === category) && (!q || tile.dataset.search.includes(q) || tile.dataset.barcode === q)));
}
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".pos-product").forEach(tile => tile.addEventListener("click", () => addProduct(tile)));
  document.querySelector("#pos-search").addEventListener("input", filterProducts);
  document.querySelector("#pos-search").addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      const tile = [...document.querySelectorAll(".pos-product")].find(t => !t.hidden);
      if (tile) addProduct(tile);
      e.target.value = ""; filterProducts();
    }
  });
  document.querySelectorAll(".category-chip").forEach(btn => btn.addEventListener("click", () => { document.querySelectorAll(".category-chip").forEach(b => b.classList.remove("active")); btn.classList.add("active"); filterProducts(); }));
  document.querySelectorAll(".pay-mode").forEach(btn => btn.addEventListener("click", () => { document.querySelectorAll(".pay-mode").forEach(b => b.classList.remove("active")); btn.classList.add("active"); paymentMode = btn.dataset.mode; }));
  document.querySelector("#pos-discount").addEventListener("input", renderCart);
  document.querySelector("#hold-cart").addEventListener("click", () => { const name = prompt("Hold slot name"); if (name) localStorage.setItem(`pos-hold-${name}`, JSON.stringify(cart)); });
  document.querySelector("#recall-cart").addEventListener("click", () => { const keys = Object.keys(localStorage).filter(k => k.startsWith("pos-hold-")); const key = prompt(`Recall slot:\n${keys.map(k => k.replace("pos-hold-","")).join("\n")}`); const data = key && localStorage.getItem(`pos-hold-${key}`); if (data) { cart.splice(0, cart.length, ...JSON.parse(data)); renderCart(); } });
  document.querySelector("#charge-btn").addEventListener("click", async () => {
    const shell = document.querySelector(".pos-shell");
    const res = await fetch("/pos/sale", {method:"POST", headers:{"Content-Type":"application/json", "X-CSRFToken":document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify({customer_id:document.querySelector("#pos-customer").value, warehouse_id:shell.dataset.warehouseId, items:cart, payment_mode:paymentMode, cash_tendered:document.querySelector("#cash-tendered").value, card_amount:document.querySelector("#card-amount").value, upi_amount:document.querySelector("#upi-amount").value, reference_no:document.querySelector("#reference-no").value, discount_total:document.querySelector("#pos-discount").value})});
    const data = await res.json();
    if (!res.ok) return alert(data.error || "Sale failed");
    document.querySelector("#receiptBody").innerHTML = `<p><strong>${data.invoice_no}</strong></p><p>Total: ${data.grand_total.toFixed(2)}<br>Change: ${data.change_due.toFixed(2)}</p>`;
    document.querySelector("#printReceipt").href = `/pos/receipt/${data.sale_id}`;
    new bootstrap.Modal(document.querySelector("#receiptModal")).show();
    cart.length = 0; renderCart();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "F2") { e.preventDefault(); document.querySelector("#pos-search").focus(); }
    if (e.key === "F4") { e.preventDefault(); document.querySelector("#pos-discount").focus(); }
    if (e.key === "F8") { e.preventDefault(); document.querySelector("#hold-cart").click(); }
    if (e.key === "F12") { e.preventDefault(); document.querySelector("#charge-btn").click(); }
    const now = Date.now();
    if (e.key.length === 1) scanBuffer = (now - lastKey < 50 ? scanBuffer : "") + e.key;
    if (e.key === "Enter" && scanBuffer.length > 3) {
      const tile = [...document.querySelectorAll(".pos-product")].find(t => t.dataset.barcode === scanBuffer);
      if (tile) addProduct(tile);
      scanBuffer = "";
    }
    lastKey = now;
  });
  renderCart();
});
