import json
import re
import urllib.parse
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request, jsonify, session
from backend.config import load_config, get_db
from backend.routes.auth import ebm_or_admin_required

ebm_bp = Blueprint("ebm", __name__)

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
    digits = re.sub(r"\D", "", str(val))
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

@ebm_bp.route("/api/ebm/dashboard", methods=["GET"])
@ebm_or_admin_required
def api_ebm_dashboard():
    requested_username = request.args.get("username")
    requested_id = request.args.get("ebm_id")

    db = get_db()
    ebm_info = None

    if session.get("admin_authenticated") and (requested_username or requested_id):
        if requested_id:
            oid = safe_object_id(requested_id)
            ebm_info = db.ebms.find_one({"$or": [{"_id": oid}, {"id": requested_id}]})
        else:
            ebm_info = db.ebms.find_one({
                "$or": [
                    {"username": requested_username.lower()},
                    {"name": {"$regex": f"^{re.escape(requested_username)}$", "$options": "i"}}
                ]
            })
    elif session.get("ebm_user"):
        session_id = session["ebm_user"]["id"]
        oid = safe_object_id(session_id)
        ebm_info = db.ebms.find_one({"$or": [{"_id": oid}, {"id": session_id}]})

    if not ebm_info:
        return jsonify({"error": "EBM profile not found"}), 404

    ebm_id_str = str(ebm_info["_id"])

    # Fetch default template
    tpl_row = db.message_templates.find_one({"is_default": 1})
    if not tpl_row:
        tpl_row = db.message_templates.find_one()
    tpl_content = tpl_row["content"] if tpl_row else "Hello {name}, welcome to the ACM Student Chapter!\n\nJoin here: {link}"

    cfg = load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

    # Fetch students assigned to this EBM
    student_docs = list(db.students.find({"assigned_ebm_id": ebm_id_str}).sort([("is_contacted", 1), ("_id", 1)]))

    # Pre-fetch invite tokens to know redemption status
    tokens = [s.get("token") for s in student_docs if s.get("token")]
    inv_map = {inv["token"]: inv for inv in db.invites.find({"token": {"$in": tokens}})} if tokens else {}

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
        if phone_num:
            encoded_msg = urllib.parse.quote(formatted_text, safe="")
            d["whatsapp_url"] = f"https://wa.me/{phone_num}?text={encoded_msg}"
        else:
            d["whatsapp_url"] = ""

        students.append(d)

    total_students = len(students)
    progress = round((contacted_count / total_students * 100) if total_students else 0, 1)

    return jsonify({
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
    })

@ebm_bp.route("/api/ebm/students/<student_id>/toggle-contact", methods=["POST"])
@ebm_or_admin_required
def api_toggle_student_contact(student_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    oid = safe_object_id(student_id)

    student = db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        return jsonify({"error": "Student not found"}), 404

    if not session.get("admin_authenticated"):
        ebm_user = session.get("ebm_user")
        if not ebm_user or str(ebm_user["id"]) != str(student.get("assigned_ebm_id")):
            return jsonify({"error": "Forbidden: You are not assigned to this student"}), 403

    current_status = student.get("is_contacted", 0)
    new_status = 0 if current_status else 1
    contacted_at = now_str if new_status == 1 else None

    db.students.update_one(
        {"_id": student["_id"]},
        {"$set": {"is_contacted": new_status, "contacted_at": contacted_at}}
    )

    return jsonify({
        "success": True,
        "is_contacted": new_status,
        "contacted_at": contacted_at
    })
