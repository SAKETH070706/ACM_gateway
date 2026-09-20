import os
import re
import hmac
import hashlib
import json
import base64
import time
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status
from werkzeug.security import generate_password_hash, check_password_hash
from backend.config import async_load_config, get_async_db

auth_router = APIRouter(tags=["Authentication"])

AUTH_SECRET = os.environ.get("FLASK_SECRET_KEY") or "ace_acm_portal_super_auth_token_key_2026_deterministic"

def generate_auth_token(payload: dict) -> str:
    payload_copy = dict(payload)
    payload_copy["exp"] = int(time.time()) + (86400 * 30)  # 30-day token lifetime
    data_str = json.dumps(payload_copy, separators=(',', ':'), sort_keys=True)
    b64_data = base64.urlsafe_b64encode(data_str.encode('utf-8')).decode('utf-8').rstrip('=')
    sig = hmac.new(AUTH_SECRET.encode('utf-8'), b64_data.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"

def verify_auth_token(token: str) -> dict | None:
    try:
        parts = token.strip().split('.')
        if len(parts) != 2:
            return None
        b64_data, sig = parts[0], parts[1]
        expected_sig = hmac.new(AUTH_SECRET.encode('utf-8'), b64_data.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        padded = b64_data + '=' * (-len(b64_data) % 4)
        raw_json = base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8')
        payload = json.loads(raw_json)
        if payload.get("exp") and time.time() > payload["exp"]:
            return None
        return payload
    except Exception:
        return None

def get_authenticated_user(request: Request) -> dict | None:
    # 1. Session cookie check
    if request.session.get("admin_authenticated"):
        return {"role": "admin", "name": "Master Administrator"}
    if request.session.get("ebm_user"):
        return request.session.get("ebm_user")

    # 2. Authorization header / Bearer token check
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = (
            request.headers.get("x-auth-token") or
            request.headers.get("X-Auth-Token") or
            request.headers.get("x-admin-token") or
            request.headers.get("X-Admin-Token") or ""
        ).strip()

    if token:
        payload = verify_auth_token(token)
        if payload:
            if payload.get("role") == "admin":
                request.session["admin_authenticated"] = True
            elif payload.get("role") == "ebm":
                request.session["ebm_user"] = payload
            return payload

    # 3. Direct admin secret key header or query fallback
    admin_key = (
        request.headers.get("x-admin-key") or
        request.headers.get("X-Admin-Key") or
        request.query_params.get("admin_key") or
        request.query_params.get("key") or ""
    ).strip()
    if admin_key:
        expected_pw = (os.environ.get("ADMIN_PASSWORD") or "admin").strip()
        is_prod = bool(
            os.environ.get("RENDER") or
            os.environ.get("VERCEL") or
            os.environ.get("ENVIRONMENT") == "production"
        )
        valid_passwords = [expected_pw]
        if not is_prod:
            for fallback in ["admin123", "admin", "freshers2026"]:
                if fallback not in valid_passwords:
                    valid_passwords.append(fallback)
        if any(hmac.compare_digest(admin_key.encode("utf-8"), p.encode("utf-8")) for p in valid_passwords):
            request.session["admin_authenticated"] = True
            return {"role": "admin", "name": "Master Administrator"}

    return None

def require_admin(request: Request):
    user = get_authenticated_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Admin access required"
        )
    return user

def require_ebm_or_admin(request: Request):
    user = get_authenticated_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Login required"
        )
    return user

# ----------------- ADMIN LOGIN -----------------
@auth_router.post("/api/auth/admin/login")
async def api_admin_login(request: Request):
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    entered_pw = (data.get("password") or data.get("key") or "").strip()
    cfg = await async_load_config()
    expected_pw = (os.environ.get("ADMIN_PASSWORD") or cfg.get("admin_password") or "admin").strip()

    is_prod = bool(
        os.environ.get("RENDER") or
        os.environ.get("VERCEL") or
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
        user_info = {"role": "admin", "name": "Master Administrator"}
        token = generate_auth_token(user_info)
        request.session["admin_authenticated"] = True
        request.session.pop("ebm_user", None)
        return {
            "success": True,
            "token": token,
            "user": user_info
        }

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect admin password")

# ----------------- EBM REGISTRATION -----------------
@auth_router.post("/api/auth/ebm/register", status_code=status.HTTP_201_CREATED)
async def api_ebm_register(request: Request):
    data = await request.json()
    name = (data.get("name") or "").strip()
    password = (data.get("password") or "").strip()
    try:
        weight = min(20, max(1, int(data.get("weight", 4))))
    except (ValueError, TypeError):
        weight = 4

    if not name or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both Name and Password are required for EBM registration"
        )

    db = get_async_db()
    existing = await db.ebms.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An EBM with the name '{name}' is already registered. Please sign in or use a different name."
        )

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
    result = await db.ebms.insert_one(ebm_doc)

    return {
        "success": True,
        "message": f"EBM '{name}' registered successfully! You can now log in.",
        "ebm": {
            "id": str(result.inserted_id),
            "name": name,
            "weight": weight
        }
    }

# ----------------- EBM LIST NAMES (FOR DROPDOWN) -----------------
@auth_router.get("/api/ebm/list-names")
@auth_router.get("/api/auth/ebm/list-names")
async def api_ebm_list_names():
    db = get_async_db()
    cursor = db.ebms.find({}, {"_id": 1, "name": 1, "weight": 1}).sort([("weight", -1), ("name", 1)])
    ebms = []
    async for doc in cursor:
        ebms.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", "EBM Member"),
            "weight": doc.get("weight", 4)
        })
    return {"ebms": ebms}

# ----------------- EBM LOGIN -----------------
@auth_router.post("/api/auth/ebm/login")
async def api_ebm_login(request: Request):
    data = await request.json()
    name_or_user = (data.get("name") or data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not name_or_user or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select your name and enter your password"
        )

    db = get_async_db()
    member = await db.ebms.find_one({
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
            is_valid = hmac.compare_digest(stored_pw.encode("utf-8"), password.encode("utf-8"))
            if is_valid:
                new_hash = generate_password_hash(password)
                await db.ebms.update_one({"_id": member["_id"]}, {"$set": {"password": new_hash}})

        if is_valid:
            user_payload = {
                "id": str(member["_id"]),
                "name": member["name"],
                "username": member.get("username", member["name"]),
                "role": member.get("role", "ebm"),
                "weight": member.get("weight", 4)
            }
            token = generate_auth_token(user_payload)
            request.session["ebm_user"] = user_payload
            request.session.pop("admin_authenticated", None)
            return {"success": True, "token": token, "user": user_payload}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid name or password. Please verify your credentials."
    )

# ----------------- AUTH STATUS & LOGOUT -----------------
@auth_router.get("/api/auth/me")
async def api_auth_me(request: Request):
    user = get_authenticated_user(request)
    if user:
        return {
            "authenticated": True,
            "role": user.get("role", "ebm"),
            "user": user
        }
    return {"authenticated": False, "role": None, "user": None}

@auth_router.post("/api/auth/logout")
@auth_router.get("/api/auth/logout")
async def api_auth_logout(request: Request):
    request.session.clear()
    return {"success": True}
