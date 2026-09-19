import json
import re
import urllib.parse
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from backend.config import load_config, get_db
from backend.routes.auth import ebm_or_admin_required

ebm_bp = Blueprint("ebm", __name__)

def clean_phone_number(val):
    if val is None:
        return ""
    digits = re.sub(r"\D", "", str(val))
    return digits

def format_message(template_str, student_dict, base_url):
    link = f"{base_url.rstrip('/')}/join/{student_dict.get('token', '')}"
    msg = template_str.replace("{name}", str(student_dict.get("name") or ""))
    msg = msg.replace("{acm_id}", str(student_dict.get("acm_id") or ""))
    msg = msg.replace("{phone}", str(student_dict.get("phone") or ""))
    msg = msg.replace("{branch}", str(student_dict.get("branch") or ""))
    msg = msg.replace("{link}", link)

    extra = {}
    if student_dict.get("extra_data"):
        try:
            extra = json.loads(student_dict["extra_data"])
        except Exception:
            pass
    for k, v in extra.items():
        placeholder = "{" + k.lower() + "}"
        msg = msg.replace(placeholder, str(v))
    return msg

@ebm_bp.route("/api/ebm/dashboard", methods=["GET"])
@ebm_or_admin_required
def api_ebm_dashboard():
    requested_username = request.args.get("username")
    requested_id = request.args.get("ebm_id")

    ebm_info = None
    with get_db() as conn:
        cursor = conn.cursor()
        if session.get("admin_authenticated") and (requested_username or requested_id):
            if requested_id:
                cursor.execute("SELECT * FROM ebm_members WHERE id = ?", (requested_id,))
            else:
                cursor.execute("SELECT * FROM ebm_members WHERE LOWER(username) = ?", (requested_username.lower(),))
            ebm_info = cursor.fetchone()
        elif session.get("ebm_user"):
            cursor.execute("SELECT * FROM ebm_members WHERE id = ?", (session["ebm_user"]["id"],))
            ebm_info = cursor.fetchone()

        if not ebm_info:
            return jsonify({"error": "EBM profile not found"}), 404

        ebm_id = ebm_info["id"]

        cursor.execute("SELECT * FROM message_templates WHERE is_default = 1 LIMIT 1")
        tpl_row = cursor.fetchone()
        if not tpl_row:
            cursor.execute("SELECT * FROM message_templates ORDER BY id ASC LIMIT 1")
            tpl_row = cursor.fetchone()
        tpl_content = tpl_row["content"] if tpl_row else "Hello {name}, join here: {link}"

        cfg = load_config()
        base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

        cursor.execute("""
            SELECT s.id, s.name, s.phone, s.acm_id, s.branch, s.extra_data, s.token,
                   s.is_contacted, s.contacted_at, s.created_at,
                   i.is_used, i.used_at
            FROM students s
            LEFT JOIN invites i ON s.token = i.token
            WHERE s.assigned_ebm_id = ?
            ORDER BY s.is_contacted ASC, s.id ASC
        """, (ebm_id,))
        student_rows = cursor.fetchall()

        students = []
        contacted_count = 0
        joined_count = 0

        for r in student_rows:
            d = dict(r)
            if d["is_contacted"]:
                contacted_count += 1
            if d["is_used"]:
                joined_count += 1

            link = f"{base_url}/join/{d['token']}" if d.get("token") else ""
            d["full_invite_link"] = link
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
            "id": ebm_info["id"],
            "name": ebm_info["name"],
            "username": ebm_info["username"],
            "weight": ebm_info["weight"]
        },
        "stats": {
            "total_assigned": total_students,
            "contacted": contacted_count,
            "pending": total_students - contacted_count,
            "joined_whatsapp": joined_count,
            "progress_percent": progress
        },
        "template": {
            "title": tpl_row["title"] if tpl_row else "Default",
            "content": tpl_content
        },
        "students": students
    })

@ebm_bp.route("/api/ebm/students/<int:student_id>/toggle-contact", methods=["POST"])
@ebm_or_admin_required
def api_toggle_student_contact(student_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_contacted, assigned_ebm_id FROM students WHERE id = ?", (student_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Student not found"}), 404

        if not session.get("admin_authenticated"):
            ebm_user = session.get("ebm_user")
            if not ebm_user or ebm_user["id"] != row["assigned_ebm_id"]:
                return jsonify({"error": "Forbidden: You are not assigned to this student"}), 403

        new_status = 0 if row["is_contacted"] else 1
        contacted_at = now_str if new_status == 1 else None

        cursor.execute("""
            UPDATE students SET is_contacted = ?, contacted_at = ? WHERE id = ?
        """, (new_status, contacted_at, student_id))
        conn.commit()

    return jsonify({
        "success": True,
        "is_contacted": new_status,
        "contacted_at": contacted_at
    })
