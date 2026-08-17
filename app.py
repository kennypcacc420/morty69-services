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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oioartwguzoxvdrlqeu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9pb2FycnR3Z3V6b3h2ZHJscWV1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY5OTY4NzAsImV4cCI6MjEwMjU3Mjg3MH0.l7KnSbzKKd-EB9bHUZQQVRUuZowMZhHaM9zUzDWqa5s")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg"}
PAYMENT_METHODS = {"cashapp", "paypal", "chime", "robux", "trade"}

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def generate_order_code():
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "M69-" + "".join(random.choice(chars) for _ in range(8))


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


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
        products_response =
