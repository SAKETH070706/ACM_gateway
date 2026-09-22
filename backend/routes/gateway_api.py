import re
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from backend.config import TEMPLATES_DIR, async_load_config, get_async_db

gateway_router = APIRouter(tags=["Gateway"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# India Standard Time (IST) is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

def get_ist_str(dt: datetime = None) -> str:
    if dt is None:
        dt = get_ist_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_ist_display(val) -> str:
    if not val:
        return ""
    if isinstance(val, str):
        if "IST" in val:
            return val
        try:
            dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%d %b %Y, %I:%M %p IST")
        except Exception:
            return val
    elif isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=IST)
        else:
            val = val.astimezone(IST)
        return val.strftime("%d %b %Y, %I:%M %p IST")
    return str(val)

BOT_USER_AGENTS = [
    "facebookexternalhit", "whatsapp", "telegrambot", "twitterbot",
    "slackbot", "discordbot", "applebot", "googlebot", "bingbot",
    "yandex", "baiduspider", "duckduckbot", "linkedinbot", "embedly",
    "quora link preview", "showyoubot", "outbrain", "pinterest", "vkshare",
    "bot", "crawler", "spider", "preview", "headless", "scanner",
    "transcoder", "android-async-http", "okhttp", "python-requests", "curl", "wget",
    "safebrowsing", "virustotal", "trendmicro", "bitdefender", "avast", "kaspersky",
    "truecaller"
]

def is_bot_or_prefetch(request: Request) -> bool:
    ua = (request.headers.get("user-agent") or "").lower()
    if any(b in ua for b in BOT_USER_AGENTS):
        return True
    purpose = (
        request.headers.get("x-purpose") or
        request.headers.get("purpose") or
        request.headers.get("sec-purpose") or ""
    ).lower()
    if "preview" in purpose or "prefetch" in purpose:
        return True
    sec_fetch_dest = (request.headers.get("sec-fetch-dest") or "").lower()
    if sec_fetch_dest in ["prefetch", "track"]:
        return True
    return False

def extract_invite_code(url: str) -> str:
    match = re.search(r"chat\.whatsapp\.com/([a-zA-Z0-9_-]+)", url or "")
    return match.group(1) if match else ""

@gateway_router.api_route("/join/{token}", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def join_group(request: Request, token: str):
    # Gracefully handle HEAD requests with 200 and no-store headers without consuming tokens
    if request.method == "HEAD":
        resp = Response("", status_code=200)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # If crawler/bot generating preview or prefetch, return secure preview page without leaking WhatsApp link
    if is_bot_or_prefetch(request):
        resp = templates.TemplateResponse(
            request=request,
            name="preview.html"
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    cfg = await async_load_config()
    group_link = cfg.get("whatsapp_group_link", "").strip()

    client_ip = (
        request.headers.get("cf-connecting-ip") or
        request.headers.get("x-forwarded-for") or
        (request.client.host if request.client else "")
    )
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    cookie_name = f"dev_token_{token}"
    client_device_id = request.cookies.get(cookie_name)
    now = get_ist_now()
    now_str = get_ist_str(now)

    db = get_async_db()
    invite = await db.invites.find_one({"token": token})

    if not invite:
        return templates.TemplateResponse(
            request=request,
            name="invalid.html",
            status_code=status.HTTP_404_NOT_FOUND
        )

    code = extract_invite_code(group_link)
    deep_link = f"whatsapp://chat?code={code}" if code else group_link

    if invite.get("is_used"):
        within_grace = False
        raw_used_at = invite.get("used_at") or ""
        formatted_used = format_ist_display(raw_used_at)

        if raw_used_at:
            try:
                used_dt = datetime.strptime(raw_used_at, "%Y-%m-%d %H:%M:%S")
                if used_dt.tzinfo is None:
                    used_dt = used_dt.replace(tzinfo=IST)
                diff_sec = abs((now - used_dt).total_seconds())

                is_same_device = bool(client_device_id and invite.get("device_id") and client_device_id == invite.get("device_id"))
                is_same_ip = bool(client_ip and invite.get("ip_address") and client_ip == invite.get("ip_address"))

                # Grace Policy:
                # 1. Within 10 minutes (600s) of first access: Always allow re-access
                #    (handles WhatsApp in-app browser to external Chrome handoff, duplicate taps, page reloads)
                # 2. Within 30 minutes (1800s): Allow if same device cookie or same IP address
                if diff_sec < 600 or ((is_same_device or is_same_ip) and diff_sec < 1800):
                    within_grace = True
            except Exception:
                pass

        if not within_grace:
            return templates.TemplateResponse(
                request=request,
                name="expired.html",
                context={
                    "used_at": raw_used_at,
                    "formatted_used_at": formatted_used
                },
                status_code=status.HTTP_410_GONE
            )

        resp = templates.TemplateResponse(
            request=request,
            name="redirect.html",
            context={"group_url": group_link, "deep_link": deep_link, "code": code}
        )
        if invite.get("device_id"):
            resp.set_cookie(cookie_name, invite["device_id"], max_age=1800, httponly=True, samesite="lax")
        return resp

    else:
        # First human visit: issue unique secret device token
        new_device_id = secrets.token_hex(16)
        result = await db.invites.update_one(
            {"token": token, "is_used": 0},
            {"$set": {
                "is_used": 1,
                "used_at": now_str,
                "ip_address": client_ip,
                "device_id": new_device_id
            }}
        )

        if result.modified_count == 0:
            return templates.TemplateResponse(
                request=request,
                name="expired.html",
                context={
                    "used_at": now_str,
                    "formatted_used_at": format_ist_display(now_str)
                },
                status_code=status.HTTP_410_GONE
            )

        # Synchronize db.students with redemption status
        await db.students.update_one(
            {"token": token},
            {"$set": {
                "is_used": 1,
                "used_at": now_str,
                "ip_address": client_ip
            }}
        )

        resp = templates.TemplateResponse(
            request=request,
            name="redirect.html",
            context={"group_url": group_link, "deep_link": deep_link, "code": code}
        )
        resp.set_cookie(cookie_name, new_device_id, max_age=1800, httponly=True, samesite="lax")
        return resp
