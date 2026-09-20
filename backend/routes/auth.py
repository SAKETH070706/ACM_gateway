import os
import re
import hmac
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from backend.config import load_config, get_db

auth_bp = Blueprint("auth", __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized: Admin access required"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

def ebm_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_authenticated") and not session.get("ebm_user"):
            return jsonify({"error": "Unauthorized: Login required"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ----------------- ADMIN LOGIN -----------------
@auth_bp.route("/api/auth/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json() or {}
    entered_pw = data.get("password", "").strip()
    cfg = load_config()
    expected_pw = (os.environ.get("ADMIN_PASSWORD") or cfg.get("admin_password") or "admin").strip()

    is_prod = bool(
        os.environ.get("RENDER") or
        os.environ.get("VERCEL") or
        os.environ.get("FLASK_ENV") == "production" or
        os.environ.get("ENVIRONMENT") == "production"
    )

    valid_passwords = [expected_pw]
    if not is_prod:
        for fallback in ["admin123", "admin", "freshers2026"]:
            if fallback not in valid_passwords:
                valid_passwords.append(fallback)

    is_valid = any(
        hmac.compare_digest(entered_pw.encode("utf-8"), p.encode("utf-8"))
        for p in valid_passwords
    )

    if entered_pw and is_valid:
        session["admin_authenticated"] = True
        session.pop("ebm_user", None)
        return jsonify({
            "success": True,
            "user": {"role": "admin", "name": "Master Administrator"}
        })
    return jsonify({"error": "Incorrect admin password"}), 401

# ----------------- EBM REGISTRATION -----------------
@auth_bp.route("/api/auth/ebm/register", methods=["POST"])
def api_ebm_register():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    password = data.get("password", "").strip()
    try:
        weight = min(20, max(1, int(data.get("weight", 4))))
    except (ValueError, TypeError):
        weight = 4

    if not name or not password:
        return jsonify({"error": "Both Name and Password are required for EBM registration"}), 400

    db = get_db()
    # Check if EBM name already registered (case-insensitive)
    existing = db.ebms.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if existing:
        return jsonify({"error": f"An EBM with the name '{name}' is already registered. Please sign in or use a different name."}), 400

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed_password = generate_password_hash(password)
    ebm_doc = {
        "name": name,
        "username": re.sub(r"[^a-zA-Z0-9_]", "", name.lower().replace(" ", "_")),
        "password": hashed_password,
        "role": "ebm",
        "weight": weight,
        "created_at": now_str
    }
    result = db.ebms.insert_one(ebm_doc)

    return jsonify({
        "success": True,
        "message": f"EBM '{name}' registered successfully! You can now log in.",
        "ebm": {
            "id": str(result.inserted_id),
            "name": name,
            "weight": weight
        }
    }), 201

# ----------------- EBM LIST NAMES (FOR DROPDOWN) -----------------
@auth_bp.route("/api/ebm/list-names", methods=["GET"])
@auth_bp.route("/api/auth/ebm/list-names", methods=["GET"])
def api_ebm_list_names():
    db = get_db()
    cursor = db.ebms.find({}, {"_id": 1, "name": 1, "weight": 1}).sort("name", 1)
    ebms = []
    for doc in cursor:
        ebms.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", "EBM Member"),
            "weight": doc.get("weight", 4)
        })
    return jsonify({"ebms": ebms})

# ----------------- EBM LOGIN -----------------
@auth_bp.route("/api/auth/ebm/login", methods=["POST"])
def api_ebm_login():
    data = request.get_json() or {}
    name_or_user = (data.get("name") or data.get("username") or "").strip()
    password = data.get("password", "").strip()

    if not name_or_user or not password:
        return jsonify({"error": "Please select your name and enter your password"}), 400

    db = get_db()
    # Match by exact name, case-insensitive name, or username
    member = db.ebms.find_one({
        "$or": [
            {"name": {"$regex": f"^{re.escape(name_or_user)}$", "$options": "i"}},
            {"username": name_or_user.lower()}
        ]
    })

    if member:
        stored_pw = member.get("password", "")
        is_valid = False

        if stored_pw.startswith("scrypt:") or stored_pw.startswith("pbkdf2:"):
            is_valid = check_password_hash(stored_pw, password)
        else:
            # Timing-safe comparison for legacy plaintext passwords
            is_valid = hmac.compare_digest(stored_pw.encode("utf-8"), password.encode("utf-8"))
            if is_valid:
                # Automatically upgrade to Werkzeug password hash
                new_hash = generate_password_hash(password)
                db.ebms.update_one({"_id": member["_id"]}, {"$set": {"password": new_hash}})

        if is_valid:
            user_payload = {
                "id": str(member["_id"]),
                "name": member["name"],
                "username": member.get("username", member["name"]),
                "role": member.get("role", "ebm"),
                "weight": member.get("weight", 4)
            }
            session["ebm_user"] = user_payload
            session.pop("admin_authenticated", None)
            return jsonify({"success": True, "user": user_payload})

    return jsonify({"error": "Invalid name or password. Please verify your credentials."}), 401

# ----------------- AUTH STATUS & LOGOUT -----------------
@auth_bp.route("/api/auth/me", methods=["GET"])
def api_auth_me():
    if session.get("admin_authenticated"):
        return jsonify({
            "authenticated": True,
            "role": "admin",
            "user": {"name": "Master Administrator", "role": "admin"}
        })
    elif session.get("ebm_user"):
        return jsonify({
            "authenticated": True,
            "role": "ebm",
            "user": session["ebm_user"]
        })
    return jsonify({"authenticated": False, "role": None, "user": None})

@auth_bp.route("/api/auth/logout", methods=["POST", "GET"])
def api_auth_logout():
    session.pop("admin_authenticated", None)
    session.pop("ebm_user", None)
    return jsonify({"success": True})
