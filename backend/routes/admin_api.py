import asyncio
import io
import csv
import json
import re
import secrets
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Response, status
from fastapi.responses import StreamingResponse
from pymongo import UpdateOne
import pandas as pd
from werkzeug.security import generate_password_hash

from backend.config import async_load_config, async_save_config, get_async_db
from backend.routes.auth_api import require_admin

admin_router = APIRouter(tags=["Admin Operations"])

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
        if pd.isna(val):
            return ""
    except Exception:
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

# ----------------- ADMIN OVERVIEW STATS -----------------
@admin_router.get("/api/admin/overview")
async def api_admin_overview(request: Request):
    require_admin(request)
    cfg = await async_load_config()
    db = get_async_db()

    # Parallelize global counts with asyncio.gather
    (
        total_students,
        contacted_students,
        total_invites,
        used_invites,
        unassigned_students,
        ebm_docs,
        templates_count
    ) = await asyncio.gather(
        db.students.count_documents({}),
        db.students.count_documents({"is_contacted": 1}),
        db.invites.count_documents({}),
        db.invites.count_documents({"is_used": 1}),
        db.students.count_documents({"$or": [{"assigned_ebm_id": None}, {"assigned_ebm_id": ""}]}),
        db.ebms.find({}, {"_id": 1, "name": 1, "username": 1, "weight": 1}).sort([("weight", -1), ("name", 1)]).to_list(length=1000),
        db.message_templates.count_documents({})
    )

    # Fast aggregate breakdown by EBM
    student_stats = await db.students.aggregate([
        {
            "$group": {
                "_id": "$assigned_ebm_id",
                "total_assigned": {"$sum": 1},
                "contacted": {"$sum": {"$cond": [{"$eq": ["$is_contacted", 1]}, 1, 0]}}
            }
        }
    ]).to_list(1000)
    stats_map = {str(item["_id"]): item for item in student_stats if item["_id"]}

    used_inv_docs = await db.invites.find({"is_used": 1}, {"token": 1}).to_list(100000)
    used_tokens = [inv["token"] for inv in used_inv_docs if inv.get("token")]
    joined_map = {}
    if used_tokens:
        joined_agg = await db.students.aggregate([
            {"$match": {"token": {"$in": used_tokens}}},
            {"$group": {"_id": "$assigned_ebm_id", "joined_count": {"$sum": 1}}}
        ]).to_list(1000)
        joined_map = {str(item["_id"]): item["joined_count"] for item in joined_agg if item["_id"]}

    ebm_breakdown = []
    for doc in ebm_docs:
        ebm_id_str = str(doc["_id"])
        item_stat = stats_map.get(ebm_id_str, {})
        total_assigned = item_stat.get("total_assigned", 0)
        contacted = item_stat.get("contacted", 0)
        joined = joined_map.get(ebm_id_str, 0)
        pending = total_assigned - contacted
        progress = round((contacted / total_assigned * 100) if total_assigned > 0 else 0, 1)

        ebm_breakdown.append({
            "ebm_id": ebm_id_str,
            "id": ebm_id_str,
            "ebm_name": doc.get("name", "EBM Member"),
            "name": doc.get("name", "EBM Member"),
            "username": doc.get("username", doc.get("name")),
            "weight": doc.get("weight", 4),
            "total_assigned": total_assigned,
            "assigned_count": total_assigned,
            "contacted": contacted,
            "contacted_count": contacted,
            "joined": joined,
            "joined_count": joined,
            "pending": pending,
            "progress_percent": progress
        })

    return {
        "stats": {
            "total_students": total_students,
            "contacted_students": contacted_students,
            "pending_students": total_students - contacted_students,
            "total_invites": total_invites,
            "used_invites": used_invites,
            "pending_invites": total_invites - used_invites,
            "unassigned_students": unassigned_students,
            "total_ebms": len(ebm_docs),
            "total_templates": templates_count
        },
        "ebm_breakdown": ebm_breakdown,
        "config": cfg
    }

# ----------------- STUDENT CRUD ENDPOINTS -----------------

@admin_router.get("/api/admin/students")
async def api_admin_get_students(
    request: Request,
    page: int = 1,
    limit: int = 25,
    per_page: int = 25,
    search: str = "",
    ebm_id: str = "",
    filter_ebm: str = "",
    contacted: str = "",
    filter_contacted: str = "",
    joined: str = "",
    filter_joined: str = "",
    year: str = "",
    filter_year: str = "",
    goodies: str = "",
    filter_goodies: str = "",
    branch: str = "",
    filter_branch: str = "",
    gender: str = "",
    filter_gender: str = ""
):
    require_admin(request)
    db = get_async_db()
    cfg = await async_load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

    # Resolve parameter aliases
    page_size = limit if limit != 25 else per_page
    active_ebm = ebm_id if ebm_id != "" else filter_ebm
    active_contacted = contacted if contacted != "" else filter_contacted
    active_joined = joined if joined != "" else filter_joined
    active_year = year if year != "" else filter_year
    active_goodies = goodies if goodies != "" else filter_goodies
    active_branch = branch if branch != "" else filter_branch
    active_gender = gender if gender != "" else filter_gender

    conditions = []

    if search.strip():
        term = re.escape(search.strip())
        conditions.append({
            "$or": [
                {"name": {"$regex": term, "$options": "i"}},
                {"phone": {"$regex": term, "$options": "i"}},
                {"acm_id": {"$regex": term, "$options": "i"}},
                {"branch": {"$regex": term, "$options": "i"}},
                {"email": {"$regex": term, "$options": "i"}}
            ]
        })

    if active_ebm == "unassigned":
        conditions.append({"$or": [{"assigned_ebm_id": None}, {"assigned_ebm_id": ""}]})
    elif active_ebm:
        conditions.append({"assigned_ebm_id": active_ebm})

    if active_contacted == "1":
        conditions.append({"is_contacted": 1})
    elif active_contacted == "0":
        conditions.append({"$or": [{"is_contacted": 0}, {"is_contacted": None}]})

    if active_year:
        conditions.append({"year": {"$regex": f"^{re.escape(active_year)}", "$options": "i"}})

    if active_goodies:
        if active_goodies.lower() == "yes":
            conditions.append({"goodies": {"$regex": "^yes", "$options": "i"}})
        elif active_goodies.lower() == "no":
            conditions.append({"goodies": {"$regex": "^no", "$options": "i"}})

    if active_branch:
        conditions.append({"branch": {"$regex": f"^{re.escape(active_branch)}$", "$options": "i"}})

    if active_gender:
        conditions.append({
            "$or": [
                {"gender": {"$regex": f"^{re.escape(active_gender)}$", "$options": "i"}},
                {"extra_data.gender": {"$regex": f"^{re.escape(active_gender)}$", "$options": "i"}},
                {"extra_data.Gender": {"$regex": f"^{re.escape(active_gender)}$", "$options": "i"}}
            ]
        })

    if active_joined:
        used_inv_docs = await db.invites.find({"is_used": 1}, {"token": 1}).to_list(100000)
        used_tokens = [inv["token"] for inv in used_inv_docs if inv.get("token")]
        if active_joined == "1":
            conditions.append({"token": {"$in": used_tokens}})
        elif active_joined == "0":
            conditions.append({"token": {"$nin": used_tokens}})

    query = {"$and": conditions} if conditions else {}

    # Fetch total matching count
    total_count = await db.students.count_documents(query)

    # Fetch paginated slice
    skip = (page - 1) * page_size
    cursor = db.students.find(query).sort([("_id", -1)]).skip(skip).limit(page_size)
    student_docs = await cursor.to_list(length=page_size)

    # Pre-fetch EBM names map
    ebm_map = {}
    async for e in db.ebms.find({}, {"_id": 1, "name": 1, "username": 1}):
        ebm_map[str(e["_id"])] = e.get("name")

    # Pre-fetch invites for joined status
    tokens = [s.get("token") for s in student_docs if s.get("token")]
    inv_map = {}
    if tokens:
        async for inv in db.invites.find({"token": {"$in": tokens}}):
            inv_map[inv["token"]] = inv

    students = []
    for s in student_docs:
        s_id = str(s["_id"])
        tok = s.get("token")
        inv = inv_map.get(tok, {}) if tok else {}
        is_used = bool(inv.get("is_used", 0))

        assigned_id = s.get("assigned_ebm_id") or ""
        ebm_name = ebm_map.get(assigned_id, "Unassigned") if assigned_id else "Unassigned"
        link = f"{base_url}/join/{tok}" if tok else ""

        students.append({
            "id": s_id,
            "_id": s_id,
            "name": s.get("name", ""),
            "phone": s.get("phone", ""),
            "email": s.get("email") or s.get("extra_data", {}).get("email", ""),
            "acm_id": s.get("acm_id", ""),
            "branch": s.get("branch", ""),
            "year": s.get("year", "1"),
            "goodies": s.get("goodies", "Yes"),
            "gender": s.get("gender") or s.get("extra_data", {}).get("gender") or s.get("extra_data", {}).get("Gender", ""),
            "section": s.get("section") or s.get("extra_data", {}).get("Section", "") or s.get("extra_data", {}).get("section", ""),
            "domain": s.get("domain") or s.get("extra_data", {}).get("Domain", "") or s.get("extra_data", {}).get("domain", ""),
            "extra_data": s.get("extra_data", {}),
            "ebm_id": assigned_id,
            "assigned_ebm_id": assigned_id,
            "ebm_name": ebm_name,
            "assigned_ebm_name": ebm_name,
            "token": tok or "",
            "invite_link": link,
            "full_invite_link": link,
            "is_contacted": 1 if s.get("is_contacted") else 0,
            "contacted_at": s.get("contacted_at", ""),
            "is_used": 1 if is_used else 0,
            "used_at": inv.get("used_at", ""),
            "created_at": s.get("created_at", "")
        })

    total_pages = max(1, (total_count + page_size - 1) // page_size)
    return {
        "students": students,
        "total": total_count,
        "page": page,
        "limit": page_size,
        "per_page": page_size,
        "total_pages": total_pages
    }

@admin_router.put("/api/admin/students/{student_id}")
async def api_admin_update_student(request: Request, student_id: str):
    require_admin(request)
    data = await request.json()
    db = get_async_db()
    oid = safe_object_id(student_id)

    student = await db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    update_fields = {}
    if "name" in data:
        update_fields["name"] = data["name"].strip()
    if "phone" in data:
        update_fields["phone"] = clean_phone_number(data["phone"])
    if "acm_id" in data:
        update_fields["acm_id"] = data["acm_id"].strip()
    if "branch" in data:
        update_fields["branch"] = data["branch"].strip()
    if "year" in data:
        update_fields["year"] = str(data["year"]).strip()
    if "goodies" in data:
        update_fields["goodies"] = str(data["goodies"]).strip()
    if "section" in data:
        update_fields["section"] = str(data["section"]).strip()
    if "domain" in data:
        update_fields["domain"] = str(data["domain"]).strip()
    if "assigned_ebm_id" in data:
        update_fields["assigned_ebm_id"] = data["assigned_ebm_id"] or ""
    if "extra_data" in data and isinstance(data["extra_data"], dict):
        update_fields["extra_data"] = data["extra_data"]

    if update_fields:
        await db.students.update_one({"_id": student["_id"]}, {"$set": update_fields})

    updated = await db.students.find_one({"_id": student["_id"]})
    updated["id"] = str(updated["_id"])
    updated.pop("_id", None)
    return {"success": True, "message": "Student updated successfully", "student": updated}

@admin_router.patch("/api/admin/students/{student_id}/status")
async def api_admin_update_student_status(request: Request, student_id: str):
    require_admin(request)
    data = await request.json()
    db = get_async_db()
    oid = safe_object_id(student_id)

    student = await db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_fields = {}

    if "is_contacted" in data:
        val = int(bool(data["is_contacted"]))
        update_fields["is_contacted"] = val
        update_fields["contacted_at"] = now_str if val == 1 else None
    elif "status" in data:
        status_str = str(data["status"]).lower()
        if "contacted" in status_str and "not" not in status_str:
            update_fields["is_contacted"] = 1
            update_fields["contacted_at"] = now_str
        else:
            update_fields["is_contacted"] = 0
            update_fields["contacted_at"] = None

    if "assigned_ebm_id" in data:
        update_fields["assigned_ebm_id"] = data["assigned_ebm_id"] or ""

    if update_fields:
        await db.students.update_one({"_id": student["_id"]}, {"$set": update_fields})

    return {
        "success": True,
        "message": "Student status updated",
        "is_contacted": update_fields.get("is_contacted", student.get("is_contacted", 0)),
        "contacted_at": update_fields.get("contacted_at", student.get("contacted_at"))
    }

@admin_router.delete("/api/admin/students/{student_id}")
async def api_admin_delete_student(request: Request, student_id: str):
    require_admin(request)
    db = get_async_db()
    oid = safe_object_id(student_id)

    student = await db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Delete or unbind invite token
    tok = student.get("token")
    if tok:
        await db.invites.delete_one({"token": tok})

    await db.students.delete_one({"_id": student["_id"]})
    return {"success": True, "message": "Student deleted successfully"}

@admin_router.post("/api/admin/students/clear-all")
@admin_router.delete("/api/admin/students/clear-all")
async def api_admin_clear_all_students(request: Request):
    require_admin(request)
    db = get_async_db()
    res_students = await db.students.delete_many({})
    res_invites = await db.invites.delete_many({})
    return {
        "success": True,
        "message": f"Cleared {res_students.deleted_count} students and {res_invites.deleted_count} tokens successfully."
    }

# ----------------- HIGH-PERFORMANCE BATCH SPLITTING -----------------
@admin_router.post("/api/admin/batch/split")
async def api_batch_split(request: Request):
    require_admin(request)
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    reassign_all = bool(data.get("reassign_all", False))

    db = get_async_db()
    # Concurrently fetch EBMs and students for maximum speed
    query = {} if reassign_all else {"$or": [{"assigned_ebm_id": None}, {"assigned_ebm_id": ""}]}
    ebms, students = await asyncio.gather(
        db.ebms.find({}, {"_id": 1, "name": 1, "weight": 1}).sort("name", 1).to_list(length=1000),
        db.students.find(query, {"_id": 1}).to_list(length=100000)
    )

    if not ebms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No EBM members available for allocation. Please register or upload EBMs first."
        )

    if not students:
        return {
            "success": True,
            "message": "No unassigned students to distribute." if not reassign_all else "No students found.",
            "distributed_count": 0
        }

    # Interleaved weighted round-robin
    ebm_pool = []
    for e in ebms:
        w = max(1, int(e.get("weight", 4)))
        ebm_pool.extend([str(e["_id"])] * w)

    pool_size = len(ebm_pool)
    bulk_ops = []
    for idx, s in enumerate(students):
        assigned_id = ebm_pool[idx % pool_size]
        bulk_ops.append(
            UpdateOne({"_id": s["_id"]}, {"$set": {"assigned_ebm_id": assigned_id}})
        )

    # Atomic, non-blocking bulk write with ordered=False
    if bulk_ops:
        await db.students.bulk_write(bulk_ops, ordered=False)

    return {
        "success": True,
        "message": f"Successfully distributed all {len(students)} students across {len(ebms)} EBM members based on weights.",
        "distributed_count": len(students)
    }

# ----------------- BATCH REASSIGN & TRANSFER -----------------
@admin_router.post("/api/admin/batch/reassign")
async def api_batch_reassign(request: Request):
    require_admin(request)
    data = await request.json()
    student_ids = data.get("student_ids", [])
    target_ebm_id = data.get("ebm_id", "")

    if not student_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No students selected")

    db = get_async_db()
    obj_ids = [safe_object_id(sid) for sid in student_ids]

    await db.students.update_many(
        {"_id": {"$in": obj_ids}},
        {"$set": {"assigned_ebm_id": target_ebm_id or ""}}
    )

    return {"success": True, "count": len(student_ids)}

@admin_router.post("/api/admin/batch/transfer")
async def api_batch_transfer(request: Request):
    require_admin(request)
    data = await request.json()
    from_ebm_id = data.get("from_ebm_id")
    to_ebm_id = data.get("to_ebm_id")
    mode = data.get("mode", "quick")
    count = int(data.get("count", 1))
    selected_ids = data.get("student_ids", [])

    if from_ebm_id == to_ebm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source and destination cannot be identical")

    db = get_async_db()
    source_query = {"$or": [{"assigned_ebm_id": None}, {"assigned_ebm_id": ""}]} if from_ebm_id == "unassigned" else {"assigned_ebm_id": from_ebm_id}
    dest_val = "" if to_ebm_id == "unassigned" else to_ebm_id

    if mode == "specific" and selected_ids:
        obj_ids = [safe_object_id(sid) for sid in selected_ids]
        res = await db.students.update_many(
            {"_id": {"$in": obj_ids}},
            {"$set": {"assigned_ebm_id": dest_val}}
        )
        transferred_count = res.modified_count
    else:
        # Quick transfer N uncontacted students first
        source_cursor = db.students.find(source_query, {"_id": 1}).sort([("is_contacted", 1), ("_id", 1)]).limit(count)
        candidates = await source_cursor.to_list(length=count)
        cand_ids = [c["_id"] for c in candidates]

        if cand_ids:
            res = await db.students.update_many(
                {"_id": {"$in": cand_ids}},
                {"$set": {"assigned_ebm_id": dest_val}}
            )
            transferred_count = res.modified_count
        else:
            transferred_count = 0

    return {
        "success": True,
        "message": f"Successfully transferred {transferred_count} student(s)",
        "transferred_count": transferred_count
    }

@admin_router.post("/api/admin/students/{student_id}/assign")
async def api_assign_single_student(request: Request, student_id: str):
    require_admin(request)
    data = await request.json()
    ebm_id = data.get("ebm_id", "")
    db = get_async_db()
    oid = safe_object_id(student_id)

    await db.students.update_one(
        {"_id": oid},
        {"$set": {"assigned_ebm_id": ebm_id or ""}}
    )

    ebm_name = "Unassigned"
    if ebm_id:
        ebm_doc = await db.ebms.find_one({"$or": [{"_id": safe_object_id(ebm_id)}, {"id": ebm_id}]})
        if ebm_doc:
            ebm_name = ebm_doc.get("name", "EBM Member")

    return {
        "success": True,
        "student_id": student_id,
        "ebm_id": ebm_id,
        "assigned_ebm_id": ebm_id,
        "ebm_name": ebm_name,
        "assigned_ebm_name": ebm_name
    }

# ----------------- CSV UPLOAD & SYNC -----------------
@admin_router.post("/api/admin/upload/students")
async def api_upload_students_csv(request: Request, file: UploadFile = File(...)):
    require_admin(request)
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse CSV: {str(e)}")

    col_map = {}
    for col in df.columns:
        c_low = col.strip().lower()
        if "name" in c_low and "user" not in c_low and "father" not in c_low:
            col_map["name"] = col
        elif "phone" in c_low or "mobile" in c_low or "whatsapp" in c_low:
            col_map["phone"] = col
        elif "id" in c_low or "acm" in c_low or "roll" in c_low:
            col_map["acm_id"] = col
        elif "branch" in c_low or "dept" in c_low:
            col_map["branch"] = col
        elif "year" in c_low:
            col_map["year"] = col
        elif "goodies" in c_low or "kit" in c_low or "tshirt" in c_low:
            col_map["goodies"] = col

    db = get_async_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    student_docs = []
    invite_docs = []

    for _, row in df.iterrows():
        name_val = str(row[col_map["name"]]).strip() if "name" in col_map and pd.notna(row[col_map["name"]]) else "Fresher"
        phone_val = clean_phone_number(row[col_map["phone"]]) if "phone" in col_map and pd.notna(row[col_map["phone"]]) else ""
        acm_id_val = str(row[col_map["acm_id"]]).strip() if "acm_id" in col_map and pd.notna(row[col_map["acm_id"]]) else ""
        branch_val = str(row[col_map["branch"]]).strip() if "branch" in col_map and pd.notna(row[col_map["branch"]]) else ""
        year_val = str(row[col_map["year"]]).strip() if "year" in col_map and pd.notna(row[col_map["year"]]) else "1"
        goodies_val = str(row[col_map["goodies"]]).strip() if "goodies" in col_map and pd.notna(row[col_map["goodies"]]) else "Yes"

        tok = secrets.token_urlsafe(12)
        student_docs.append({
            "name": name_val,
            "phone": phone_val,
            "acm_id": acm_id_val,
            "branch": branch_val,
            "year": year_val,
            "goodies": goodies_val,
            "token": tok,
            "assigned_ebm_id": "",
            "is_contacted": 0,
            "created_at": now_str
        })
        invite_docs.append({
            "token": tok,
            "is_used": 0,
            "created_at": now_str
        })

    if student_docs:
        await db.students.insert_many(student_docs)
        await db.invites.insert_many(invite_docs)

    return {
        "success": True,
        "message": f"Successfully imported {len(student_docs)} students."
    }

@admin_router.post("/api/admin/upload/ebm")
async def api_upload_ebm_csv(request: Request, file: UploadFile = File(...)):
    require_admin(request)
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse CSV: {str(e)}")

    name_col = None
    pass_col = None
    phone_col = None
    branch_col = None
    domain_col = None
    weight_col = None

    for col in df.columns:
        c_low = col.strip().lower()
        if "full name" in c_low or (c_low == "name"):
            name_col = col
        elif "password" in c_low:
            pass_col = col
        elif "phone" in c_low or "whatsapp" in c_low:
            phone_col = col
        elif "branch" in c_low:
            branch_col = col
        elif "domain" in c_low:
            domain_col = domain_col or col
        elif "weight" in c_low:
            weight_col = col

    db = get_async_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ebm_ops = []
    imported_count = 0

    for _, row in df.iterrows():
        raw_name = row[name_col] if name_col and pd.notna(row[name_col]) else None
        if not raw_name or not str(raw_name).strip():
            continue

        clean_name = str(raw_name).strip()
        raw_pass = row[pass_col] if pass_col and pd.notna(row[pass_col]) else None
        pw_str = str(raw_pass).strip() if raw_pass else f"ebm_{secrets.token_hex(3)}"
        hashed_pw = generate_password_hash(pw_str)

        clean_user = re.sub(r"[^a-zA-Z0-9_]", "", clean_name.lower().replace(" ", "_"))

        w = 4
        if weight_col and pd.notna(row[weight_col]):
            try:
                w = min(20, max(1, int(row[weight_col])))
            except Exception:
                pass

        doc = {
            "name": clean_name,
            "username": clean_user,
            "password": hashed_pw,
            "role": "ebm",
            "weight": w,
            "created_at": now_str
        }

        ebm_ops.append(
            UpdateOne(
                {"name": {"$regex": f"^{re.escape(clean_name)}$", "$options": "i"}},
                {"$set": doc},
                upsert=True
            )
        )
        imported_count += 1

    if ebm_ops:
        await db.ebms.bulk_write(ebm_ops)

    return {
        "success": True,
        "message": f"Successfully processed {imported_count} EBM accounts from Google Sheet CSV."
    }

@admin_router.post("/api/admin/sync/registrations")
async def api_admin_sync_registrations(request: Request):
    require_admin(request)
    data = await request.json()
    year_filter = data.get("year", "all")
    goodies_filter = data.get("goodies", "all")
    mode = data.get("mode", "sync")

    db = get_async_db()
    query = {}
    if year_filter != "all":
        query["year"] = {"$regex": f"^{re.escape(year_filter)}", "$options": "i"}
    if goodies_filter != "all":
        if goodies_filter.lower() == "yes":
            query["goodies"] = {"$regex": "^yes", "$options": "i"}
        elif goodies_filter.lower() == "no":
            query["goodies"] = {"$regex": "^no", "$options": "i"}

    regs_cursor = db.registrations.find(query)
    regs = await regs_cursor.to_list(length=50000)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if mode == "overwrite":
        await db.students.delete_many({})
        await db.invites.delete_many({})

    student_ops = []
    invite_ops = []
    synced_count = 0

    for r in regs:
        acm_id = r.get("acm_id") or ""
        phone = clean_phone_number(r.get("phone"))
        name = r.get("name") or "Student"
        branch = r.get("branch") or ""
        year = r.get("year") or "1"
        goodies = r.get("goodies") or "Yes"

        tok = secrets.token_urlsafe(12)
        match_query = {"acm_id": acm_id} if acm_id else {"phone": phone}

        student_ops.append(
            UpdateOne(
                match_query,
                {"$setOnInsert": {
                    "name": name,
                    "phone": phone,
                    "acm_id": acm_id,
                    "branch": branch,
                    "year": year,
                    "goodies": goodies,
                    "token": tok,
                    "assigned_ebm_id": "",
                    "is_contacted": 0,
                    "created_at": now_str
                }},
                upsert=True
            )
        )
        invite_ops.append(
            UpdateOne(
                {"token": tok},
                {"$setOnInsert": {"token": tok, "is_used": 0, "created_at": now_str}},
                upsert=True
            )
        )
        synced_count += 1

    if student_ops:
        await db.students.bulk_write(student_ops, ordered=False)
        await db.invites.bulk_write(invite_ops, ordered=False)

    return {
        "success": True,
        "message": f"Synced {synced_count} records successfully.",
        "count": synced_count
    }

@admin_router.get("/api/admin/filter-options")
async def api_admin_filter_options(request: Request):
    require_admin(request)
    db = get_async_db()
    student_branches = [b for b in await db.students.distinct("branch") if b]
    reg_branches = [b for b in await db.registrations.distinct("branch") if b]
    all_branches = sorted(list(set(student_branches + reg_branches)))

    return {
        "branches": all_branches,
        "years": ["1st Year", "2nd Year", "3rd Year", "4th Year"],
        "goodies": ["Yes", "No"],
        "genders": ["Male", "Female"]
    }

# ----------------- EBM TEAM CRUD -----------------
@admin_router.get("/api/admin/ebm/list")
async def api_admin_ebm_list(request: Request):
    require_admin(request)
    db = get_async_db()
    ebm_docs = await db.ebms.find({}).sort([("weight", -1), ("name", 1)]).to_list(length=1000)

    # Fast aggregate assigned and contacted counts
    student_stats = await db.students.aggregate([
        {
            "$group": {
                "_id": "$assigned_ebm_id",
                "assigned_count": {"$sum": 1},
                "contacted_count": {"$sum": {"$cond": [{"$eq": ["$is_contacted", 1]}, 1, 0]}}
            }
        }
    ]).to_list(1000)
    stats_map = {str(item["_id"]): item for item in student_stats if item["_id"]}

    # Fast aggregate joined counts via redeemed tokens
    used_inv_docs = await db.invites.find({"is_used": 1}, {"token": 1}).to_list(100000)
    used_tokens = [inv["token"] for inv in used_inv_docs if inv.get("token")]
    joined_map = {}
    if used_tokens:
        joined_agg = await db.students.aggregate([
            {"$match": {"token": {"$in": used_tokens}}},
            {"$group": {"_id": "$assigned_ebm_id", "joined_count": {"$sum": 1}}}
        ]).to_list(1000)
        joined_map = {str(item["_id"]): item["joined_count"] for item in joined_agg if item["_id"]}

    ebms = []
    for doc in ebm_docs:
        e_id_str = str(doc["_id"])
        stat = stats_map.get(e_id_str, {})
        assigned = stat.get("assigned_count", 0)
        contacted = stat.get("contacted_count", 0)
        joined = joined_map.get(e_id_str, 0)
        pending = assigned - contacted
        progress = round((contacted / assigned * 100) if assigned > 0 else 0, 1)

        ebms.append({
            "id": e_id_str,
            "_id": e_id_str,
            "name": doc.get("name", "EBM Member"),
            "username": doc.get("username", doc.get("name")),
            "role": doc.get("role", "ebm"),
            "weight": doc.get("weight", 4),
            "phone": doc.get("phone", ""),
            "email": doc.get("email", ""),
            "branch": doc.get("branch", ""),
            "created_at": doc.get("created_at", ""),
            "assigned_count": assigned,
            "contacted_count": contacted,
            "joined_count": joined,
            "total_assigned": assigned,
            "contacted": contacted,
            "pending": pending,
            "progress_percent": progress
        })
    return {"ebms": ebms}

@admin_router.post("/api/admin/ebm", status_code=status.HTTP_201_CREATED)
async def api_admin_create_ebm(request: Request):
    require_admin(request)
    data = await request.json()
    name = (data.get("name") or "").strip()
    password = (data.get("password") or "").strip()
    weight = min(20, max(1, int(data.get("weight", 4))))

    if not name or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name and password required")

    db = get_async_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed_pw = generate_password_hash(password)
    doc = {
        "name": name,
        "username": re.sub(r"[^a-zA-Z0-9_]", "", name.lower().replace(" ", "_")),
        "password": hashed_pw,
        "role": "ebm",
        "weight": weight,
        "created_at": now_str
    }
    res = await db.ebms.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    doc.pop("password", None)
    return {"success": True, "ebm": doc}

@admin_router.put("/api/admin/ebm/{ebm_id}")
async def api_admin_update_ebm(request: Request, ebm_id: str):
    require_admin(request)
    data = await request.json()
    db = get_async_db()
    oid = safe_object_id(ebm_id)

    update = {}
    if "name" in data:
        update["name"] = data["name"].strip()
    if "weight" in data:
        update["weight"] = min(20, max(1, int(data["weight"])))
    if "password" in data and data["password"].strip():
        update["password"] = generate_password_hash(data["password"].strip())

    if update:
        await db.ebms.update_one({"$or": [{"_id": oid}, {"id": ebm_id}]}, {"$set": update})

    return {"success": True}

@admin_router.delete("/api/admin/ebm/{ebm_id}")
async def api_admin_delete_ebm(request: Request, ebm_id: str):
    require_admin(request)
    db = get_async_db()
    oid = safe_object_id(ebm_id)
    await db.ebms.delete_one({"$or": [{"_id": oid}, {"id": ebm_id}]})
    # Reset students assigned to this deleted EBM
    await db.students.update_many({"assigned_ebm_id": ebm_id}, {"$set": {"assigned_ebm_id": ""}})
    return {"success": True}

# ----------------- TOKENS RENEWAL -----------------
@admin_router.post("/api/admin/tokens/renew/{student_id}")
async def api_admin_renew_token(request: Request, student_id: str):
    require_admin(request)
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    action = data.get("action", "reset")

    db = get_async_db()
    oid = safe_object_id(student_id)
    student = await db.students.find_one({"$or": [{"_id": oid}, {"id": student_id}]})
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "generate":
        tok = secrets.token_urlsafe(12)
        await db.students.update_one({"_id": student["_id"]}, {"$set": {"token": tok}})
        await db.invites.insert_one({"token": tok, "is_used": 0, "created_at": now_str})
    else:
        # Reset existing token
        tok = student.get("token")
        if tok:
            await db.invites.update_one(
                {"token": tok},
                {"$set": {"is_used": 0, "used_at": None, "device_id": None, "ip_address": None}}
            )

    return {"success": True, "message": f"Token successfully {action}ed."}

# ----------------- MESSAGE TEMPLATES -----------------
@admin_router.get("/api/templates")
async def api_get_templates(request: Request):
    require_admin(request)
    db = get_async_db()
    cursor = db.message_templates.find({}).sort([("is_default", -1), ("title", 1)])
    templates = []
    async for doc in cursor:
        templates.append({
            "id": str(doc["_id"]),
            "title": doc.get("title", ""),
            "content": doc.get("content", ""),
            "is_default": bool(doc.get("is_default", 0))
        })
    return {"templates": templates}

@admin_router.post("/api/templates", status_code=status.HTTP_201_CREATED)
async def api_create_template(request: Request):
    require_admin(request)
    data = await request.json()
    title = (data.get("title") or "New Template").strip()
    content = (data.get("content") or "").strip()
    is_default = 1 if data.get("is_default") else 0

    db = get_async_db()
    if is_default:
        await db.message_templates.update_many({}, {"$set": {"is_default": 0}})

    res = await db.message_templates.insert_one({
        "title": title,
        "content": content,
        "is_default": is_default,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    return {"success": True, "id": str(res.inserted_id)}

@admin_router.put("/api/templates/{template_id}")
async def api_update_template(request: Request, template_id: str):
    require_admin(request)
    data = await request.json()
    db = get_async_db()
    oid = safe_object_id(template_id)

    update = {}
    if "title" in data:
        update["title"] = data["title"].strip()
    if "content" in data:
        update["content"] = data["content"].strip()
    if "is_default" in data:
        is_def = 1 if data["is_default"] else 0
        update["is_default"] = is_def
        if is_def:
            await db.message_templates.update_many({}, {"$set": {"is_default": 0}})

    if update:
        await db.message_templates.update_one({"$or": [{"_id": oid}, {"id": template_id}]}, {"$set": update})

    return {"success": True}

@admin_router.post("/api/templates/{template_id}/set-default")
async def api_set_default_template(request: Request, template_id: str):
    require_admin(request)
    db = get_async_db()
    oid = safe_object_id(template_id)
    await db.message_templates.update_many({}, {"$set": {"is_default": 0}})
    await db.message_templates.update_one({"$or": [{"_id": oid}, {"id": template_id}]}, {"$set": {"is_default": 1}})
    return {"success": True}

@admin_router.delete("/api/templates/{template_id}")
async def api_delete_template(request: Request, template_id: str):
    require_admin(request)
    db = get_async_db()
    oid = safe_object_id(template_id)
    await db.message_templates.delete_one({"$or": [{"_id": oid}, {"id": template_id}]})
    return {"success": True}

# ----------------- CONFIG & SETTINGS -----------------
@admin_router.get("/api/admin/config")
async def api_get_config(request: Request):
    require_admin(request)
    cfg = await async_load_config()
    return {
        "whatsapp_group_link": cfg.get("whatsapp_group_link", ""),
        "base_url": cfg.get("base_url", ""),
        "admin_password": "••••••••" if cfg.get("admin_password") else ""
    }

@admin_router.post("/api/admin/config")
async def api_save_config(request: Request):
    require_admin(request)
    data = await request.json()
    cfg = await async_load_config()

    if "whatsapp_group_link" in data:
        cfg["whatsapp_group_link"] = data["whatsapp_group_link"].strip()
    if "base_url" in data:
        cfg["base_url"] = data["base_url"].strip().rstrip("/")
    if "admin_password" in data and data["admin_password"].strip() and data["admin_password"] != "••••••••":
        cfg["admin_password"] = data["admin_password"].strip()

    await async_save_config(cfg)
    return {"success": True, "message": "Settings saved successfully"}

# ----------------- EXPORT LINKS -----------------
@admin_router.get("/api/admin/export/links")
async def api_admin_export_links(request: Request):
    require_admin(request)
    db = get_async_db()
    cfg = await async_load_config()
    base_url = cfg.get("base_url", "http://localhost:5000").rstrip("/")

    cursor = db.students.find({}).sort("name", 1)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ACM_ID", "Name", "Phone", "Branch", "Year", "Invite_Link", "Contacted", "Joined"])

    async for s in cursor:
        tok = s.get("token") or ""
        link = f"{base_url}/join/{tok}" if tok else ""
        writer.writerow([
            s.get("acm_id", ""),
            s.get("name", ""),
            s.get("phone", ""),
            s.get("branch", ""),
            s.get("year", "1"),
            link,
            "Yes" if s.get("is_contacted") else "No",
            "Yes" if s.get("is_used") else "No"
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=acm_whatsapp_links.csv"}
    )
