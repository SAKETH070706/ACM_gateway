import json
import re
import urllib.parse
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Request, HTTPException, status
from backend.config import async_load_config, get_async_db
from backend.routes.auth_api import require_ebm_or_admin

ebm_router = APIRouter(tags=["EBM Operations"])

def safe_object_id(id_val):
    if id_val is None:
        return None
    try:
        return ObjectId(str(id_val))
    except (InvalidId, TypeError):
        return id_val

def clean_phone_number(val):
    if val is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(val):
            return ""
    except ImportError:
        pass

    if isinstance(val, float):
        import math
        if math.isnan(val):
            return ""
        val = int(val)

    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]

    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) == 10 and digits[0] in ["6", "7", "8", "9"]:
        digits = f"91{digits}"

    return digits

def format_message(template_str, student_dict, base_url):
    link = f"{base_url.rstrip('/')}/join/{student_dict.get('token', '')}" if student_dict.get("token") else ""
    msg = template_str.replace("{name}", str(student_dict.get("name") or ""))
    msg = msg.replace("{acm_id}", str(student_dict.get("acm_id") or ""))
    msg = msg.replace("{phone}", str(student_dict.get("phone") or ""))
    msg = msg.replace("{branch}", str(student_dict.get("branch") or ""))
    msg = msg.replace("{year}", str(student_dict.get("year") or "1"))
    msg = msg.replace("{goodies}", str(student_dict.get("goodies") or "Yes"))
    msg = msg.replace("{link}", link)

    extra = student_dict.get("extra_data") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}

    for k, v in extra.items():
        placeholder = "{" + k.lower() + "}"
        msg = msg.replace(placeholder, str(v))
    return msg

@ebm_router.get("/api/ebm/dashboard")
async def api_ebm_dashboard(request: Request, username: str = None, ebm_id: str = None):
    require_ebm_or_admin(request)
    db = get_async_db()
    ebm_info = None

    if request.session.get("admin_authenticated") and (username or ebm_id):
        if ebm_id:
            oid = safe_object_id(ebm_id)
            ebm_info = await db.ebms.find_one({"$or": [{"_id": oid}, {"id": ebm_id}]})
        else:
            ebm_info = await db.ebms.find_one({
                "$or": [
                    {"username": username.lower()},
                    {"name": {"$regex": f"^{re.escape(username)}$", "$options": "i"}}
                ]
            })
    elif request.session.get("ebm_user"):
        session_id = request.session["ebm_user"]["id"]
        oid = safe_object_id(session_id)
        ebm_info = await db.ebms.find_one({"$or": [{"_id": oid}, {"id": session_id}]})

    if not ebm_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EBM profile not found")

    ebm_id_str = str(ebm_info["_id"])

    # Fetch default template
    tpl_row = await db.message_templates.find_one({"is_default": 1})
    if not tpl_row:
        tpl_row = await db.message_templates.find_one()
    tpl_content = tpl_row["content"] if tpl_row else "Hello {name}, welcome to the ACM Student Chapter!\n\nJoin here: {link}"

    cfg = await async_load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

    # Fetch students assigned to this EBM
    student_cursor = db.students.find({"assigned_ebm_id": ebm_id_str}).sort([("is_contacted", 1), ("_id", 1)])
    student_docs = await student_cursor.to_list(length=5000)

    # Pre-fetch invite tokens to know redemption status
    tokens = [s.get("token") for s in student_docs if s.get("token")]
    inv_map = {}
    if tokens:
        inv_cursor = db.invites.find({"token": {"$in": tokens}})
        async for inv in inv_cursor:
            inv_map[inv["token"]] = inv

    students = []
    contacted_count = 0
    joined_count = 0

    for s in student_docs:
        s_id = str(s["_id"])
        is_contacted = bool(s.get("is_contacted", 0))
        if is_contacted:
            contacted_count += 1

        tok = s.get("token")
        inv = inv_map.get(tok, {}) if tok else {}
        is_used = bool(inv.get("is_used", 0))
        if is_used:
            joined_count += 1

        link = f"{base_url}/join/{tok}" if tok else ""
        d = {
            "id": s_id,
            "name": s.get("name", ""),
            "phone": s.get("phone", ""),
            "acm_id": s.get("acm_id", ""),
            "branch": s.get("branch", ""),
            "year": s.get("year", "1"),
            "goodies": s.get("goodies", "Yes"),
            "extra_data": s.get("extra_data", {}),
            "token": tok or "",
            "full_invite_link": link,
            "is_contacted": 1 if is_contacted else 0,
            "contacted_at": s.get("contacted_at", ""),
            "created_at": s.get("created_at", ""),
            "is_used": 1 if is_used else 0,
            "used_at": inv.get("used_at", "")
        }

        formatted_text = format_message(tpl_content, d, base_url)
        d["formatted_message"] = formatted_text

        phone_num = clean_phone_number(d.get("phone"))
        d["phone"] = phone_num or s.get("phone", "")
        if phone_num and len(phone_num) >= 10:
            encoded_msg = urllib.parse.quote(formatted_text, safe="")
            d["whatsapp_url"] = f"https://wa.me/{phone_num}?text={encoded_msg}"
        else:
            d["whatsapp_url"] = ""

        students.append(d)

    total_students = len(students)
    progress = round((contacted_count / total_students * 100) if total_students else 0, 1)

    return {
        "ebm": {
            "id": ebm_id_str,
            "name": ebm_info.get("name", "EBM Member"),
            "username": ebm_info.get("username", ebm_info.get("name")),
            "weight": ebm_info.get("weight", 4)
        },
        "stats": {
            "total_assigned": total_students,
            "contacted": contacted_count,
            "pending": total_students - contacted_count,
            "joined_whatsapp": joined_count,
            "progress_percent": progress
        },
        "template": {
            "title": tpl_row.get("title", "Default") if tpl_row else "Default",
            "content": tpl_content
        },
        "students": students
    }

@ebm_router.post("/api/ebm/students/{student_id}/toggle-contact")
async def api_toggle_student_contact(request: Request, student_id: str):
    require_ebm_or_admin(request)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_async_db()
    oid = safe_object_id(student_id)

    student = await db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if not request.session.get("admin_authenticated"):
        ebm_user = request.session.get("ebm_user")
        if not ebm_user or str(ebm_user["id"]) != str(student.get("assigned_ebm_id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not assigned to this student"
            )

    current_status = student.get("is_contacted", 0)
    new_status = 0 if current_status else 1
    contacted_at = now_str if new_status == 1 else None

    await db.students.update_one(
        {"_id": student["_id"]},
        {"$set": {"is_contacted": new_status, "contacted_at": contacted_at}}
    )

    return {
        "success": True,
        "is_contacted": new_status,
        "contacted_at": contacted_at
    }
