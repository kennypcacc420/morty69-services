let cart = JSON.parse(localStorage.getItem('morty69_cart') || '[]');
let adminKey = sessionStorage.getItem('morty69_admin_key') || '';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function saveCart() {
  localStorage.setItem('morty69_cart', JSON.stringify(cart));
  updateCartBadge();
}

function updateCartBadge() {
  const count = cart.reduce((sum, item) => sum + item.quantity, 0);
  $('#cart-badge').textContent = count;
}

function formatCash(n) {
  return Number(n).toFixed(2);
}

function statusBadge(status) {
  return `<span class="status-badge status-${status}">${status}</span>`;
}

async function api(url, options = {}) {
  const headers = { ...options.headers };
  if (adminKey && url.includes('/admin/')) {
    headers['x-admin-key'] = adminKey;
  }
  const res = await fetch(url, { ...options, headers });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function switchTab(tabName) {
  $$('.tab').forEach((t) => t.classList.remove('active'));
  $$('.nav-btn').forEach((b) => b.classList.remove('active'));
  $(`#tab-${tabName}`).classList.add('active');
  $(`.nav-btn[data-tab="${tabName}"]`).classList.add('active');
  if (tabName === 'store') loadProducts();
  if (tabName === 'cart') { renderCart(); loadQueue(); }
  if (tabName === 'trade') renderTradeTab();
  if (tabName === 'admin' && adminKey) loadAdminData();
}

$$('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

async function loadProducts() {
  try {
    const products = await api('/api/products');
    const grid = $('#products-grid');
    const empty = $('#products-empty');
    if (products.length === 0) {
      grid.innerHTML = '';
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    grid.innerHTML = products
      .map(
        (p) => `
        <div class="product-card">
          <img class="product-image" src="/uploads/${p.image_filename}" alt="${p.name}">
          <div class="product-body">
            <h3>${escapeHtml(p.name)}</h3>
            ${p.description ? `<p class="muted">${escapeHtml(p.description)}</p>` : ''}
            <div class="product-prices">
              <span class="price-rbx">${p.rbx_price} RBX</span>
              <span class="price-cash">$${formatCash(p.cash_price)}</span>
            </div>
            <button class="btn btn-primary btn-sm" onclick="addToCart(${p.id})">Add to Cart</button>
          </div>
        </div>`
      )
      .join('');
  } catch (err) {
    console.error(err);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

window.addToCart = function (productId) {
  const existing = cart.find((i) => i.product_id === productId);
  if (existing) {
    existing.quantity++;
  } else {
    cart.push({ product_id: productId, quantity: 1 });
  }
  saveCart();
};

async function renderCart() {
  const container = $('#cart-items');
  const empty = $('#cart-empty');
  const checkout = $('#checkout-panel');
  if (cart.length === 0) {
    container.innerHTML = '';
    empty.classList.remove('hidden');
    checkout.classList.add('hidden');
    return;
  }
  empty.classList.add('hidden');
  checkout.classList.remove('hidden');

  try {
    const products = await api('/api/products');
    let totalRbx = 0;
    let totalCash = 0;
    container.innerHTML = cart
      .map((item) => {
        const product = products.find((p) => p.id === item.product_id);
        if (!product) return '';
        totalRbx += product.rbx_price * item.quantity;
        totalCash += product.cash_price * item.quantity;
        return `
        <div class="cart-item">
          <img src="/uploads/${product.image_filename}" alt="${product.name}">
          <div class="cart-item-info">
            <strong>${escapeHtml(product.name)}</strong>
            <div class="muted">${product.rbx_price} RBX / $${formatCash(product.cash_price)} each</div>
          </div>
          <div class="cart-item-controls">
            <button onclick="changeQty(${product.id}, -1)">-</button>
            <span>${item.quantity}</span>
            <button onclick="changeQty(${product.id}, 1)">+</button>
            <button onclick="removeFromCart(${product.id})" style="margin-left:0.5rem;color:var(--danger)">✕</button>
          </div>
        </div>`;
      })
      .join('');
    $('#total-rbx').textContent = totalRbx;
    $('#total-cash').textContent = formatCash(totalCash);
  } catch (err) {
    console.error(err);
  }
}

window.changeQty = function (productId, delta) {
  const item = cart.find((i) => i.product_id === productId);
  if (!item) return;
  item.quantity += delta;
  if (item.quantity <= 0) {
    cart = cart.filter((i) => i.product_id !== productId);
  }
  saveCart();
  renderCart();
};

window.removeFromCart = function (productId) {
  cart = cart.filter((i) => i.product_id !== productId);
  saveCart();
  renderCart();
};

async function loadQueue() {
  try {
    const data = await api('/api/queue');
    $('#waiting-count').textContent = data.waitingCount;
    const list = $('#waiting-list');
    if (data.orders.length === 0) {
      list.innerHTML = '<p class="muted">No one waiting right now.</p>';
      return;
    }
    list.innerHTML = data.orders
      .map(
        (o, i) => `
        <div class="waiting-item">
          <span>#${i + 1} — ${escapeHtml(o.customer_name)}</span>
          <span>${statusBadge(o.status)}</span>
        </div>`
      )
      .join('');
  } catch (err) {
    console.error(err);
  }
}

const paymentMethodSelect = $('#payment-method');
if (paymentMethodSelect) {
  paymentMethodSelect.addEventListener('change', () => {
    const isTrade = paymentMethodSelect.value === 'trade';
    $('#payment-trade-note').classList.toggle('hidden', !isTrade);
  });
}

$('#place-order-btn').addEventListener('click', async () => {
  const name = $('#customer-name').value.trim();
  if (!name) {
    alert('Please enter your name');
    return;
  }
  if (cart.length === 0) {
    alert('Your cart is empty');
    return;
  }
  const paymentMethod = $('#payment-method') ? $('#payment-method').value : 'cashapp';
  if (paymentMethod === 'trade') {
    alert("To pay by trade, please use the Trade tab to upload a photo and description.");
    switchTab('trade');
    return;
  }
  try {
    const result = await api('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_name: name, items: cart, payment_method: paymentMethod }),
    });
    cart = [];
    saveCart();
    renderCart();
    $('#order-success').classList.remove('hidden');
    $('#success-order-code').textContent = result.order_code;
    $('#success-queue-pos').textContent = `#${result.queue_position} (${result.waiting_count} waiting)`;
    loadQueue();
  } catch (err) {
    alert(err.message);
  }
});

function renderTradeTab() {
  const locked = $('#trade-locked');
  const panel = $('#trade-panel');
  if (!locked || !panel) return;
  if (cart.length === 0) {
    locked.classList.remove('hidden');
    panel.classList.add('hidden');
  } else {
    locked.classList.add('hidden');
    panel.classList.remove('hidden');
  }
}

const tradeForm = $('#trade-form');
if (tradeForm) {
  tradeForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    if (cart.length === 0) {
      alert('Add at least 1 item to your cart before submitting a trade offer.');
      renderTradeTab();
      return;
    }

    const name = $('#trade-customer-name').value.trim();
    const description = $('#trade-description').value.trim();
    const imageInput = $('#trade-image');
    const imageFile = imageInput.files[0];

    if (!name) {
      alert('Please enter your name');
      return;
    }
    if (!imageFile) {
      alert('Please upload a JPG photo of what you are trading');
      return;
    }
    if (!description) {
      alert('Please describe what you are offering');
      return;
    }

    const formData = new FormData();
    formData.append('customer_name', name);
    formData.append('description', description);
    formData.append('items', JSON.stringify(cart));
    formData.append('image', imageFile);

    try {
      const result = await api('/api/orders/trade', {
        method: 'POST',
        body: formData,
      });
      cart = [];
      saveCart();
      tradeForm.reset();
      renderTradeTab();
      $('#trade-success').classList.remove('hidden');
      $('#trade-success-order-code').textContent = result.order_code;
      $('#trade-success-queue-pos').textContent = `#${result.queue_position} (${result.waiting_count} waiting)`;
      loadQueue();
    } catch (err) {
      alert(err.message);
    }
  });
}

$('#check-order-btn').addEventListener('click', async () => {
  const code = $('#check-order-code').value.trim().toUpperCase();
  if (!code) {
    alert('Enter your order code');
    return;
  }
  try {
    const order = await api(`/api/orders/${encodeURIComponent(code)}`);
    const result = $('#order-result');
    result.classList.remove('hidden');
    const itemsList = order.items
      .map((i) => `<li>${escapeHtml(i.name)} x${i.quantity}</li>`)
      .join('');
    result.innerHTML = `
      <div class="card">
        <h3>Order ${escapeHtml(order.order_code)}</h3>
        <dl>
          <dt>Customer</dt><dd>${escapeHtml(order.customer_name)}</dd>
          <dt>Status</dt><dd>${statusBadge(order.status)}</dd>
          <dt>Payment Method</dt><dd>${escapeHtml(order.payment_method || 'cashapp')}</dd>
          <dt>Est. Time</dt><dd>${order.est_time || 'Not set yet'}</dd>
          <dt>Queue Position</dt><dd>#${order.queue_position} (${order.waiting_count} waiting)</dd>
          <dt>Total RBX</dt><dd>${order.total_rbx}</dd>
          <dt>Total Cash</dt><dd>$${formatCash(order.total_cash)}</dd>
          <dt>Items</dt><dd><ul>${itemsList}</ul></dd>
          ${order.payment_method === 'trade' ? `<dt>Trade Offer</dt><dd>${escapeHtml(order.trade_description || '')}</dd>` : ''}
          <dt>Ordered</dt><dd>${new Date(order.created_at + 'Z').toLocaleString()}</dd>
        </dl>
      </div>`;
  } catch (err) {
    alert(err.message);
  }
});

$('#admin-login-btn').addEventListener('click', async () => {
  const key = $('#admin-key-input').value;
  try {
    await api('/api/admin/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    });
    adminKey = key;
    sessionStorage.setItem('morty69_admin_key', key);
    $('#admin-login').classList.add('hidden');
    $('#admin-panel').classList.remove('hidden');
    $('#admin-login-error').classList.add('hidden');
    loadAdminData();
  } catch {
    $('#admin-login-error').classList.remove('hidden');
  }
});

$('#admin-logout-btn').addEventListener('click', () => {
  adminKey = '';
  sessionStorage.removeItem('morty69_admin_key');
  $('#admin-login').classList.remove('hidden');
  $('#admin-panel').classList.add('hidden');
  $('#admin-key-input').value = '';
});

$('#add-product-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    await api('/api/admin/products', {
      method: 'POST',
      headers: { 'x-admin-key': adminKey },
      body: formData,
    });
    form.reset();
    loadAdminData();
    alert('Product added!');
  } catch (err) {
    alert(err.message);
  }
});

async function loadAdminData() {
  try {
    const [orders, products] = await Promise.all([
      api('/api/admin/orders'),
      api('/api/products'),
    ]);

    const ordersEl = $('#admin-orders');
    if (orders.length === 0) {
      ordersEl.innerHTML = '<p class="muted">No orders yet.</p>';
    } else {
      ordersEl.innerHTML = orders
        .map(
          (o) => `
          <div class="admin-order" data-id="${o.id}">
            <div class="admin-order-header">
              <strong>${escapeHtml(o.order_code)}</strong>
              ${statusBadge(o.status)}
            </div>
            <div>${escapeHtml(o.customer_name)} — ${o.total_rbx} RBX / $${formatCash(o.total_cash)}</div>
            <div class="muted">Payment: ${escapeHtml(o.payment_method || 'cashapp')}${o.payment_method === 'trade' ? ' — ' + escapeHtml(o.trade_description || '') : ''}</div>
            ${o.payment_method === 'trade' && o.trade_image_filename ? `<div><img src="/uploads/${o.trade_image_filename}" alt="Trade item" style="max-width:120px;border-radius:8px;margin-top:0.5rem;"></div>` : ''}
            <div class="admin-order-actions">
              <select class="status-select" data-id="${o.id}">
                <option value="waiting" ${o.status === 'waiting' ? 'selected' : ''}>Waiting</option>
                <option value="pending" ${o.status === 'pending' ? 'selected' : ''}>Pending</option>
                <option value="completed" ${o.status === 'completed' ? 'selected' : ''}>Completed</option>
              </select>
              <input type="text" class="est-time-input" data-id="${o.id}" placeholder="Est. time" value="${escapeHtml(o.est_time || '')}">
              <button class="btn btn-primary btn-sm update-order-btn" data-id="${o.id}">Update</button>
            </div>
          </div>`
        )
        .join('');
    }

    const productsEl = $('#admin-products');
    if (products.length === 0) {
      productsEl.innerHTML = '<p class="muted">No products yet.</p>';
    } else {
      productsEl.innerHTML = products
        .map(
          (p) => `
          <div class="admin-product-row">
            <span>${escapeHtml(p.name)} — ${p.rbx_price} RBX / $${formatCash(p.cash_price)}</span>
            <button class="btn btn-danger btn-sm" onclick="deleteProduct(${p.id})">Delete</button>
          </div>`
        )
        .join('');
    }
  } catch (err) {
    console.error(err);
  }
}

document.addEventListener('click', async (e) => {
  if (e.target.classList.contains('update-order-btn')) {
    const id = e.target.dataset.id;
    const status = document.querySelector(`.status-select[data-id="${id}"]`).value;
    const est_time = document.querySelector(`.est-time-input[data-id="${id}"]`).value;
    try {
      await api(`/api/admin/orders/${id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'x-admin-key': adminKey,
        },
        body: JSON.stringify({ status, est_time }),
      });
      loadAdminData();
    } catch (err) {
      alert(err.message);
    }
  }
});

window.deleteProduct = async function (id) {
  if (!confirm('Delete this product?')) return;
  try {
    await api(`/api/admin/products/${id}`, {
      method: 'DELETE',
      headers: { 'x-admin-key': adminKey },
    });
    loadAdminData();
    loadProducts();
  } catch (err) {
    alert(err.message);
  }
};

if (adminKey) {
  $('#admin-login').classList.add('hidden');
  $('#admin-panel').classList.remove('hidden');
}

updateCartBadge();
loadProducts();

setInterval(() => {
  const cartTab = $('#tab-cart');
  if (cartTab.classList.contains('active')) loadQueue();
}, 15000);
