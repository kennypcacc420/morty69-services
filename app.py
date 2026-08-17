import json
import os
import random
import sqlite3
import string
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PUBLIC_DIR = BASE_DIR / "public"
DB_PATH = DATA_DIR / "store.db"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "Morty666")
DISCORD_WEBHOOK = os.environ.get(
    "DISCORD_WEBHOOK",
    "https://discord.com/api/webhooks/1538332569102319616/-Ltcb2L4u0oEiHPz4e10_WqgkBf0NJFdhrkjXsLdxPperMCH-4WSPgSjkPFsReAkp313",
)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg"}

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            image_filename TEXT NOT NULL,
            rbx_price REAL NOT NULL DEFAULT 0,
            cash_price REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total_rbx REAL NOT NULL DEFAULT 0,
            total_cash REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'waiting',
            est_time TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def generate_order_code():
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "M69-" + "".join(random.choice(chars) for _ in range(8))


def get_waiting_count(conn):
    row = conn.execute(
        "SELECT COUNT(*) as count FROM orders WHERE status IN ('waiting', 'pending')"
    ).fetchone()
    return row["count"]


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def send_discord_notification(order, waiting_count):
    items = json.loads(order["items_json"])
    item_lines = "\n".join(
        f"• {item['name']} x{item['quantity']} — {item['rbx_price']} RBX / ${item['cash_price']:.2f}"
        for item in items
    )

    embed = {
        "title": "🛒 New Order — Morty69 Services",
        "color": 0x7C3AED,
        "fields": [
            {"name": "Order Code", "value": f"`{order['order_code']}`", "inline": True},
            {"name": "Customer", "value": order["customer_name"], "inline": True},
            {"name": "Status", "value": order["status"], "inline": True},
            {"name": "Items", "value": item_lines or "None", "inline": False},
            {
                "name": "Totals",
                "value": f"{order['total_rbx']} RBX / ${order['total_cash']:.2f}",
                "inline": False,
            },
            {"name": "Queue Position", "value": str(waiting_count), "inline": True},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    except Exception as exc:
        print(f"Discord webhook failed: {exc}")


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get("x-admin-key") != ADMIN_KEY:
            return jsonify({"error": "Invalid admin key"}), 401
        return f(*args, **kwargs)

    return decorated


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOADS_DIR, filename)


@app.route("/api/products", methods=["GET"])
def list_products():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([row_to_dict(p) for p in products])


@app.route("/api/queue", methods=["GET"])
def queue_info():
    conn = get_db()
    waiting_count = get_waiting_count(conn)
    orders = conn.execute(
        """
        SELECT id, order_code, customer_name, status, est_time, created_at
        FROM orders
        WHERE status IN ('waiting', 'pending')
        ORDER BY created_at ASC
        """
    ).fetchall()
    conn.close()
    return jsonify({"waitingCount": waiting_count, "orders": [row_to_dict(o) for o in orders]})


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    customer_name = (data.get("customer_name") or "").strip()
    items = data.get("items") or []

    if not customer_name or not items:
        return jsonify({"error": "Customer name and items are required"}), 400

    conn = get_db()
    total_rbx = 0.0
    total_cash = 0.0
    order_items = []

    for item in items:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (item.get("product_id"),)
        ).fetchone()
        if not product:
            conn.close()
            return jsonify({"error": f"Product {item.get('product_id')} not found"}), 400

        qty = max(1, int(item.get("quantity") or 1))
        total_rbx += product["rbx_price"] * qty
        total_cash += product["cash_price"] * qty
        order_items.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "quantity": qty,
                "rbx_price": product["rbx_price"] * qty,
                "cash_price": product["cash_price"] * qty,
            }
        )

    for _ in range(10):
        order_code = generate_order_code()
        try:
            cursor = conn.execute(
                """
                INSERT INTO orders (order_code, customer_name, items_json, total_rbx, total_cash, status)
                VALUES (?, ?, ?, ?, ?, 'waiting')
                """,
                (order_code, customer_name, json.dumps(order_items), total_rbx, total_cash),
            )
            conn.commit()
            order = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            order_dict = row_to_dict(order)
            waiting_count = get_waiting_count(conn)
            conn.close()
            send_discord_notification(order_dict, waiting_count)
            return jsonify(
                {
                    "order_code": order_dict["order_code"],
                    "status": order_dict["status"],
                    "queue_position": waiting_count,
                    "waiting_count": waiting_count,
                }
            )
        except sqlite3.IntegrityError:
            continue

    conn.close()
    return jsonify({"error": "Could not create order"}), 500


@app.route("/api/orders/<code>", methods=["GET"])
def get_order(code):
    conn = get_db()
    order = conn.execute(
        "SELECT * FROM orders WHERE order_code = ?", (code.upper(),)
    ).fetchone()

    if not order:
        conn.close()
        return jsonify({"error": "Order not found"}), 404

    ahead = conn.execute(
        """
        SELECT COUNT(*) as count FROM orders
        WHERE status IN ('waiting', 'pending')
        AND created_at < ?
        AND id != ?
        """,
        (order["created_at"], order["id"]),
    ).fetchone()

    waiting_count = get_waiting_count(conn)
    conn.close()

    result = row_to_dict(order)
    result["items"] = json.loads(order["items_json"])
    result["queue_position"] = 0 if order["status"] == "completed" else ahead["count"] + 1
    result["waiting_count"] = waiting_count
    return jsonify(result)


@app.route("/api/admin/verify", methods=["POST"])
def verify_admin():
    data = request.get_json(silent=True) or {}
    if data.get("key") == ADMIN_KEY:
        return jsonify({"success": True})
    return jsonify({"error": "Invalid admin key"}), 401


@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def admin_orders():
    conn = get_db()
    orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify(
        [{**row_to_dict(o), "items": json.loads(o["items_json"])} for o in orders]
    )


@app.route("/api/admin/orders/<int:order_id>", methods=["PATCH"])
@require_admin
def update_order(order_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    est_time = data.get("est_time")

    valid_statuses = {"waiting", "pending", "completed"}
    if status and status not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"error": "Order not found"}), 404

    conn.execute(
        """
        UPDATE orders
        SET status = ?, est_time = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (status or order["status"], est_time if est_time is not None else order["est_time"], order_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    result = row_to_dict(updated)
    result["items"] = json.loads(updated["items_json"])
    return jsonify(result)


@app.route("/api/admin/products", methods=["POST"])
@require_admin
def create_product():
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    rbx_price = float(request.form.get("rbx_price") or 0)
    cash_price = float(request.form.get("cash_price") or 0)
    image = request.files.get("image")

    if not name or not image or not image.filename:
        return jsonify({"error": "Name and JPG image are required"}), 400

    if not allowed_file(image.filename):
        return jsonify({"error": "Only JPG image files are allowed"}), 400

    ext = Path(image.filename).suffix.lower()
    filename = f"{int(datetime.now().timestamp())}-{uuid.uuid4().hex}{ext}"
    image.save(UPLOADS_DIR / filename)

    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO products (name, description, image_filename, rbx_price, cash_price)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, description, filename, rbx_price, cash_price),
    )
    conn.commit()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(product))


@app.route("/api/admin/products/<int:product_id>", methods=["DELETE"])
@require_admin
def delete_product(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    image_path = UPLOADS_DIR / product["image_filename"]
    if image_path.exists():
        image_path.unlink()

    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.errorhandler(Exception)
def handle_error(exc):
    print(exc)
    return jsonify({"error": str(exc)}), 400


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
