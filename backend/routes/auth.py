import os
import hmac
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

@auth_bp.route("/api/auth/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json() or {}
    entered_pw = data.get("password", "").strip()
    cfg = load_config()
    expected_pw = (os.environ.get("ADMIN_PASSWORD") or cfg.get("admin_password") or "admin").strip()

    if entered_pw and hmac.compare_digest(entered_pw.encode("utf-8"), expected_pw.encode("utf-8")):
        session["admin_authenticated"] = True
        session.pop("ebm_user", None)
        return jsonify({
            "success": True,
            "user": {"role": "admin", "name": "Master Administrator"}
        })
    return jsonify({"error": "Incorrect admin password"}), 401

@auth_bp.route("/api/auth/ebm/login", methods=["POST"])
def api_ebm_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ebm_members WHERE LOWER(username) = ?", (username,))
        member = cursor.fetchone()

        if member:
            stored_pw = member["password"] or ""
            is_valid = False

            # Check if password is stored as a Werkzeug hash
            if stored_pw.startswith("scrypt:") or stored_pw.startswith("pbkdf2:"):
                is_valid = check_password_hash(stored_pw, password)
            else:
                # Timing-safe comparison for legacy plaintext passwords
                is_valid = hmac.compare_digest(stored_pw.encode("utf-8"), password.encode("utf-8"))
                if is_valid:
                    # Automatically upgrade to Werkzeug password hash
                    new_hash = generate_password_hash(password)
                    cursor.execute("UPDATE ebm_members SET password = ? WHERE id = ?", (new_hash, member["id"]))
                    conn.commit()

            if is_valid:
                user_payload = {
                    "id": member["id"],
                    "name": member["name"],
                    "username": member["username"],
                    "role": member["role"],
                    "weight": member["weight"]
                }
                session["ebm_user"] = user_payload
                session.pop("admin_authenticated", None)
                return jsonify({"success": True, "user": user_payload})

    return jsonify({"error": "Invalid EBM credentials"}), 401

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
