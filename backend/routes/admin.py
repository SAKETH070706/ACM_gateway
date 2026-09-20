import json
import secrets
from datetime import datetime
import io
import csv
import re
import pandas as pd
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request, jsonify, Response
from pymongo import UpdateOne
from werkzeug.security import generate_password_hash
from backend.config import load_config, save_config, get_db
from backend.routes.auth import admin_required

admin_bp = Blueprint("admin", __name__)

def safe_object_id(id_val):
    """Safely converts string or int to ObjectId or returns original if invalid"""
    if id_val is None:
        return None
    try:
        return ObjectId(str(id_val))
    except (InvalidId, TypeError):
        return id_val

def clean_phone_number(val):
    if val is None or pd.isna(val):
        return ""

    if isinstance(val, float):
        import math
        if math.isnan(val):
            return ""
        val = int(val)

    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""

    # Remove international dialing prefix 00
    if digits.startswith("00"):
        digits = digits[2:]

    # If 11 digits starting with 0, remove trunk prefix 0
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    # If it's a 10-digit Indian mobile number (starts with 6, 7, 8, 9), prepend '91'
    if len(digits) == 10 and digits[0] in ["6", "7", "8", "9"]:
        digits = f"91{digits}"

    return digits

# ----------------- ADMIN OVERVIEW STATS -----------------
@admin_bp.route("/api/admin/overview", methods=["GET"])
@admin_required
def api_admin_overview():
    cfg = load_config()
    db = get_db()

    total_students = db.students.count_documents({})
    contacted_students = db.students.count_documents({"is_contacted": 1})
    total_invites = db.invites.count_documents({})
    used_invites = db.invites.count_documents({"is_used": 1})
    unassigned_students = db.students.count_documents({
        "$or": [{"assigned_ebm_id": None}, {"assigned_ebm_id": ""}]
    })

    # Aggregate EBM team members
    ebm_docs = list(db.ebms.find().sort([("weight", -1), ("name", 1)]))
    ebm_summary = []

    for e in ebm_docs:
        e_id_str = str(e["_id"])
        assigned_count = db.students.count_documents({"assigned_ebm_id": e_id_str})
        contacted_count = db.students.count_documents({"assigned_ebm_id": e_id_str, "is_contacted": 1})

        # Count joined
        student_tokens = [
            s["token"] for s in db.students.find(
                {"assigned_ebm_id": e_id_str, "token": {"$ne": None}},
                {"token": 1}
            ) if s.get("token")
        ]
        joined_count = db.invites.count_documents({"token": {"$in": student_tokens}, "is_used": 1}) if student_tokens else 0

        ebm_summary.append({
            "id": e_id_str,
            "name": e.get("name", "EBM Member"),
            "username": e.get("username", e.get("name")),
            "weight": e.get("weight", 4),
            "assigned_count": assigned_count,
            "contacted_count": contacted_count,
            "joined_count": joined_count
        })

    return jsonify({
        "stats": {
            "total_students": total_students,
            "contacted_students": contacted_students,
            "contact_rate": round((contacted_students / total_students * 100) if total_students else 0, 1),
            "total_invites": total_invites,
            "joined_whatsapp": used_invites,
            "join_rate": round((used_invites / total_invites * 100) if total_invites else 0, 1),
            "unassigned_students": unassigned_students,
            "total_ebms": len(ebm_summary)
        },
        "ebm_summary": ebm_summary,
        "config": {
            "whatsapp_group_link": cfg.get("whatsapp_group_link", ""),
            "base_url": cfg.get("base_url", "")
        }
    })

# ----------------- CSV INGESTION & DATA INTAKE -----------------
def read_csv_dataframe(file):
    """
    Safely parse CSV bytes prioritizing utf-8-sig, cp1252, latin-1, utf-8,
    preserving literal 'NA' strings with keep_default_na=False,
    and automatically sniffing delimiters (comma, semicolon, tab, pipe).
    """
    content = file.read()
    file.seek(0)

    text = None
    for enc in ["utf-8-sig", "cp1252", "latin-1", "utf-8"]:
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = content.decode("utf-8", errors="replace")

    delimiter = ","
    try:
        sample = "\n".join([line for line in text.splitlines()[:15] if line.strip()])
        if sample:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t,")
            delimiter = dialect.delimiter
    except Exception:
        first_line = next((l for l in text.splitlines() if l.strip()), "")
        if first_line.count(";") > first_line.count(","):
            delimiter = ";"
        elif "\t" in first_line:
            delimiter = "\t"
        elif "|" in first_line:
            delimiter = "|"

    df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df

@admin_bp.route("/api/admin/upload/students", methods=["POST"])
@admin_required
def api_upload_students():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file or not file.filename.endswith(".csv"):
        return jsonify({"error": "Please upload a valid .csv file"}), 400

    try:
        df = read_csv_dataframe(file)
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {str(e)}"}), 400

    if df.empty:
        return jsonify({"error": "Uploaded CSV file is empty"}), 400

    # Flexible column matching
    col_map = {}
    for col in df.columns:
        norm = col.strip().lower().replace("_", " ").replace("-", " ")
        if norm in ["name", "student name", "fullname", "full name", "candidate name"] and "name" not in col_map:
            col_map["name"] = col
        elif norm in ["phone", "mobile", "contact", "phone number", "mobile number", "whatsapp", "contact no", "phone no"] and "phone" not in col_map:
            col_map["phone"] = col
        elif norm in ["acm id", "acmid", "id", "roll", "roll no", "roll number", "reg no", "registration no", "membership id"] and "acm_id" not in col_map:
            col_map["acm_id"] = col
        elif norm in ["branch", "department", "dept", "stream", "course"] and "branch" not in col_map:
            col_map["branch"] = col
        elif norm in ["year", "academic year", "class", "batch year"] and "year" not in col_map:
            col_map["year"] = col
        elif norm in ["goodies", "goody", "swag", "kit", "goodies eligible", "goodie eligible"] and "goodies" not in col_map:
            col_map["goodies"] = col

    if "name" not in col_map:
        col_map["name"] = df.columns[0]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upload_mode = request.form.get("mode", "overwrite").strip().lower()

    # Conditional Token Generation Toggle (true by default)
    raw_gen = request.form.get("generate_tokens")
    generate_tokens = True if raw_gen is None or str(raw_gen).lower() in ["true", "1", "yes"] else False

    db = get_db()

    if upload_mode == "overwrite":
        students_to_insert = []
        invites_to_insert = []

        for _, row in df.iterrows():
            name_val = str(row[col_map["name"]]).strip() if pd.notna(row[col_map["name"]]) else "Student"
            phone_raw = row[col_map["phone"]] if "phone" in col_map and pd.notna(row[col_map["phone"]]) else ""
            phone_val = clean_phone_number(phone_raw)
            acm_id_val = str(row[col_map["acm_id"]]).strip() if "acm_id" in col_map and pd.notna(row[col_map["acm_id"]]) else ""
            branch_val = str(row[col_map["branch"]]).strip() if "branch" in col_map and pd.notna(row[col_map["branch"]]) else ""
            year_val = str(row[col_map["year"]]).strip() if "year" in col_map and pd.notna(row[col_map["year"]]) else "1"
            goodies_val = str(row[col_map["goodies"]]).strip() if "goodies" in col_map and pd.notna(row[col_map["goodies"]]) else "Yes"

            extra_dict = {}
            for c in df.columns:
                if c not in col_map.values() and pd.notna(row[c]):
                    extra_dict[c] = str(row[c]).strip()

            token = secrets.token_urlsafe(12) if generate_tokens else None

            s_doc = {
                "name": name_val,
                "phone": phone_val,
                "acm_id": acm_id_val,
                "branch": branch_val,
                "year": year_val,
                "goodies": goodies_val,
                "extra_data": extra_dict,
                "assigned_ebm_id": None,
                "token": token,
                "is_contacted": 0,
                "contacted_at": None,
                "created_at": now_str
            }
            students_to_insert.append(s_doc)

            if token:
                invites_to_insert.append({
                    "token": token,
                    "assigned_to": name_val,
                    "student_id": None,
                    "is_used": 0,
                    "used_at": None,
                    "ip_address": None,
                    "device_id": None,
                    "created_at": now_str
                })

        try:
            db.students.delete_many({})
            db.invites.delete_many({})

            if students_to_insert:
                res = db.students.insert_many(students_to_insert)
                if generate_tokens and invites_to_insert:
                    for inv, s_id in zip(invites_to_insert, res.inserted_ids):
                        inv["student_id"] = str(s_id)
                    db.invites.insert_many(invites_to_insert)

        except Exception as e:
            return jsonify({"error": f"MongoDB operation failed during overwrite: {str(e)}"}), 500

        return jsonify({
            "success": True,
            "message": f"Successfully ingested {len(students_to_insert)} students into MongoDB (Tokens Generated: {'Yes' if generate_tokens else 'No'}).",
            "count": len(students_to_insert),
            "mode": "overwrite",
            "tokens_generated": generate_tokens,
            "detected_columns": list(col_map.keys())
        })

    else:
        # Sync mode
        updated_count = 0
        inserted_count = 0

        for _, row in df.iterrows():
            name_val = str(row[col_map["name"]]).strip() if pd.notna(row[col_map["name"]]) else "Student"
            phone_raw = row[col_map["phone"]] if "phone" in col_map and pd.notna(row[col_map["phone"]]) else ""
            phone_val = clean_phone_number(phone_raw)
            acm_id_val = str(row[col_map["acm_id"]]).strip() if "acm_id" in col_map and pd.notna(row[col_map["acm_id"]]) else ""
            branch_val = str(row[col_map["branch"]]).strip() if "branch" in col_map and pd.notna(row[col_map["branch"]]) else ""
            year_val = str(row[col_map["year"]]).strip() if "year" in col_map and pd.notna(row[col_map["year"]]) else "1"
            goodies_val = str(row[col_map["goodies"]]).strip() if "goodies" in col_map and pd.notna(row[col_map["goodies"]]) else "Yes"

            extra_dict = {}
            for c in df.columns:
                if c not in col_map.values() and pd.notna(row[c]):
                    extra_dict[c] = str(row[c]).strip()

            query = {}
            if acm_id_val:
                query = {"acm_id": {"$regex": f"^{re.escape(acm_id_val)}$", "$options": "i"}}
            elif phone_val:
                query = {"phone": phone_val}
            elif name_val:
                query = {"name": {"$regex": f"^{re.escape(name_val)}$", "$options": "i"}}

            existing = db.students.find_one(query) if query else None

            if existing:
                update_fields = {
                    "name": name_val,
                    "phone": phone_val,
                    "acm_id": acm_id_val,
                    "branch": branch_val,
                    "year": year_val,
                    "goodies": goodies_val,
                    "extra_data": extra_dict
                }
                # If generate_tokens is requested and student lacks a token, issue one
                if generate_tokens and not existing.get("token"):
                    new_token = secrets.token_urlsafe(12)
                    update_fields["token"] = new_token
                    db.invites.insert_one({
                        "token": new_token,
                        "assigned_to": name_val,
                        "student_id": str(existing["_id"]),
                        "is_used": 0,
                        "used_at": None,
                        "ip_address": None,
                        "device_id": None,
                        "created_at": now_str
                    })
                db.students.update_one({"_id": existing["_id"]}, {"$set": update_fields})
                updated_count += 1
            else:
                new_token = secrets.token_urlsafe(12) if generate_tokens else None
                s_doc = {
                    "name": name_val,
                    "phone": phone_val,
                    "acm_id": acm_id_val,
                    "branch": branch_val,
                    "year": year_val,
                    "goodies": goodies_val,
                    "extra_data": extra_dict,
                    "assigned_ebm_id": None,
                    "token": new_token,
                    "is_contacted": 0,
                    "contacted_at": None,
                    "created_at": now_str
                }
                s_res = db.students.insert_one(s_doc)
                if new_token:
                    db.invites.insert_one({
                        "token": new_token,
                        "assigned_to": name_val,
                        "student_id": str(s_res.inserted_id),
                        "is_used": 0,
                        "used_at": None,
                        "ip_address": None,
                        "device_id": None,
                        "created_at": now_str
                    })
                inserted_count += 1

        return jsonify({
            "success": True,
            "message": f"Sync complete: {updated_count} students updated, {inserted_count} new students added to MongoDB.",
            "count": updated_count + inserted_count,
            "mode": "sync",
            "tokens_generated": generate_tokens,
            "detected_columns": list(col_map.keys())
        })

# ----------------- LIVE ACM MONGODB SYNC (registrations collection) -----------------
@admin_bp.route("/api/admin/sync/registrations", methods=["POST"])
@admin_required
def api_sync_from_registrations():
    data = request.get_json(silent=True) or {}
    year_filter = str(data.get("year", "all")).strip()
    goodies_filter = str(data.get("goodies", "all")).strip()
    raw_gen = data.get("generate_tokens")
    generate_tokens = True if raw_gen is None or str(raw_gen).lower() in ["true", "1", "yes"] else False
    mode = str(data.get("mode", "sync")).strip().lower()  # "sync" or "overwrite"

    db = get_db()

    query = {}
    if year_filter and year_filter.lower() not in ["all", "any"]:
        query["year"] = {"$regex": f"^{re.escape(year_filter)}", "$options": "i"}
    if goodies_filter and goodies_filter.lower() not in ["all", "any"]:
        if goodies_filter.lower() in ["yes", "true", "eligible"]:
            query["goodies"] = {"$in": ["Yes", "yes", "YES", True]}
        elif goodies_filter.lower() in ["no", "false", "not eligible"]:
            query["goodies"] = {"$in": ["No", "no", "NO", False, None]}

    reg_docs = list(db.registrations.find(query))
    if not reg_docs:
        return jsonify({"error": "No registrations found in database matching specified criteria."}), 404

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if mode == "overwrite":
        db.students.delete_many({})
        db.invites.delete_many({})
        students_to_insert = []
        invites_to_insert = []

        for r in reg_docs:
            token = secrets.token_urlsafe(12) if generate_tokens else None
            s_doc = {
                "name": r.get("name") or "Student",
                "phone": clean_phone_number(r.get("phone")),
                "email": r.get("email", ""),
                "acm_id": r.get("aceId") or "",
                "branch": r.get("branch", ""),
                "year": r.get("year", "1st Year"),
                "goodies": r.get("goodies", "Yes"),
                "gender": r.get("gender", ""),
                "registration_id": str(r["_id"]),
                "extra_data": {
                    "email": r.get("email", ""),
                    "gender": r.get("gender", ""),
                    "mode": r.get("mode", ""),
                    "registrationType": r.get("registrationType", ""),
                    "payment": r.get("payment", "")
                },
                "assigned_ebm_id": None,
                "token": token,
                "is_contacted": 0,
                "contacted_at": None,
                "created_at": now_str
            }
            students_to_insert.append(s_doc)
            if token:
                invites_to_insert.append({
                    "token": token,
                    "assigned_to": r.get("name") or "Student",
                    "student_id": None,
                    "is_used": 0,
                    "used_at": None,
                    "ip_address": None,
                    "device_id": None,
                    "created_at": now_str
                })

        res = db.students.insert_many(students_to_insert)
        if generate_tokens and invites_to_insert:
            for inv, s_id in zip(invites_to_insert, res.inserted_ids):
                inv["student_id"] = str(s_id)
            db.invites.insert_many(invites_to_insert)

        return jsonify({
            "success": True,
            "message": f"Successfully imported {len(students_to_insert)} student(s) directly from ACE_REG registrations (Overwrite Mode).",
            "imported_count": len(students_to_insert),
            "tokens_generated": generate_tokens
        })

    else:
        # Sync mode: High-performance bulk upsert
        existing_cursor = list(db.students.find({}, {"_id": 1, "registration_id": 1, "acm_id": 1, "phone": 1, "token": 1}))
        existing_by_reg = {str(s["registration_id"]): s for s in existing_cursor if s.get("registration_id")}
        existing_by_acm = {str(s["acm_id"]).strip().upper(): s for s in existing_cursor if s.get("acm_id")}
        existing_by_phone = {str(s["phone"]).strip(): s for s in existing_cursor if s.get("phone")}

        students_to_insert = []
        invites_for_new = []
        update_operations = []
        invites_for_updated = []

        for r in reg_docs:
            ace_id = (r.get("aceId") or "").strip()
            phone = clean_phone_number(r.get("phone"))
            reg_id = str(r["_id"])

            existing = (
                existing_by_reg.get(reg_id) or
                (existing_by_acm.get(ace_id.upper()) if ace_id else None) or
                (existing_by_phone.get(phone) if phone else None)
            )

            if existing:
                update_fields = {
                    "name": r.get("name") or "Student",
                    "email": r.get("email", ""),
                    "phone": phone,
                    "acm_id": ace_id,
                    "branch": r.get("branch", ""),
                    "year": r.get("year", "1st Year"),
                    "goodies": r.get("goodies", "Yes"),
                    "gender": r.get("gender", ""),
                    "registration_id": reg_id
                }
                if generate_tokens and not existing.get("token"):
                    new_tok = secrets.token_urlsafe(12)
                    update_fields["token"] = new_tok
                    existing["token"] = new_tok
                    invites_for_updated.append({
                        "token": new_tok,
                        "assigned_to": r.get("name") or "Student",
                        "student_id": str(existing["_id"]),
                        "is_used": 0,
                        "used_at": None,
                        "ip_address": None,
                        "device_id": None,
                        "created_at": now_str
                    })
                update_operations.append(UpdateOne({"_id": existing["_id"]}, {"$set": update_fields}))
            else:
                new_tok = secrets.token_urlsafe(12) if generate_tokens else None
                s_doc = {
                    "name": r.get("name") or "Student",
                    "phone": phone,
                    "email": r.get("email", ""),
                    "acm_id": ace_id,
                    "branch": r.get("branch", ""),
                    "year": r.get("year", "1st Year"),
                    "goodies": r.get("goodies", "Yes"),
                    "gender": r.get("gender", ""),
                    "registration_id": reg_id,
                    "extra_data": {
                        "email": r.get("email", ""),
                        "gender": r.get("gender", ""),
                        "mode": r.get("mode", ""),
                        "registrationType": r.get("registrationType", ""),
                        "payment": r.get("payment", "")
                    },
                    "assigned_ebm_id": None,
                    "token": new_tok,
                    "is_contacted": 0,
                    "contacted_at": None,
                    "created_at": now_str
                }
                students_to_insert.append(s_doc)
                if new_tok:
                    invites_for_new.append({
                        "token": new_tok,
                        "assigned_to": r.get("name") or "Student",
                        "student_id": None,
                        "is_used": 0,
                        "used_at": None,
                        "ip_address": None,
                        "device_id": None,
                        "created_at": now_str
                    })

        updated_count = len(update_operations)
        inserted_count = len(students_to_insert)

        if update_operations:
            db.students.bulk_write(update_operations, ordered=False)
        if invites_for_updated:
            db.invites.insert_many(invites_for_updated)

        if students_to_insert:
            res = db.students.insert_many(students_to_insert)
            if generate_tokens and invites_for_new:
                for inv, s_id in zip(invites_for_new, res.inserted_ids):
                    inv["student_id"] = str(s_id)
                db.invites.insert_many(invites_for_new)

        return jsonify({
            "success": True,
            "message": f"Sync from ACE_REG complete: {inserted_count} new student(s) added, {updated_count} updated.",
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "tokens_generated": generate_tokens
        })

# ----------------- DYNAMIC FILTER OPTIONS -----------------
@admin_bp.route("/api/admin/filter-options", methods=["GET"])
@admin_required
def api_get_filter_options():
    db = get_db()
    # Collect branches from students and registrations collections
    student_branches = [b for b in db.students.distinct("branch") if b]
    reg_branches = [b for b in db.registrations.distinct("branch") if b]
    all_branches = sorted(list(set(student_branches + reg_branches)))

    years = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
    goodies = ["Yes", "No"]
    genders = ["Male", "Female"]
    return jsonify({
        "years": years,
        "goodies": goodies,
        "branches": all_branches,
        "genders": genders
    })

# ----------------- EBM CSV UPLOAD (GOOGLE SHEET COMPATIBLE) -----------------
@admin_bp.route("/api/admin/upload/ebm", methods=["POST"])
@admin_required
def api_upload_ebm():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file or not file.filename.endswith(".csv"):
        return jsonify({"error": "Please upload a valid .csv file"}), 400

    try:
        df = read_csv_dataframe(file)
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {str(e)}"}), 400

    if df.empty:
        return jsonify({"error": "Uploaded CSV file is empty"}), 400

    # Flexible column matching for Google Sheets & standard templates
    col_map = {}
    for col in df.columns:
        norm = col.strip().lower().replace("_", " ").replace("-", " ")
        if norm in ["full name", "name", "ebm name", "candidate name"] and "name" not in col_map:
            col_map["name"] = col
        elif norm in ["password", "pass", "pwd", "secret"] and "password" not in col_map:
            col_map["password"] = col
        elif norm in ["confirmation number", "conf number", "conf no", "registration number", "id"] and "confirmation_number" not in col_map:
            col_map["confirmation_number"] = col
        elif any(k in norm for k in ["phone", "mobile", "whatsapp", "contact"]) and "phone" not in col_map:
            col_map["phone"] = col
        elif norm in ["weight", "quota", "capacity"] and "weight" not in col_map:
            col_map["weight"] = col
        elif norm in ["email", "email address"] and "email" not in col_map:
            col_map["email"] = col
        elif norm in ["branch", "dept", "department"] and "branch" not in col_map:
            col_map["branch"] = col

    if "name" not in col_map:
        col_map["name"] = df.columns[0]

    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upserted_count = 0

    for _, row in df.iterrows():
        name_val = str(row[col_map["name"]]).strip() if pd.notna(row[col_map["name"]]) else ""
        if not name_val:
            continue

        # Determine password: check 'password' column, fallback to 'confirmation_number', fallback to 'ebm123'
        raw_pw = ""
        if "password" in col_map and pd.notna(row[col_map["password"]]):
            raw_pw = str(row[col_map["password"]]).strip()
        elif "confirmation_number" in col_map and pd.notna(row[col_map["confirmation_number"]]):
            raw_pw = str(row[col_map["confirmation_number"]]).strip()
        if not raw_pw:
            raw_pw = "ebm123"

        # Determine weight: default leads to 6, others to 4, capped 1-20
        default_weight = 6 if "lead" in name_val.lower() else 4
        weight_val = default_weight
        if "weight" in col_map and pd.notna(row[col_map["weight"]]):
            try:
                weight_val = min(20, max(1, int(row[col_map["weight"]])))
            except Exception:
                weight_val = default_weight

        phone_val = clean_phone_number(row[col_map["phone"]]) if "phone" in col_map and pd.notna(row[col_map["phone"]]) else ""
        email_val = str(row[col_map["email"]]).strip() if "email" in col_map and pd.notna(row[col_map["email"]]) else ""
        branch_val = str(row[col_map["branch"]]).strip() if "branch" in col_map and pd.notna(row[col_map["branch"]]) else ""

        # Extra data from remaining columns
        extra_dict = {}
        for c in df.columns:
            if c not in col_map.values() and pd.notna(row[c]):
                extra_dict[c] = str(row[c]).strip()

        username_val = re.sub(r"[^a-zA-Z0-9_]", "", name_val.lower().replace(" ", "_"))
        hashed_pw = generate_password_hash(raw_pw)

        # Upsert by exact name or username
        existing = db.ebms.find_one({
            "$or": [
                {"name": {"$regex": f"^{re.escape(name_val)}$", "$options": "i"}},
                {"username": username_val}
            ]
        })

        if existing:
            update_data = {
                "name": name_val,
                "phone": phone_val or existing.get("phone", ""),
                "weight": weight_val,
                "email": email_val or existing.get("email", ""),
                "branch": branch_val or existing.get("branch", ""),
                "extra_data": extra_dict
            }
            # Only update password if explicit password was provided
            if "password" in col_map or "confirmation_number" in col_map:
                update_data["password"] = hashed_pw
            db.ebms.update_one({"_id": existing["_id"]}, {"$set": update_data})
        else:
            db.ebms.insert_one({
                "name": name_val,
                "username": username_val,
                "password": hashed_pw,
                "phone": phone_val,
                "email": email_val,
                "branch": branch_val,
                "weight": weight_val,
                "role": "ebm",
                "extra_data": extra_dict,
                "created_at": now_str
            })
        upserted_count += 1

    return jsonify({
        "success": True,
        "message": f"Successfully processed {upserted_count} EBM team members from CSV into MongoDB.",
        "count": upserted_count
    })

# ----------------- EBM TEAM MANAGEMENT -----------------
@admin_bp.route("/api/admin/ebm/list", methods=["GET"])
@admin_required
def api_list_ebms():
    db = get_db()
    ebm_docs = list(db.ebms.find().sort([("weight", -1), ("name", 1)]))
    ebms = []

    for e in ebm_docs:
        e_id_str = str(e["_id"])
        assigned_count = db.students.count_documents({"assigned_ebm_id": e_id_str})
        contacted_count = db.students.count_documents({"assigned_ebm_id": e_id_str, "is_contacted": 1})

        tokens = [
            s["token"] for s in db.students.find(
                {"assigned_ebm_id": e_id_str, "token": {"$ne": None}},
                {"token": 1}
            ) if s.get("token")
        ]
        joined_count = db.invites.count_documents({"token": {"$in": tokens}, "is_used": 1}) if tokens else 0

        ebms.append({
            "id": e_id_str,
            "name": e.get("name", "EBM Member"),
            "username": e.get("username", e.get("name")),
            "role": e.get("role", "ebm"),
            "weight": e.get("weight", 4),
            "created_at": e.get("created_at", ""),
            "assigned_count": assigned_count,
            "contacted_count": contacted_count,
            "joined_count": joined_count
        })

    return jsonify({"ebms": ebms})

@admin_bp.route("/api/admin/ebm", methods=["POST"])
@admin_required
def api_create_ebm():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    username = data.get("username", "").strip() or re.sub(r"[^a-zA-Z0-9_]", "", name.lower().replace(" ", "_"))
    password = data.get("password", "").strip() or "ebm123"
    weight = min(20, max(1, int(data.get("weight", 4))))

    if not name:
        return jsonify({"error": "Name is required"}), 400

    db = get_db()
    existing = db.ebms.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if existing:
        return jsonify({"error": "An EBM with this name already exists"}), 400

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed_password = generate_password_hash(password)
    doc = {
        "name": name,
        "username": username.lower(),
        "password": hashed_password,
        "role": "ebm",
        "weight": weight,
        "created_at": now_str
    }
    db.ebms.insert_one(doc)

    return jsonify({"success": True, "message": f"EBM member '{name}' added successfully."})

@admin_bp.route("/api/admin/ebm/<ebm_id>", methods=["PUT"])
@admin_required
def api_update_ebm(ebm_id):
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    password = data.get("password", "").strip()
    weight = min(20, max(1, int(data.get("weight", 4))))

    db = get_db()
    oid = safe_object_id(ebm_id)
    query = {"$or": [{"_id": oid}, {"id": ebm_id}]}

    update_doc = {"weight": weight}
    if name:
        update_doc["name"] = name
    if password:
        update_doc["password"] = generate_password_hash(password)

    db.ebms.update_one(query, {"$set": update_doc})
    return jsonify({"success": True, "message": "EBM updated successfully"})

@admin_bp.route("/api/admin/ebm/<ebm_id>", methods=["DELETE"])
@admin_required
def api_delete_ebm(ebm_id):
    db = get_db()
    oid = safe_object_id(ebm_id)
    db.students.update_many({"assigned_ebm_id": str(ebm_id)}, {"$set": {"assigned_ebm_id": None}})
    db.ebms.delete_one({"$or": [{"_id": oid}, {"id": ebm_id}]})
    return jsonify({"success": True, "message": "EBM deleted and their students unassigned."})

# ----------------- BATCH SPLITTING -----------------
@admin_bp.route("/api/admin/batch/split", methods=["POST"])
@admin_required
def api_batch_split():
    data = request.get_json(silent=True) or {}
    reassign_all = bool(data.get("reassign_all", False))
    target_year = str(data.get("year", "")).strip()
    target_goodies = str(data.get("goodies", "")).strip()
    target_branch = str(data.get("branch", "")).strip()

    db = get_db()
    ebms = list(db.ebms.find().sort([("weight", -1), ("name", 1)]))

    if not ebms:
        return jsonify({"error": "No EBM members found. Please register or add EBMs first."}), 400

    query = {}
    if not reassign_all:
        query["$or"] = [{"assigned_ebm_id": None}, {"assigned_ebm_id": ""}]

    if target_year and target_year.lower() not in ["all", "any"]:
        query["year"] = {"$regex": f"^{re.escape(target_year)}", "$options": "i"}

    if target_goodies and target_goodies.lower() not in ["all", "any"]:
        if target_goodies.lower() in ["yes", "true", "eligible"]:
            query["goodies"] = {"$in": ["Yes", "yes", "YES", True, 1]}
        elif target_goodies.lower() in ["no", "false", "not eligible"]:
            query["goodies"] = {"$in": ["No", "no", "NO", False, 0, None]}

    if target_branch and target_branch.lower() not in ["all", "any"]:
        query["branch"] = {"$regex": f"^{re.escape(target_branch)}$", "$options": "i"}

    students = list(db.students.find(query).sort("_id", 1))

    if not students:
        return jsonify({"message": "No matching students to split."}), 200

    # Build fair interleaved weighted pool
    weights_map = {str(e["_id"]): min(20, max(1, int(e.get("weight", 4)))) for e in ebms}
    weighted_pool = []
    remaining_weights = dict(weights_map)
    while any(v > 0 for v in remaining_weights.values()):
        for e_id in weights_map:
            if remaining_weights[e_id] > 0:
                weighted_pool.append(e_id)
                remaining_weights[e_id] -= 1

    pool_len = len(weighted_pool)

    # Distribute continuously across the weighted pool rather than resetting index 0 every batch
    current_offset = 0
    if not reassign_all:
        current_offset = db.students.count_documents({
            "assigned_ebm_id": {"$nin": [None, ""]}
        })

    bulk_ops = []
    for idx, s in enumerate(students):
        assigned_ebm_id = weighted_pool[(current_offset + idx) % pool_len]
        bulk_ops.append(UpdateOne({"_id": s["_id"]}, {"$set": {"assigned_ebm_id": assigned_ebm_id}}))

    if bulk_ops:
        try:
            db.students.bulk_write(bulk_ops, ordered=False)
        except TypeError:
            for op in bulk_ops:
                db.students.update_one(op._filter, op._doc)

    return jsonify({
        "success": True,
        "message": f"Successfully distributed all {len(students)} students across {len(ebms)} EBM members based on weights.",
        "distributed_count": len(students)
    })

@admin_bp.route("/api/admin/batch/reassign", methods=["POST"])
@admin_required
def api_batch_reassign():
    data = request.get_json() or {}
    student_ids = data.get("student_ids", [])
    raw_ebm_id = data.get("ebm_id")

    if not student_ids:
        return jsonify({"error": "No students selected"}), 400

    target_ebm_id = None
    if raw_ebm_id is not None and str(raw_ebm_id).strip() not in ["", "unassigned", "null", "None", "-1"]:
        target_ebm_id = str(raw_ebm_id).strip()

    db = get_db()
    oids = [safe_object_id(sid) for sid in student_ids]
    db.students.update_many(
        {"$or": [{"_id": {"$in": oids}}, {"id": {"$in": student_ids}}]},
        {"$set": {"assigned_ebm_id": target_ebm_id}}
    )

    return jsonify({"success": True, "message": f"Successfully reassigned {len(student_ids)} student(s)."})

@admin_bp.route("/api/admin/batch/transfer", methods=["POST"])
@admin_required
def api_batch_transfer():
    data = request.get_json() or {}
    raw_from = data.get("from_ebm_id")
    raw_to = data.get("to_ebm_id")
    raw_count = data.get("count")
    student_ids = data.get("student_ids", [])

    from_ebm_id = str(raw_from).strip() if raw_from and str(raw_from).strip() not in ["", "unassigned", "null", "-1"] else None
    target_ebm_id = str(raw_to).strip() if raw_to and str(raw_to).strip() not in ["", "unassigned", "null", "-1"] else None

    db = get_db()
    if student_ids:
        oids = [safe_object_id(sid) for sid in student_ids]
        db.students.update_many(
            {"$or": [{"_id": {"$in": oids}}, {"id": {"$in": student_ids}}]},
            {"$set": {"assigned_ebm_id": target_ebm_id}}
        )
        moved_count = len(student_ids)
    elif raw_count:
        try:
            count = int(raw_count)
        except ValueError:
            return jsonify({"error": "Invalid student count"}), 400
        if count <= 0:
            return jsonify({"error": "Count must be greater than 0"}), 400

        query = {"assigned_ebm_id": from_ebm_id} if from_ebm_id else {"assigned_ebm_id": {"$in": [None, ""]}}
        docs = list(db.students.find(query).sort([("is_contacted", 1), ("_id", 1)]).limit(count))
        if not docs:
            return jsonify({"error": "No students available to transfer from selected source"}), 400

        doc_ids = [d["_id"] for d in docs]
        db.students.update_many({"_id": {"$in": doc_ids}}, {"$set": {"assigned_ebm_id": target_ebm_id}})
        moved_count = len(doc_ids)
    else:
        return jsonify({"error": "Please provide a count or specific student IDs to transfer"}), 400

    return jsonify({"success": True, "message": f"Successfully transferred {moved_count} student(s)."})

@admin_bp.route("/api/admin/students/<student_id>/assign", methods=["POST"])
@admin_required
def api_assign_single_student(student_id):
    data = request.get_json() or {}
    raw_ebm_id = data.get("ebm_id")
    target_ebm_id = str(raw_ebm_id).strip() if raw_ebm_id and str(raw_ebm_id).strip() not in ["", "unassigned", "null", "-1"] else None

    db = get_db()
    oid = safe_object_id(student_id)
    db.students.update_one({"$or": [{"_id": oid}, {"id": student_id}]}, {"$set": {"assigned_ebm_id": target_ebm_id}})

    ebm_name = "Unassigned"
    if target_ebm_id:
        e_doc = db.ebms.find_one({"$or": [{"_id": safe_object_id(target_ebm_id)}, {"id": target_ebm_id}]})
        if e_doc:
            ebm_name = e_doc.get("name", "EBM Member")

    return jsonify({
        "success": True,
        "message": f"Assigned to {ebm_name}",
        "ebm_id": target_ebm_id,
        "ebm_name": ebm_name
    })

# ----------------- DYNAMIC STUDENT DIRECTORY (YEAR & GOODIES) -----------------
@admin_bp.route("/api/admin/students", methods=["GET"])
@admin_required
def api_admin_students():
    ebm_id = request.args.get("ebm_id")
    search = request.args.get("search", "").strip()
    contacted = request.args.get("contacted")
    joined = request.args.get("joined")
    year = request.args.get("year", "").strip()
    goodies = request.args.get("goodies", "").strip()
    branch = request.args.get("branch", "").strip()
    gender = request.args.get("gender", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    limit = min(max(10, int(request.args.get("limit", 50))), 500)
    offset = (page - 1) * limit

    cfg = load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")
    db = get_db()

    filter_query = {}

    if ebm_id:
        if ebm_id == "unassigned":
            filter_query["assigned_ebm_id"] = {"$in": [None, ""]}
        else:
            filter_query["assigned_ebm_id"] = str(ebm_id)

    if contacted is not None and contacted != "":
        filter_query["is_contacted"] = int(contacted)

    # Dynamic Year Filter (matches 1, 1st Year, 2, 2nd Year, etc.)
    if year and year.lower() not in ["all", "any"]:
        filter_query["year"] = {"$regex": f"^{re.escape(year)}", "$options": "i"}

    # Dynamic Goodies Filter (Yes / No)
    if goodies and goodies.lower() not in ["all", "any"]:
        if goodies.lower() in ["yes", "true", "1", "eligible"]:
            filter_query["goodies"] = {"$in": [True, 1, "Yes", "yes", "YES", "Eligible", "eligible"]}
        elif goodies.lower() in ["no", "false", "0", "not eligible"]:
            filter_query["goodies"] = {"$in": [False, 0, "No", "no", "NO", "Not Eligible", None, ""]}

    # Dynamic Branch Filter
    if branch and branch.lower() not in ["all", "any"]:
        filter_query["branch"] = {"$regex": f"^{re.escape(branch)}$", "$options": "i"}

    # Dynamic Gender Filter
    if gender and gender.lower() not in ["all", "any"]:
        filter_query["gender"] = {"$regex": f"^{re.escape(gender)}$", "$options": "i"}

    if search:
        s_regex = {"$regex": re.escape(search), "$options": "i"}
        filter_query["$or"] = [{"name": s_regex}, {"phone": s_regex}, {"acm_id": s_regex}, {"email": s_regex}]

    # Handle joined filter via invite tokens if requested
    if joined is not None and joined != "":
        is_used_target = int(joined)
        used_tokens = [
            inv["token"] for inv in db.invites.find({"is_used": is_used_target}, {"token": 1})
        ]
        if is_used_target == 1:
            filter_query["token"] = {"$in": used_tokens}
        else:
            filter_query["$or"] = [
                {"token": {"$in": used_tokens}},
                {"token": None}
            ]

    total_count = db.students.count_documents(filter_query)
    student_docs = list(db.students.find(filter_query).sort("_id", 1).skip(offset).limit(limit))

    # Pre-fetch EBM names and token invite statuses
    ebm_map = {str(e["_id"]): e.get("name", "EBM Member") for e in db.ebms.find()}
    student_tokens = [s.get("token") for s in student_docs if s.get("token")]
    invites_map = {inv["token"]: inv for inv in db.invites.find({"token": {"$in": student_tokens}})} if student_tokens else {}

    students = []
    for s in student_docs:
        s_id = str(s["_id"])
        tok = s.get("token")
        inv = invites_map.get(tok, {}) if tok else {}

        students.append({
            "id": s_id,
            "name": s.get("name", "Student"),
            "phone": s.get("phone", ""),
            "email": s.get("email", ""),
            "gender": s.get("gender", ""),
            "acm_id": s.get("acm_id", ""),
            "branch": s.get("branch", ""),
            "year": s.get("year", "1"),
            "goodies": s.get("goodies", "Yes"),
            "extra_data": json.dumps(s.get("extra_data", {})) if isinstance(s.get("extra_data"), dict) else s.get("extra_data", ""),
            "token": tok or "",
            "full_invite_link": f"{base_url}/join/{tok}" if tok else "",
            "is_contacted": s.get("is_contacted", 0),
            "contacted_at": s.get("contacted_at", ""),
            "created_at": s.get("created_at", ""),
            "ebm_id": s.get("assigned_ebm_id"),
            "ebm_name": ebm_map.get(str(s.get("assigned_ebm_id")), "Unassigned"),
            "is_used": inv.get("is_used", 0),
            "used_at": inv.get("used_at", ""),
            "ip_address": inv.get("ip_address", "")
        })

    return jsonify({
        "students": students,
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": (total_count + limit - 1) // limit if limit else 1
    })

# ----------------- TOKEN RENEWAL & GENERATION -----------------
@admin_bp.route("/api/admin/tokens/renew/<student_id>", methods=["POST"])
@admin_required
def api_renew_token(student_id):
    data = request.get_json() or {}
    action = data.get("action", "reset")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()

    oid = safe_object_id(student_id)
    student = db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        return jsonify({"error": "Student not found"}), 404

    old_token = student.get("token")

    if action == "new_token" or not old_token:
        new_tok = secrets.token_urlsafe(12)
        db.students.update_one({"_id": student["_id"]}, {"$set": {"token": new_tok}})
        db.invites.insert_one({
            "token": new_tok,
            "assigned_to": student.get("name", "Student"),
            "student_id": str(student["_id"]),
            "is_used": 0,
            "used_at": None,
            "ip_address": None,
            "device_id": None,
            "created_at": now_str
        })
        token_to_return = new_tok
    else:
        db.invites.update_one(
            {"token": old_token},
            {"$set": {"is_used": 0, "used_at": None, "device_id": None, "ip_address": None}}
        )
        token_to_return = old_token

    return jsonify({
        "success": True,
        "message": f"Token renewed for {student.get('name')}",
        "token": token_to_return
    })

@admin_bp.route("/api/admin/students/<student_id>", methods=["DELETE"])
@admin_required
def api_delete_student(student_id):
    db = get_db()
    oid = safe_object_id(student_id)
    student = db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if student and student.get("token"):
        db.invites.delete_many({"token": student["token"]})
    db.students.delete_one({"$or": [{"_id": oid}, {"id": student_id}]})
    return jsonify({"success": True, "message": "Student deleted."})

@admin_bp.route("/api/admin/students/clear-all", methods=["POST"])
@admin_required
def api_clear_all_students():
    db = get_db()
    db.students.delete_many({})
    db.invites.delete_many({})
    return jsonify({"success": True, "message": "All students and associated invite links have been cleared."})

@admin_bp.route("/api/admin/export/links", methods=["GET"])
@admin_required
def api_export_links_csv():
    cfg = load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")
    db = get_db()

    student_docs = list(db.students.find().sort("_id", 1))
    ebm_map = {str(e["_id"]): e.get("name", "EBM Member") for e in db.ebms.find()}
    tokens = [s.get("token") for s in student_docs if s.get("token")]
    inv_map = {inv["token"]: inv for inv in db.invites.find({"token": {"$in": tokens}})} if tokens else {}

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Student ID", "Name", "Phone", "ACM ID", "Branch", "Year", "Goodies", "Assigned EBM",
        "One-Time Link", "Redeemed Status", "Redeemed At", "Contacted Status", "Contacted At", "IP Address"
    ])

    for s in student_docs:
        tok = s.get("token", "")
        inv = inv_map.get(tok, {})
        link = f"{base_url}/join/{tok}" if tok else ""
        status = "Redeemed" if inv.get("is_used") else ("Active" if tok else "No Token")
        contacted = "Yes" if s.get("is_contacted") else "No"
        writer.writerow([
            str(s["_id"]),
            s.get("name", ""),
            s.get("phone", ""),
            s.get("acm_id", ""),
            s.get("branch", ""),
            s.get("year", "1"),
            s.get("goodies", "Yes"),
            ebm_map.get(str(s.get("assigned_ebm_id")), "Unassigned"),
            link,
            status,
            inv.get("used_at", ""),
            contacted,
            s.get("contacted_at", ""),
            inv.get("ip_address", "")
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ebm_students_invite_links.csv"}
    )

# ----------------- MESSAGE TEMPLATES -----------------
@admin_bp.route("/api/templates", methods=["GET"])
def api_get_templates():
    db = get_db()
    tpls = list(db.message_templates.find().sort([("is_default", -1), ("_id", -1)]))
    result = []
    for t in tpls:
        result.append({
            "id": str(t["_id"]),
            "title": t.get("title", ""),
            "content": t.get("content", ""),
            "is_default": t.get("is_default", 0)
        })
    return jsonify({"templates": result})

@admin_bp.route("/api/templates", methods=["POST"])
@admin_required
def api_create_template():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    is_default = 1 if data.get("is_default") else 0

    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400

    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if is_default:
        db.message_templates.update_many({}, {"$set": {"is_default": 0}})

    res = db.message_templates.insert_one({
        "title": title,
        "content": content,
        "is_default": is_default,
        "created_at": now_str,
        "updated_at": now_str
    })
    return jsonify({"success": True, "message": "Message template saved.", "id": str(res.inserted_id)})

@admin_bp.route("/api/templates/<template_id>", methods=["PUT"])
@admin_required
def api_update_template(template_id):
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    oid = safe_object_id(template_id)
    db.message_templates.update_one(
        {"$or": [{"_id": oid}, {"id": template_id}]},
        {"$set": {"title": title, "content": content, "updated_at": now_str}}
    )
    return jsonify({"success": True, "message": "Template updated."})

@admin_bp.route("/api/templates/<template_id>/set-default", methods=["POST"])
@admin_required
def api_set_default_template(template_id):
    db = get_db()
    oid = safe_object_id(template_id)
    db.message_templates.update_many({}, {"$set": {"is_default": 0}})
    db.message_templates.update_one({"$or": [{"_id": oid}, {"id": template_id}]}, {"$set": {"is_default": 1}})
    return jsonify({"success": True, "message": "Default template updated."})

@admin_bp.route("/api/templates/<template_id>", methods=["DELETE"])
@admin_required
def api_delete_template(template_id):
    db = get_db()
    oid = safe_object_id(template_id)
    db.message_templates.delete_one({"$or": [{"_id": oid}, {"id": template_id}]})
    return jsonify({"success": True, "message": "Template deleted."})

# ----------------- CONFIG SETTINGS -----------------
@admin_bp.route("/api/admin/config", methods=["GET", "POST"])
@admin_required
def api_admin_config():
    if request.method == "POST":
        data = request.get_json() or {}
        cfg = load_config()
        if data.get("whatsapp_group_link"):
            cfg["whatsapp_group_link"] = data["whatsapp_group_link"].strip()
        if data.get("base_url"):
            cfg["base_url"] = data["base_url"].strip().rstrip("/")
        if data.get("admin_password"):
            cfg["admin_password"] = data["admin_password"].strip()
        save_config(cfg)
        return jsonify({"success": True, "message": "Configuration saved successfully."})

    cfg = load_config()
    safe_cfg = {
        "whatsapp_group_link": cfg.get("whatsapp_group_link", ""),
        "base_url": cfg.get("base_url", "")
    }
    return jsonify(safe_cfg)
