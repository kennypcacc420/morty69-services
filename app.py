import json
import os
import random
import string
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from supabase import create_client, Client

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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oioanrtwguzoxvdrlqeu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9pb2FucnR3Z3V6b3h2ZHJscWV1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY5OTY4NzAsImV4cCI6MjEwMjU3Mjg3MH0.l7KnSbzKKd-EB9bHUZQQVRUuZowMZhHaM9zUzDWqa5s")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg"}
PAYMENT_METHODS = {"cashapp", "paypal", "chime", "robux", "trade"}

STORAGE_BUCKET = "product-images"

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def generate_order_code():
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "M69-" + "".join(random.choice(chars) for _ in range(8))


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def upload_image_to_supabase(image_file, filename_prefix=""):
    """Uploads a Flask FileStorage image to the Supabase Storage bucket and returns its public URL."""
    ext = Path(image_file.filename).suffix.lower()
    filename = f"{filename_prefix}{int(datetime.now().timestamp())}-{uuid.uuid4().hex}{ext}"
    image_bytes = image_file.read()
    supabase.storage.from_(STORAGE_BUCKET).upload(
        filename,
        image_bytes,
        {"content-type": image_file.mimetype or "image/jpeg"},
    )
    return supabase.storage.from_(STORAGE_BUCKET).get_public_url(filename), filename


def send_discord_notification(order, waiting_count):
    items = json.loads(order["items_json"])
    item_lines = "\n".join(
        f"• {item['name']} x{item['quantity']} — {item['rbx_price']} RBX / ${item['cash_price']:.2f}"
        for item in items
    )

    fields = [
        {"name": "Order Code", "value": f"`{order['order_code']}`", "inline": True},
        {"name": "Customer", "value": order["customer_name"], "inline": True},
        {"name": "Status", "value": order["status"], "inline": True},
        {"name": "Payment Method", "value": order["payment_method"], "inline": True},
        {"name": "Items", "value": item_lines or "None", "inline": False},
        {
            "name": "Totals",
            "value": f"{order['total_rbx']} RBX / ${order['total_cash']:.2f}",
            "inline": False,
        },
        {"name": "Queue Position", "value": str(waiting_count), "inline": True},
    ]

    if order["payment_method"] == "trade":
        fields.append(
            {
                "name": "Trade Offer",
                "value": order["trade_description"] or "No description provided",
                "inline": False,
            }
        )

    embed = {
        "title": "🛒 New Order — Morty69 Services",
        "color": 0x7C3AED,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if order["payment_method"] == "trade" and order["trade_image_filename"]:
        embed["image"] = {"url": f"/uploads/{order['trade_image_filename']}"}

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
    try:
        response = supabase.table("products").select("*").order("created_at", desc=True).execute()
        return jsonify(response.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue", methods=["GET"])
def queue_info():
    try:
        response = supabase.table("orders").select(
            "id, order_code, customer_name, status, est_time, created_at"
        ).in_("status", ["waiting", "pending"]).order("created_at", desc=False).execute()

        waiting_count = len(response.data)
        return jsonify({"waitingCount": waiting_count, "orders": response.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _build_order_items(items):
    """Validate cart items against products and return (order_items, total_rbx, total_cash) or an error dict."""
    total_rbx = 0.0
    total_cash = 0.0
    order_items = []

    try:
        products_response = supabase.table("products").select("*").execute()
        products = {p["id"]: p for p in products_response.data}
    except Exception as e:
        return {"error": f"Database error: {str(e)}"}

    for item in items:
        product_id = item.get("product_id")
        if product_id not in products:
            return {"error": f"Product {product_id} not found"}

        product = products[product_id]
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

    return order_items, total_rbx, total_cash


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    customer_name = (data.get("customer_name") or "").strip()
    items = data.get("items") or []
    payment_method = (data.get("payment_method") or "cashapp").strip().lower()

    if not customer_name or not items:
        return jsonify({"error": "Customer name and items are required"}), 400

    if payment_method not in PAYMENT_METHODS:
        return jsonify({"error": "Invalid payment method"}), 400

    if payment_method == "trade":
        return (
            jsonify({"error": "Use the Trade tab to submit a trade offer with an image"}),
            400,
        )

    built = _build_order_items(items)
    if isinstance(built, dict):
        return jsonify(built), 400
    order_items, total_rbx, total_cash = built

    for _ in range(10):
        order_code = generate_order_code()
        try:
            order_data = {
                "order_code": order_code,
                "customer_name": customer_name,
                "items_json": json.dumps(order_items),
                "total_rbx": total_rbx,
                "total_cash": total_cash,
                "status": "waiting",
                "payment_method": payment_method,
            }
            response = supabase.table("orders").insert(order_data).execute()
            order = response.data[0]

            waiting_response = supabase.table("orders").select("id").in_(
                "status", ["waiting", "pending"]
            ).execute()
            waiting_count = len(waiting_response.data)

            send_discord_notification(order, waiting_count)
            return jsonify(
                {
                    "order_code": order["order_code"],
                    "status": order["status"],
                    "queue_position": waiting_count,
                    "waiting_count": waiting_count,
                }
            )
        except Exception as e:
            if "duplicate" in str(e).lower():
                continue
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Could not create order"}), 500


@app.route("/api/orders/trade", methods=["POST"])
def create_trade_order():
    customer_name = (request.form.get("customer_name") or "").strip()
    description = (request.form.get("description") or "").strip()
    items_raw = request.form.get("items") or "[]"
    image = request.files.get("image")

    try:
        items = json.loads(items_raw)
    except (TypeError, ValueError):
        items = []

    if not customer_name:
        return jsonify({"error": "Name is required"}), 400

    if not items:
        return jsonify({"error": "You need at least 1 item in your cart to trade"}), 400

    if not image or not image.filename:
        return jsonify({"error": "A JPG image of what you're trading is required"}), 400

    if not allowed_file(image.filename):
        return jsonify({"error": "Only JPG image files are allowed"}), 400

    if not description:
        return jsonify({"error": "A description of what you're offering is required"}), 400

    built = _build_order_items(items)
    if isinstance(built, dict):
        return jsonify(built), 400
    order_items, total_rbx, total_cash = built

    try:
        trade_image_url, trade_filename = upload_image_to_supabase(image, filename_prefix="trade-")
    except Exception as e:
        return jsonify({"error": f"Image upload failed: {str(e)}"}), 500

    for _ in range(10):
        order_code = generate_order_code()
        try:
            order_data = {
                "order_code": order_code,
                "customer_name": customer_name,
                "items_json": json.dumps(order_items),
                "total_rbx": total_rbx,
                "total_cash": total_cash,
                "status": "waiting",
                "payment_method": "trade",
                "trade_image_filename": trade_image_url,
                "trade_description": description,
            }
            response = supabase.table("orders").insert(order_data).execute()
            order = response.data[0]

            waiting_response = supabase.table("orders").select("id").in_(
                "status", ["waiting", "pending"]
            ).execute()
            waiting_count = len(waiting_response.data)

            send_discord_notification(order, waiting_count)
            return jsonify(
                {
                    "order_code": order["order_code"],
                    "status": order["status"],
                    "queue_position": waiting_count,
                    "waiting_count": waiting_count,
                }
            )
        except Exception as e:
            if "duplicate" in str(e).lower():
                continue
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Could not create trade order"}), 500


@app.route("/api/orders/<code>", methods=["GET"])
def get_order(code):
    try:
        response = supabase.table("orders").select("*").eq(
            "order_code", code.upper()
        ).execute()

        if not response.data:
            return jsonify({"error": "Order not found"}), 404

        order = response.data[0]

        ahead_response = supabase.table("orders").select("id").in_(
            "status", ["waiting", "pending"]
        ).lt("created_at", order["created_at"]).execute()
        ahead_count = len(ahead_response.data)

        waiting_response = supabase.table("orders").select("id").in_(
            "status", ["waiting", "pending"]
        ).execute()
        waiting_count = len(waiting_response.data)

        order["items"] = json.loads(order["items_json"])
        order["queue_position"] = 0 if order["status"] == "completed" else ahead_count + 1
        order["waiting_count"] = waiting_count
        return jsonify(order)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/verify", methods=["POST"])
def verify_admin():
    data = request.get_json(silent=True) or {}
    if data.get("key") == ADMIN_KEY:
        return jsonify({"success": True})
    return jsonify({"error": "Invalid admin key"}), 401


@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def admin_orders():
    try:
        response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
        for order in response.data:
            order["items"] = json.loads(order["items_json"])
        return jsonify(response.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/orders/<int:order_id>", methods=["PATCH"])
@require_admin
def update_order(order_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    est_time = data.get("est_time")

    valid_statuses = {"waiting", "pending", "completed"}
    if status and status not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    try:
        order_response = supabase.table("orders").select("*").eq("id", order_id).execute()
        if not order_response.data:
            return jsonify({"error": "Order not found"}), 404

        current_order = order_response.data[0]
        update_data = {
            "status": status or current_order["status"],
            "est_time": est_time if est_time is not None else current_order["est_time"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        response = supabase.table("orders").update(update_data).eq("id", order_id).execute()
        updated = response.data[0]
        updated["items"] = json.loads(updated["items_json"])
        return jsonify(updated)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    try:
        image_url, filename = upload_image_to_supabase(image)
    except Exception as e:
        return jsonify({"error": f"Image upload failed: {str(e)}"}), 500

    try:
        product_data = {
            "name": name,
            "description": description,
            "image_filename": image_url,
            "rbx_price": rbx_price,
            "cash_price": cash_price,
        }
        response = supabase.table("products").insert(product_data).execute()
        return jsonify(response.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/products/<int:product_id>", methods=["DELETE"])
@require_admin
def delete_product(product_id):
    try:
        response = supabase.table("products").select("*").eq("id", product_id).execute()
        if not response.data:
            return jsonify({"error": "Product not found"}), 404

        product = response.data[0]
        image_path = UPLOADS_DIR / product["image_filename"]
        if image_path.exists():
            image_path.unlink()

        supabase.table("products").delete().eq("id", product_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/debug-env")
def debug_env():
    return jsonify({
        "SUPABASE_URL": os.environ.get("SUPABASE_URL", "NOT SET"),
        "SUPABASE_KEY_prefix": os.environ.get("SUPABASE_KEY", "NOT SET")[:20],
    })


@app.route("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.errorhandler(Exception)
def handle_error(exc):
    print(exc)
    return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
