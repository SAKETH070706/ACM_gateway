import re
import secrets
from datetime import datetime
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from backend.config import TEMPLATES_DIR, async_load_config, get_async_db

gateway_router = APIRouter(tags=["Gateway"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

BOT_USER_AGENTS = [
    "facebookexternalhit", "whatsapp", "telegrambot", "twitterbot",
    "slackbot", "discordbot", "applebot", "googlebot", "bingbot",
    "yandex", "baiduspider", "duckduckbot", "linkedinbot", "embedly",
    "quora link preview", "showyoubot", "outbrain", "pinterest", "vkshare"
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
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

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
        # Strict Single-Device Lock:
        is_same_device = bool(client_device_id and invite.get("device_id") and client_device_id == invite.get("device_id"))
        within_grace = False

        if is_same_device and invite.get("used_at"):
            try:
                used_dt = datetime.strptime(invite["used_at"], "%Y-%m-%d %H:%M:%S")
                if (now - used_dt).total_seconds() < 900:  # 15 min window
                    within_grace = True
            except Exception:
                pass

        if not within_grace:
            return templates.TemplateResponse(
                request=request,
                name="expired.html",
                context={"used_at": invite.get("used_at")},
                status_code=status.HTTP_410_GONE
            )

        return templates.TemplateResponse(
            request=request,
            name="redirect.html",
            context={"group_url": group_link, "deep_link": deep_link, "code": code}
        )

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
                context={"used_at": now_str},
                status_code=status.HTTP_410_GONE
            )

        resp = templates.TemplateResponse(
            request=request,
            name="redirect.html",
            context={"group_url": group_link, "deep_link": deep_link, "code": code}
        )
        resp.set_cookie(cookie_name, new_device_id, max_age=900, httponly=True, samesite="lax")
        return resp
