import os
from pymongo import MongoClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

try:
    from dotenv import load_dotenv
    # Load backend/.env first, then root .env if present
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

_mongo_client = None

def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        uri = os.environ.get("MONGO_URI") or "mongodb://localhost:27017/acm_gateway"
        _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _mongo_client

class MongoDatabaseWrapper:
    """Wrapper that supports both direct collection access (db.students) and context manager (with get_db() as db)"""
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def __getitem__(self, name):
        return self._db[name]

    def __enter__(self):
        return self._db

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def get_db():
    client = get_mongo_client()
    try:
        db = client.get_default_database()
        if db is None or db.name == "admin":
            db = client["ACE_REG"]
    except Exception:
        db = client["ACE_REG"]
    return MongoDatabaseWrapper(db)

def load_config():
    cfg = {
        "whatsapp_group_link": os.environ.get("WHATSAPP_GROUP_LINK") or "https://chat.whatsapp.com/JvimDEP8FrQHOlicdDCEXX",
        "base_url": os.environ.get("BASE_URL") or "https://wp-add-auto.onrender.com",
        "admin_password": os.environ.get("ADMIN_PASSWORD") or "admin"
    }
    try:
        db = get_db()
        for doc in db.settings.find():
            if "key" in doc and "value" in doc:
                cfg[doc["key"]] = doc["value"]
    except Exception as e:
        print("Note on loading config from MongoDB:", e)

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
        db = get_db()
        for k, v in cfg.items():
            db.settings.update_one({"key": k}, {"$set": {"key": k, "value": str(v)}}, upsert=True)
    except Exception as e:
        print("Note on saving config to MongoDB:", e)