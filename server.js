const express = require('express');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const { v4: uuidv4 } = require('uuid');
const db = require('./db');

const app = express();
const PORT = process.env.PORT || 3000;
const ADMIN_KEY = process.env.ADMIN_KEY || 'Morty666';
const DISCORD_WEBHOOK =
  process.env.DISCORD_WEBHOOK ||
  'https://discord.com/api/webhooks/1538332569102319616/-Ltcb2L4u0oEiHPz4e10_WqgkBf0NJFdhrkjXsLdxPperMCH-4WSPgSjkPFsReAkp313';

const dataDir = path.join(__dirname, 'data');
const uploadsDir = path.join(dataDir, 'uploads');
[dataDir, uploadsDir].forEach((dir) => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(uploadsDir));

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadsDir),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase() || '.jpg';
    cb(null, `${Date.now()}-${uuidv4()}${ext}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 5 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const allowed = ['.jpg', '.jpeg'];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) {
      cb(null, true);
    } else {
      cb(new Error('Only JPG image files are allowed'));
    }
  },
});

function generateOrderCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = 'M69-';
  for (let i = 0; i < 8; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
}

function getWaitingCount() {
  const row = db
    .prepare("SELECT COUNT(*) as count FROM orders WHERE status IN ('waiting', 'pending')")
    .get();
  return row.count;
}

async function sendDiscordNotification(order) {
  const items = JSON.parse(order.items_json);
  const itemLines = items
    .map(
      (item) =>
        `• ${item.name} x${item.quantity} — ${item.rbx_price} RBX / $${item.cash_price.toFixed(2)}`
    )
    .join('\n');

  const embed = {
    title: '🛒 New Order — Morty69 Services',
    color: 0x7c3aed,
    fields: [
      { name: 'Order Code', value: `\`${order.order_code}\``, inline: true },
      { name: 'Customer', value: order.customer_name, inline: true },
      { name: 'Status', value: order.status, inline: true },
      { name: 'Items', value: itemLines || 'None', inline: false },
      {
        name: 'Totals',
        value: `${order.total_rbx} RBX / $${order.total_cash.toFixed(2)}`,
        inline: false,
      },
      { name: 'Queue Position', value: String(getWaitingCount()), inline: true },
    ],
    timestamp: new Date().toISOString(),
  };

  try {
    await fetch(DISCORD_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ embeds: [embed] }),
    });
  } catch (err) {
    console.error('Discord webhook failed:', err.message);
  }
}

function requireAdmin(req, res, next) {
  const key = req.headers['x-admin-key'];
  if (key !== ADMIN_KEY) {
    return res.status(401).json({ error: 'Invalid admin key' });
  }
  next();
}

app.get('/api/products', (_req, res) => {
  const products = db.prepare('SELECT * FROM products ORDER BY created_at DESC').all();
  res.json(products);
});

app.get('/api/queue', (_req, res) => {
  const waitingCount = getWaitingCount();
  const orders = db
    .prepare(
      "SELECT id, order_code, customer_name, status, est_time, created_at FROM orders WHERE status IN ('waiting', 'pending') ORDER BY created_at ASC"
    )
    .all();
  res.json({ waitingCount, orders });
});

app.post('/api/orders', (req, res) => {
  const { customer_name, items } = req.body;

  if (!customer_name || !items || !Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ error: 'Customer name and items are required' });
  }

  let totalRbx = 0;
  let totalCash = 0;
  const orderItems = [];

  for (const item of items) {
    const product = db.prepare('SELECT * FROM products WHERE id = ?').get(item.product_id);
    if (!product) {
      return res.status(400).json({ error: `Product ${item.product_id} not found` });
    }
    const qty = Math.max(1, parseInt(item.quantity, 10) || 1);
    totalRbx += product.rbx_price * qty;
    totalCash += product.cash_price * qty;
    orderItems.push({
      product_id: product.id,
      name: product.name,
      quantity: qty,
      rbx_price: product.rbx_price * qty,
      cash_price: product.cash_price * qty,
    });
  }

  let orderCode = generateOrderCode();
  let attempts = 0;
  while (attempts < 10) {
    try {
      const result = db
        .prepare(
          `INSERT INTO orders (order_code, customer_name, items_json, total_rbx, total_cash, status)
           VALUES (?, ?, ?, ?, ?, 'waiting')`
        )
        .run(orderCode, customer_name.trim(), JSON.stringify(orderItems), totalRbx, totalCash);

      const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(result.lastInsertRowid);
      sendDiscordNotification(order);

      const queuePosition = getWaitingCount();
      return res.json({
        order_code: order.order_code,
        status: order.status,
        queue_position: queuePosition,
        waiting_count: queuePosition,
      });
    } catch (err) {
      if (err.message.includes('UNIQUE')) {
        orderCode = generateOrderCode();
        attempts++;
      } else {
        throw err;
      }
    }
  }

  res.status(500).json({ error: 'Could not create order' });
});

app.get('/api/orders/:code', (req, res) => {
  const order = db
    .prepare('SELECT * FROM orders WHERE order_code = ?')
    .get(req.params.code.toUpperCase());

  if (!order) {
    return res.status(404).json({ error: 'Order not found' });
  }

  const ahead = db
    .prepare(
      `SELECT COUNT(*) as count FROM orders
       WHERE status IN ('waiting', 'pending')
       AND created_at < ?
       AND id != ?`
    )
    .get(order.created_at, order.id);

  res.json({
    ...order,
    items: JSON.parse(order.items_json),
    queue_position: order.status === 'completed' ? 0 : ahead.count + 1,
    waiting_count: getWaitingCount(),
  });
});

app.post('/api/admin/verify', (req, res) => {
  if (req.body.key === ADMIN_KEY) {
    return res.json({ success: true });
  }
  res.status(401).json({ error: 'Invalid admin key' });
});

app.get('/api/admin/orders', requireAdmin, (_req, res) => {
  const orders = db.prepare('SELECT * FROM orders ORDER BY created_at DESC').all();
  res.json(
    orders.map((o) => ({
      ...o,
      items: JSON.parse(o.items_json),
    }))
  );
});

app.patch('/api/admin/orders/:id', requireAdmin, (req, res) => {
  const { status, est_time } = req.body;
  const validStatuses = ['waiting', 'pending', 'completed'];

  if (status && !validStatuses.includes(status)) {
    return res.status(400).json({ error: 'Invalid status' });
  }

  const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!order) {
    return res.status(404).json({ error: 'Order not found' });
  }

  db.prepare(
    `UPDATE orders SET status = ?, est_time = ?, updated_at = datetime('now') WHERE id = ?`
  ).run(status || order.status, est_time ?? order.est_time, req.params.id);

  const updated = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  res.json({ ...updated, items: JSON.parse(updated.items_json) });
});

app.post('/api/admin/products', requireAdmin, upload.single('image'), (req, res) => {
  const { name, description, rbx_price, cash_price } = req.body;

  if (!name || !req.file) {
    return res.status(400).json({ error: 'Name and JPG image are required' });
  }

  const result = db
    .prepare(
      `INSERT INTO products (name, description, image_filename, rbx_price, cash_price)
       VALUES (?, ?, ?, ?, ?)`
    )
    .run(
      name.trim(),
      (description || '').trim(),
      req.file.filename,
      parseFloat(rbx_price) || 0,
      parseFloat(cash_price) || 0
    );

  const product = db.prepare('SELECT * FROM products WHERE id = ?').get(result.lastInsertRowid);
  res.json(product);
});

app.delete('/api/admin/products/:id', requireAdmin, (req, res) => {
  const product = db.prepare('SELECT * FROM products WHERE id = ?').get(req.params.id);
  if (!product) {
    return res.status(404).json({ error: 'Product not found' });
  }

  const imagePath = path.join(uploadsDir, product.image_filename);
  if (fs.existsSync(imagePath)) {
    fs.unlinkSync(imagePath);
  }

  db.prepare('DELETE FROM products WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(400).json({ error: err.message || 'Something went wrong' });
});

app.get('*', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Morty69 Services running on port ${PORT}`);
});
