import json
import secrets
from datetime import datetime
import io
import csv
import re
import sqlite3
import pandas as pd
from flask import Blueprint, request, jsonify, Response
from werkzeug.security import generate_password_hash
from backend.config import load_config, save_config, get_db
from backend.routes.auth import admin_required

admin_bp = Blueprint("admin", __name__)

def clean_phone_number(val):
    if val is None or pd.isna(val):
        return ""
    digits = re.sub(r"\D", "", str(val))
    return digits

@admin_bp.route("/api/admin/overview", methods=["GET"])
@admin_required
def api_admin_overview():
    cfg = load_config()
    with get_db() as conn:
        cursor = conn.cursor()

        # Students stats
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM students WHERE is_contacted = 1")
        contacted_students = cursor.fetchone()[0]

        # Invites stats
        cursor.execute("SELECT COUNT(*) FROM invites")
        total_invites = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM invites WHERE is_used = 1")
        used_invites = cursor.fetchone()[0]

        # EBM stats
        cursor.execute("""
            SELECT e.id, e.name, e.username, e.weight,
                   COUNT(s.id) as assigned_count,
                   SUM(CASE WHEN s.is_contacted = 1 THEN 1 ELSE 0 END) as contacted_count,
                   SUM(CASE WHEN i.is_used = 1 THEN 1 ELSE 0 END) as joined_count
            FROM ebm_members e
            LEFT JOIN students s ON s.assigned_ebm_id = e.id
            LEFT JOIN invites i ON s.token = i.token
            GROUP BY e.id
            ORDER BY e.weight DESC, e.name ASC
        """)
        ebm_summary = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT COUNT(*) FROM students WHERE assigned_ebm_id IS NULL OR assigned_ebm_id = ''")
        unassigned_students = cursor.fetchone()[0]

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

# ----------------- DYNAMIC CSV INGESTION (PANDAS) -----------------

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

    # Flexible case-insensitive column matching
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

    if "name" not in col_map:
        col_map["name"] = df.columns[0]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upload_mode = request.form.get("mode", "overwrite").strip().lower()

    if upload_mode == "overwrite":
        # Prepare all data in memory FIRST so failures never delete existing data
        students_to_insert = []
        invites_to_insert = []

        for _, row in df.iterrows():
            name_val = str(row[col_map["name"]]).strip() if pd.notna(row[col_map["name"]]) else "Student"
            phone_raw = row[col_map["phone"]] if "phone" in col_map and pd.notna(row[col_map["phone"]]) else ""
            phone_val = clean_phone_number(phone_raw)
            acm_id_val = str(row[col_map["acm_id"]]).strip() if "acm_id" in col_map and pd.notna(row[col_map["acm_id"]]) else ""
            branch_val = str(row[col_map["branch"]]).strip() if "branch" in col_map and pd.notna(row[col_map["branch"]]) else ""

            extra_dict = {}
            for c in df.columns:
                if c not in col_map.values() and pd.notna(row[c]):
                    extra_dict[c] = str(row[c]).strip()
            extra_json = json.dumps(extra_dict) if extra_dict else None

            token = secrets.token_urlsafe(12)
            students_to_insert.append((name_val, phone_val, acm_id_val, branch_val, extra_json, token, 0, None, now_str))
            invites_to_insert.append((token, name_val, 0, None, None, now_str))

        with get_db() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM invites WHERE student_id IS NOT NULL")
                cursor.execute("DELETE FROM students")

                for s, inv in zip(students_to_insert, invites_to_insert):
                    cursor.execute("""
                        INSERT INTO students (name, phone, acm_id, branch, extra_data, token, is_contacted, contacted_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, s)
                    student_id = cursor.lastrowid
                    cursor.execute("""
                        INSERT INTO invites (token, assigned_to, student_id, is_used, used_at, ip_address, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (inv[0], inv[1], student_id, inv[2], inv[3], inv[4], inv[5]))
                conn.commit()
            except Exception as e:
                conn.rollback()
                return jsonify({"error": f"Database transaction failed during overwrite: {str(e)}"}), 500

        return jsonify({
            "success": True,
            "message": f"Successfully replaced student roster: {len(students_to_insert)} fresh students ingested with new secure tokens.",
            "count": len(students_to_insert),
            "mode": "overwrite",
            "detected_columns": list(col_map.keys())
        })

    else:
        with get_db() as conn:
            cursor = conn.cursor()
            try:
                updated_count = 0
                inserted_count = 0

                for _, row in df.iterrows():
                    name_val = str(row[col_map["name"]]).strip() if pd.notna(row[col_map["name"]]) else "Student"
                    phone_raw = row[col_map["phone"]] if "phone" in col_map and pd.notna(row[col_map["phone"]]) else ""
                    phone_val = clean_phone_number(phone_raw)
                    acm_id_val = str(row[col_map["acm_id"]]).strip() if "acm_id" in col_map and pd.notna(row[col_map["acm_id"]]) else ""
                    branch_val = str(row[col_map["branch"]]).strip() if "branch" in col_map and pd.notna(row[col_map["branch"]]) else ""

                    extra_dict = {}
                    for c in df.columns:
                        if c not in col_map.values() and pd.notna(row[c]):
                            extra_dict[c] = str(row[c]).strip()
                    extra_json = json.dumps(extra_dict) if extra_dict else None

                    existing = None
                    if acm_id_val:
                        cursor.execute("SELECT * FROM students WHERE LOWER(acm_id) = ?", (acm_id_val.lower(),))
                        existing = cursor.fetchone()
                    if not existing and phone_val:
                        cursor.execute("SELECT * FROM students WHERE phone = ?", (phone_val,))
                        existing = cursor.fetchone()
                    if not existing and name_val:
                        cursor.execute("SELECT * FROM students WHERE LOWER(name) = ?", (name_val.lower(),))
                        existing = cursor.fetchone()

                    if existing:
                        cursor.execute("""
                            UPDATE students
                            SET name = ?, phone = ?, acm_id = ?, branch = ?, extra_data = ?
                            WHERE id = ?
                        """, (name_val, phone_val, acm_id_val, branch_val, extra_json, existing["id"]))
                        if existing["token"]:
                            cursor.execute("UPDATE invites SET assigned_to = ? WHERE token = ?", (name_val, existing["token"]))
                        updated_count += 1
                    else:
                        token = secrets.token_urlsafe(12)
                        cursor.execute("""
                            INSERT INTO students (name, phone, acm_id, branch, extra_data, token, is_contacted, contacted_at, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?)
                        """, (name_val, phone_val, acm_id_val, branch_val, extra_json, token, now_str))
                        student_id = cursor.lastrowid
                        cursor.execute("""
                            INSERT INTO invites (token, assigned_to, student_id, is_used, used_at, ip_address, created_at)
                            VALUES (?, ?, ?, 0, NULL, NULL, ?)
                        """, (token, name_val, student_id, now_str))
                        inserted_count += 1

                conn.commit()
            except Exception as e:
                conn.rollback()
                return jsonify({"error": f"Database transaction failed during sync: {str(e)}"}), 500

        return jsonify({
            "success": True,
            "message": f"Sync complete: {updated_count} students updated, {inserted_count} new students added.",
            "count": updated_count + inserted_count,
            "mode": "sync",
            "detected_columns": list(col_map.keys())
        })

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

    col_map = {}
    for col in df.columns:
        norm = col.strip().lower().replace("_", " ")
        if norm in ["name", "ebm name", "member name", "team member"] and "name" not in col_map:
            col_map["name"] = col
        elif norm in ["username", "user", "login id", "login"] and "username" not in col_map:
            col_map["username"] = col
        elif norm in ["password", "pass", "pin", "credential"] and "password" not in col_map:
            col_map["password"] = col
        elif norm in ["weight", "weighting", "quota", "ratio"] and "weight" not in col_map:
            col_map["weight"] = col

    if "name" not in col_map:
        col_map["name"] = df.columns[0]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ebm_to_upsert = []

    for _, row in df.iterrows():
        name_val = str(row[col_map["name"]]).strip() if pd.notna(row[col_map["name"]]) else "EBM Member"
        if not name_val or name_val.lower() == "nan":
            continue

        if "username" in col_map and pd.notna(row[col_map["username"]]):
            username_val = str(row[col_map["username"]]).strip().lower()
        else:
            username_val = re.sub(r"[^a-zA-Z0-9]", "", name_val.lower().split()[0])
            if not username_val:
                username_val = f"ebm{secrets.token_hex(2)}"

        if "password" in col_map and pd.notna(row[col_map["password"]]):
            password_val = str(row[col_map["password"]]).strip()
        else:
            password_val = "ebm123"

        if "weight" in col_map and pd.notna(row[col_map["weight"]]):
            try:
                weight_val = int(row[col_map["weight"]])
            except ValueError:
                weight_val = 4
        else:
            if any(lead in name_val.lower() for lead in ["lead", "head", "admin", "coordinator"]):
                weight_val = 6
            else:
                weight_val = 4

        # Server-side weight cap (between 1 and 20) and secure password hashing
        weight_val = min(20, max(1, weight_val))
        hashed_password = generate_password_hash(password_val)

        ebm_to_upsert.append((name_val, username_val, hashed_password, weight_val, now_str))

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            for e in ebm_to_upsert:
                cursor.execute("""
                    INSERT INTO ebm_members (name, username, password, weight, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        name=excluded.name,
                        password=excluded.password,
                        weight=excluded.weight
                """, e)
            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Database transaction failed: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "message": f"Successfully parsed and updated {len(ebm_to_upsert)} EBM team members.",
        "count": len(ebm_to_upsert)
    })

# ----------------- EBM CRUD MANAGEMENT -----------------

@admin_bp.route("/api/admin/ebm/list", methods=["GET"])
@admin_required
def api_list_ebms():
    with get_db() as conn:
        cursor = conn.cursor()
        # Plaintext and hashed passwords are intentionally excluded from the query for security
        cursor.execute("""
            SELECT e.id, e.name, e.username, e.role, e.weight, e.created_at,
                   COUNT(s.id) as assigned_count,
                   SUM(CASE WHEN s.is_contacted = 1 THEN 1 ELSE 0 END) as contacted_count,
                   SUM(CASE WHEN i.is_used = 1 THEN 1 ELSE 0 END) as joined_count
            FROM ebm_members e
            LEFT JOIN students s ON s.assigned_ebm_id = e.id
            LEFT JOIN invites i ON s.token = i.token
            GROUP BY e.id
            ORDER BY e.weight DESC, e.name ASC
        """)
        ebms = [dict(r) for r in cursor.fetchall()]
    return jsonify({"ebms": ebms})

@admin_bp.route("/api/admin/ebm", methods=["POST"])
@admin_required
def api_create_ebm():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip() or "ebm123"
    weight = min(20, max(1, int(data.get("weight", 4))))

    if not name or not username:
        return jsonify({"error": "Name and username are required"}), 400

    hashed_password = generate_password_hash(password)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT INTO ebm_members (name, username, password, weight, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, username, hashed_password, weight, now_str))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "An EBM with this username already exists"}), 400

    return jsonify({"success": True, "message": f"EBM member {name} added."})

@admin_bp.route("/api/admin/ebm/<int:ebm_id>", methods=["PUT"])
@admin_required
def api_update_ebm(ebm_id):
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    password = data.get("password", "").strip()
    weight = min(20, max(1, int(data.get("weight", 4))))

    with get_db() as conn:
        cursor = conn.cursor()
        if password:
            hashed_password = generate_password_hash(password)
            cursor.execute("""
                UPDATE ebm_members SET name = ?, password = ?, weight = ? WHERE id = ?
            """, (name, hashed_password, weight, ebm_id))
        else:
            cursor.execute("""
                UPDATE ebm_members SET name = ?, weight = ? WHERE id = ?
            """, (name, weight, ebm_id))
        conn.commit()
    return jsonify({"success": True, "message": "EBM updated successfully"})

@admin_bp.route("/api/admin/ebm/<int:ebm_id>", methods=["DELETE"])
@admin_required
def api_delete_ebm(ebm_id):
    with get_db() as conn:
        conn.execute("UPDATE students SET assigned_ebm_id = NULL WHERE assigned_ebm_id = ?", (ebm_id,))
        conn.execute("DELETE FROM ebm_members WHERE id = ?", (ebm_id,))
        conn.commit()
    return jsonify({"success": True, "message": "EBM deleted and their students unassigned."})

# ----------------- BATCH SPLITTING -----------------

@admin_bp.route("/api/admin/batch/split", methods=["POST"])
@admin_required
def api_batch_split():
    data = request.get_json() or {}
    reassign_all = bool(data.get("reassign_all", False))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, weight FROM ebm_members ORDER BY weight DESC, id ASC")
        ebms = cursor.fetchall()

        if not ebms:
            return jsonify({"error": "No EBM members found. Please add or upload EBMs first."}), 400

        if reassign_all:
            cursor.execute("SELECT id FROM students ORDER BY id ASC")
        else:
            cursor.execute("SELECT id FROM students WHERE assigned_ebm_id IS NULL ORDER BY id ASC")
        students = cursor.fetchall()

        if not students:
            return jsonify({"message": "No unassigned students to split."}), 200

        # Build weighted pool with weights capped 1-20
        weighted_pool = []
        for e in ebms:
            w = min(20, max(1, int(e["weight"] or 1)))
            weighted_pool.extend([e["id"]] * w)

        pool_len = len(weighted_pool)

        # Distribute continuously across the weighted pool rather than resetting index 0 every batch
        current_offset = 0
        if not reassign_all:
            cursor.execute("SELECT COUNT(*) FROM students WHERE assigned_ebm_id IS NOT NULL")
            current_offset = cursor.fetchone()[0]

        assignments = []
        for idx, s in enumerate(students):
            assigned_ebm_id = weighted_pool[(current_offset + idx) % pool_len]
            assignments.append((assigned_ebm_id, s["id"]))

        cursor.executemany("UPDATE students SET assigned_ebm_id = ? WHERE id = ?", assignments)
        conn.commit()

    return jsonify({
        "success": True,
        "message": f"Successfully distributed {len(students)} students across {len(ebms)} EBM members based on weights.",
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
        try:
            target_ebm_id = int(raw_ebm_id)
        except ValueError:
            target_ebm_id = None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "UPDATE students SET assigned_ebm_id = ? WHERE id = ?",
            [(target_ebm_id, sid) for sid in student_ids]
        )
        conn.commit()

    return jsonify({"success": True, "message": f"Successfully reassigned {len(student_ids)} student(s)."})

@admin_bp.route("/api/admin/batch/transfer", methods=["POST"])
@admin_required
def api_batch_transfer():
    data = request.get_json() or {}
    raw_from = data.get("from_ebm_id")
    raw_to = data.get("to_ebm_id")
    raw_count = data.get("count")
    student_ids = data.get("student_ids", [])

    from_ebm_id = None
    if raw_from is not None and str(raw_from).strip() not in ["", "unassigned", "null", "None", "-1"]:
        try:
            from_ebm_id = int(raw_from)
        except ValueError:
            from_ebm_id = None

    target_ebm_id = None
    if raw_to is not None and str(raw_to).strip() not in ["", "unassigned", "null", "None", "-1"]:
        try:
            target_ebm_id = int(raw_to)
        except ValueError:
            target_ebm_id = None

    with get_db() as conn:
        cursor = conn.cursor()
        if student_ids:
            cursor.executemany(
                "UPDATE students SET assigned_ebm_id = ? WHERE id = ?",
                [(target_ebm_id, sid) for sid in student_ids]
            )
            moved_count = len(student_ids)
        elif raw_count:
            try:
                count = int(raw_count)
            except ValueError:
                return jsonify({"error": "Invalid student count"}), 400
            if count <= 0:
                return jsonify({"error": "Count must be greater than 0"}), 400

            if from_ebm_id is not None:
                cursor.execute("""
                    SELECT id FROM students 
                    WHERE assigned_ebm_id = ?
                    ORDER BY is_contacted ASC, id ASC
                    LIMIT ?
                """, (from_ebm_id, count))
            else:
                cursor.execute("""
                    SELECT id FROM students 
                    WHERE assigned_ebm_id IS NULL
                    ORDER BY is_contacted ASC, id ASC
                    LIMIT ?
                """, (count,))
            ids_to_move = [r[0] for r in cursor.fetchall()]
            if not ids_to_move:
                return jsonify({"error": "No students available to transfer from selected source"}), 400

            cursor.executemany(
                "UPDATE students SET assigned_ebm_id = ? WHERE id = ?",
                [(target_ebm_id, sid) for sid in ids_to_move]
            )
            moved_count = len(ids_to_move)
        else:
            return jsonify({"error": "Please provide a count or specific student IDs to transfer"}), 400

        conn.commit()

    return jsonify({
        "success": True, 
        "message": f"Successfully transferred {moved_count} student(s)."
    })

@admin_bp.route("/api/admin/students/<int:student_id>/assign", methods=["POST"])
@admin_required
def api_assign_single_student(student_id):
    data = request.get_json() or {}
    raw_ebm_id = data.get("ebm_id")
    target_ebm_id = None
    if raw_ebm_id is not None and str(raw_ebm_id).strip() not in ["", "unassigned", "null", "None", "-1"]:
        try:
            target_ebm_id = int(raw_ebm_id)
        except ValueError:
            target_ebm_id = None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET assigned_ebm_id = ? WHERE id = ?", (target_ebm_id, student_id))
        
        ebm_name = "Unassigned"
        if target_ebm_id:
            cursor.execute("SELECT name FROM ebm_members WHERE id = ?", (target_ebm_id,))
            row = cursor.fetchone()
            if row:
                ebm_name = row[0]
        conn.commit()

    return jsonify({
        "success": True,
        "message": f"Assigned to {ebm_name}",
        "ebm_id": target_ebm_id,
        "ebm_name": ebm_name
    })

# ----------------- STUDENT DIRECTORY & TOKEN RENEWAL -----------------

@admin_bp.route("/api/admin/students", methods=["GET"])
@admin_required
def api_admin_students():
    ebm_id = request.args.get("ebm_id")
    search = request.args.get("search", "").strip()
    contacted = request.args.get("contacted")
    joined = request.args.get("joined")
    page = max(1, int(request.args.get("page", 1)))
    limit = min(max(10, int(request.args.get("limit", 50))), 500)
    offset = (page - 1) * limit

    cfg = load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

    query = """
        SELECT s.id, s.name, s.phone, s.acm_id, s.branch, s.extra_data, s.token,
               s.is_contacted, s.contacted_at, s.created_at,
               e.id as ebm_id, e.name as ebm_name,
               i.is_used, i.used_at, i.ip_address
        FROM students s
        LEFT JOIN ebm_members e ON s.assigned_ebm_id = e.id
        LEFT JOIN invites i ON s.token = i.token
        WHERE 1=1
    """
    params = []

    if ebm_id:
        if ebm_id == "unassigned":
            query += " AND s.assigned_ebm_id IS NULL"
        else:
            query += " AND s.assigned_ebm_id = ?"
            params.append(ebm_id)
    if contacted is not None and contacted != "":
        query += " AND s.is_contacted = ?"
        params.append(int(contacted))
    if joined is not None and joined != "":
        query += " AND i.is_used = ?"
        params.append(int(joined))
    if search:
        query += " AND (s.name LIKE ? OR s.phone LIKE ? OR s.acm_id LIKE ?)"
        s_term = f"%{search}%"
        params.extend([s_term, s_term, s_term])

    count_query = f"SELECT COUNT(*) FROM ({query})"
    query += f" ORDER BY s.id ASC LIMIT {limit} OFFSET {offset}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        cursor.execute(query, params)
        rows = cursor.fetchall()

        students = []
        for r in rows:
            d = dict(r)
            d["full_invite_link"] = f"{base_url}/join/{d['token']}" if d.get("token") else ""
            students.append(d)

    return jsonify({
        "students": students,
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": (total_count + limit - 1) // limit if limit else 1
    })

@admin_bp.route("/api/admin/tokens/renew/<int:student_id>", methods=["POST"])
@admin_required
def api_renew_token(student_id):
    data = request.get_json() or {}
    action = data.get("action", "reset")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
        student = cursor.fetchone()
        if not student:
            return jsonify({"error": "Student not found"}), 404

        old_token = student["token"]

        if action == "new_token" or not old_token:
            new_tok = secrets.token_urlsafe(12)
            cursor.execute("UPDATE students SET token = ? WHERE id = ?", (new_tok, student_id))
            cursor.execute("""
                INSERT INTO invites (token, assigned_to, student_id, is_used, used_at, ip_address, created_at)
                VALUES (?, ?, ?, 0, NULL, NULL, ?)
            """, (new_tok, student["name"], student_id, now_str))
            token_to_return = new_tok
        else:
            cursor.execute("""
                UPDATE invites 
                SET is_used = 0, used_at = NULL, device_id = NULL, ip_address = NULL
                WHERE token = ?
            """, (old_token,))
            token_to_return = old_token

        conn.commit()

    return jsonify({
        "success": True,
        "message": f"Token renewed for {student['name']}",
        "token": token_to_return
    })

@admin_bp.route("/api/admin/students/<int:student_id>", methods=["DELETE"])
@admin_required
def api_delete_student(student_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM students WHERE id = ?", (student_id,))
        student = cursor.fetchone()
        if student and student["token"]:
            cursor.execute("DELETE FROM invites WHERE token = ?", (student["token"],))
        cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()
    return jsonify({"success": True, "message": "Student deleted."})

@admin_bp.route("/api/admin/students/clear-all", methods=["POST"])
@admin_required
def api_clear_all_students():
    with get_db() as conn:
        conn.execute("DELETE FROM students")
        conn.execute("DELETE FROM invites WHERE student_id IS NOT NULL")
        conn.commit()
    return jsonify({"success": True, "message": "All students and associated invite links have been cleared."})

@admin_bp.route("/api/admin/export/links", methods=["GET"])
@admin_required
def api_export_links_csv():
    cfg = load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.phone, s.acm_id, s.branch, s.is_contacted, s.contacted_at,
                   e.name as assigned_ebm,
                   i.token, i.is_used, i.used_at, i.ip_address, s.created_at
            FROM students s
            LEFT JOIN ebm_members e ON s.assigned_ebm_id = e.id
            LEFT JOIN invites i ON s.token = i.token
            ORDER BY s.id ASC
        """)
        records = cursor.fetchall()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Student ID", "Name", "Phone", "ACM ID", "Branch", "Assigned EBM",
        "One-Time Link", "Redeemed Status", "Redeemed At", "Contacted Status", "Contacted At", "IP Address"
    ])

    for r in records:
        link = f"{base_url}/join/{r['token']}" if r["token"] else ""
        status = "Redeemed" if r["is_used"] else "Active"
        contacted = "Yes" if r["is_contacted"] else "No"
        writer.writerow([
            r["id"],
            r["name"],
            r["phone"] or "",
            r["acm_id"] or "",
            r["branch"] or "",
            r["assigned_ebm"] or "Unassigned",
            link,
            status,
            r["used_at"] or "",
            contacted,
            r["contacted_at"] or "",
            r["ip_address"] or ""
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ebm_students_invite_links.csv"}
    )

# ----------------- MESSAGE TEMPLATES -----------------

@admin_bp.route("/api/templates", methods=["GET"])
def api_get_templates():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM message_templates ORDER BY is_default DESC, id DESC")
        templates = [dict(r) for r in cursor.fetchall()]
    return jsonify({"templates": templates})

@admin_bp.route("/api/templates", methods=["POST"])
@admin_required
def api_create_template():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    is_default = 1 if data.get("is_default") else 0

    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        if is_default:
            cursor.execute("UPDATE message_templates SET is_default = 0")
        cursor.execute("""
            INSERT INTO message_templates (title, content, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (title, content, is_default, now_str, now_str))
        conn.commit()

    return jsonify({"success": True, "message": "Message template saved."})

@admin_bp.route("/api/templates/<int:template_id>", methods=["PUT"])
@admin_required
def api_update_template(template_id):
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        conn.execute("""
            UPDATE message_templates SET title = ?, content = ?, updated_at = ? WHERE id = ?
        """, (title, content, now_str, template_id))
        conn.commit()

    return jsonify({"success": True, "message": "Template updated."})

@admin_bp.route("/api/templates/<int:template_id>/set-default", methods=["POST"])
@admin_required
def api_set_default_template(template_id):
    with get_db() as conn:
        conn.execute("UPDATE message_templates SET is_default = 0")
        conn.execute("UPDATE message_templates SET is_default = 1 WHERE id = ?", (template_id,))
        conn.commit()
    return jsonify({"success": True, "message": "Default template updated."})

@admin_bp.route("/api/templates/<int:template_id>", methods=["DELETE"])
@admin_required
def api_delete_template(template_id):
    with get_db() as conn:
        conn.execute("DELETE FROM message_templates WHERE id = ?", (template_id,))
        conn.commit()
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
