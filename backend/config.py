import os
import json
import sqlite3
import contextlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

IS_VERCEL = bool(os.environ.get("VERCEL"))
IS_RENDER = bool(os.environ.get("RENDER"))

if IS_VERCEL:
    CONFIG_FILE = "/tmp/config.json"
    DB_FILE = "/tmp/invites.db"
elif IS_RENDER:
    # Render persistent disk mount directory path
    RENDER_DATA_DIR = "/var/data"
    os.makedirs(RENDER_DATA_DIR, exist_ok=True)
    CONFIG_FILE = os.path.join(RENDER_DATA_DIR, "config.json")
    DB_FILE = os.path.join(RENDER_DATA_DIR, "invites.db")
else:
    CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
    DB_FILE = os.path.join(BASE_DIR, "invites.db")

FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()

def load_config():
    cfg = {
        "whatsapp_group_link": os.environ.get("WHATSAPP_GROUP_LINK") or "https://chat.whatsapp.com/JvimDEP8FrQHOlicdDCEXX",
        "base_url": os.environ.get("BASE_URL") or "https://wp-add-auto.onrender.com",
        "admin_password": os.environ.get("ADMIN_PASSWORD") or "admin"
    }
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            for row in rows:
                cfg[row["key"]] = row["value"]
    except Exception as e:
        print("Error loading config from SQLite:", e)

    # Environment variable overrides (highest priority)
    if os.environ.get("WHATSAPP_GROUP_LINK"):
        cfg["whatsapp_group_link"] = os.environ.get("WHATSAPP_GROUP_LINK").strip()
    if os.environ.get("BASE_URL"):
        cfg["base_url"] = os.environ.get("BASE_URL").strip().rstrip("/")
    if os.environ.get("ADMIN_PASSWORD"):
        cfg["admin_password"] = os.environ.get("ADMIN_PASSWORD").strip()
    return cfg

def save_config(cfg):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            for k, v in cfg.items():
                cursor.execute("""
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """, (k, str(v)))
            conn.commit()
    except Exception as e:
        print("Error saving config to SQLite:", e)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass