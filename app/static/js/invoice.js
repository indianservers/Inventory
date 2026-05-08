function rowTemplate(products) {
  const options = products.map((p) => `<option value="${p.id}" data-price="${p.sales_price}" data-cost="${p.purchase_price}" data-tax="${p.tax_rate}" data-stock="${p.current_stock}">${p.sku} - ${p.name}${p.current_stock <= 0 ? " (Out)" : ""}</option>`).join("");
  return `<div class="item-row mb-2">
    <select name="product_id[]" class="form-select product-select" required><option value="">Product</option>${options}</select>
    <input name="quantity[]" class="form-control qty" type="number" min="0.001" step="0.001" value="1">
    <input name="rate[]" class="form-control rate" type="number" min="0" step="0.01" value="0">
    <input name="discount[]" class="form-control discount" type="number" min="0" step="0.01" value="0">
    <input name="tax_rate[]" class="form-control tax" type="number" min="0" step="0.01" value="0">
    <input class="form-control line-total" readonly value="0.00">
    <button class="btn btn-outline-danger remove-row" type="button"><i class="bi bi-trash"></i></button>
    <div class="stock-hint small text-muted"></div>
  </div>`;
}

async function initInvoiceForm(mode) {
  const holder = document.querySelector("#items");
  if (!holder) return;
  const products = await fetch("/api/products").then((r) => r.json());
  document.querySelector("#add-row").addEventListener("click", () => {
    holder.insertAdjacentHTML("beforeend", rowTemplate(products));
  });
  if (!holder.children.length) document.querySelector("#add-row").click();
  holder.addEventListener("change", (e) => {
    if (e.target.classList.contains("product-select")) {
      const opt = e.target.selectedOptions[0];
      const row = e.target.closest(".item-row");
      row.querySelector(".rate").value = mode === "purchase" ? opt.dataset.cost : opt.dataset.price;
      row.querySelector(".tax").value = opt.dataset.tax || 0;
      row.querySelector(".stock-hint").textContent = opt.value ? `Available: ${opt.dataset.stock || 0}` : "";
      calculateInvoice();
    }
  });
  holder.addEventListener("input", calculateInvoice);
  holder.addEventListener("click", (e) => {
    if (e.target.closest(".remove-row")) {
      e.target.closest(".item-row").remove();
      calculateInvoice();
    }
  });
  document.querySelectorAll("#paid_amount,#shipping_charges,#other_charges,#round_off").forEach((el) => el?.addEventListener("input", calculateInvoice));
  document.querySelector("#pay-full")?.addEventListener("click", () => {
    const grand = document.querySelector("#grand_total")?.value || 0;
    document.querySelector("#paid_amount").value = grand;
    calculateInvoice();
  });
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
  document.querySelector("#subtotal").value = subtotal.toFixed(2);
  document.querySelector("#discount_total").value = discountTotal.toFixed(2);
  document.querySelector("#tax_total").value = taxTotal.toFixed(2);
  document.querySelector("#grand_total").value = grand.toFixed(2);
  document.querySelector("#balance_amount").value = (grand - paid).toFixed(2);
  document.querySelector("#payment_status").value = paid <= 0 ? "Unpaid" : (paid >= grand ? "Paid" : "Partial");
}
