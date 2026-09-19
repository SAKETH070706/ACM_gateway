import re
import secrets
from datetime import datetime
from flask import Blueprint, request, render_template, make_response
from backend.config import load_config, get_db

gateway_bp = Blueprint("gateway", __name__)

BOT_USER_AGENTS = [
    "facebookexternalhit", "whatsapp", "telegrambot", "twitterbot",
    "slackbot", "discordbot", "applebot", "googlebot", "bingbot",
    "yandex", "baiduspider", "duckduckbot", "linkedinbot", "embedly",
    "quora link preview", "showyoubot", "outbrain", "pinterest", "vkshare"
]

def is_bot_or_prefetch():
    ua = (request.headers.get("User-Agent") or "").lower()
    if any(b in ua for b in BOT_USER_AGENTS):
        return True
    purpose = (request.headers.get("X-Purpose") or request.headers.get("Purpose") or request.headers.get("Sec-Purpose") or "").lower()
    if "preview" in purpose or "prefetch" in purpose:
        return True
    return False

def extract_invite_code(url):
    match = re.search(r"chat\.whatsapp\.com/([a-zA-Z0-9_-]+)", url or "")
    return match.group(1) if match else ""

@gateway_bp.route("/join/<token>", methods=["GET", "HEAD"])
def join_group(token):
    # Gracefully handle HEAD requests with 200 and no-store headers without consuming tokens
    if request.method == "HEAD":
        resp = make_response("", 200)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # If crawler/bot generating preview or prefetch, return secure preview page without leaking WhatsApp link
    if is_bot_or_prefetch():
        resp = make_response(render_template("preview.html"))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    cfg = load_config()
    group_link = cfg.get("whatsapp_group_link", "").strip()
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    cookie_name = f"dev_token_{token}"
    client_device_id = request.cookies.get(cookie_name)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invites WHERE token = ?", (token,))
        invite = cursor.fetchone()

        if not invite:
            return render_template("invalid.html"), 404

        code = extract_invite_code(group_link)
        deep_link = f"whatsapp://chat?code={code}" if code else group_link

        if invite["is_used"]:
            # Strict Single-Device Lock:
            # ONLY the exact device/browser that has the secret device cookie AND is within 15 minutes can access!
            is_same_device = bool(client_device_id and invite["device_id"] and client_device_id == invite["device_id"])
            within_grace = False

            if is_same_device and invite["used_at"]:
                try:
                    used_dt = datetime.strptime(invite["used_at"], "%Y-%m-%d %H:%M:%S")
                    if (now - used_dt).total_seconds() < 900:  # 15 min window
                        within_grace = True
                except Exception:
                    pass

            if not within_grace:
                return render_template("expired.html", used_at=invite["used_at"]), 410

            return render_template("redirect.html", group_url=group_link, deep_link=deep_link, code=code)

        else:
            # First human visit on first device: issue unique secret device token
            new_device_id = secrets.token_hex(16)
            cursor.execute("""
                UPDATE invites 
                SET is_used = 1, used_at = ?, ip_address = ?, device_id = ? 
                WHERE token = ? AND is_used = 0
            """, (now_str, client_ip, new_device_id, token))
            conn.commit()

            if cursor.rowcount == 0:
                return render_template("expired.html", used_at=now_str), 410

            resp = make_response(render_template("redirect.html", group_url=group_link, deep_link=deep_link, code=code))
            resp.set_cookie(cookie_name, new_device_id, max_age=900, httponly=True, samesite="Lax")
            return resp
