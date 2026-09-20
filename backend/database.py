from datetime import datetime
from backend.config import get_db

def init_db():
    try:
        db = get_db()
        # 1. Base invites collection indexes
        db.invites.create_index("token", unique=True)
        db.invites.create_index("student_id")

        # 2. Settings collection indexes
        db.settings.create_index("key", unique=True)

        # 3. EBM Members collection indexes
        db.ebms.create_index("name", unique=True)
        db.ebms.create_index("username", sparse=True)

        # 4. Students collection indexes
        db.students.create_index("token", unique=True, sparse=True)
        db.students.create_index("acm_id", sparse=True)
        db.students.create_index("phone", sparse=True)
        db.students.create_index("assigned_ebm_id")
        db.students.create_index("year")
        db.students.create_index("goodies")

        # 5. Seed default message template if none exists
        if db.message_templates.count_documents({}) == 0:
            default_template = (
                "Hello {name}, welcome to the ACM Student Chapter!\n\n"
                "Here is your exclusive, one-time invitation link to join our official WhatsApp group:\n"
                "{link}\n\n"
                "⚠️ Note: This link is single-use and bound to your device for security. "
                "Do not forward it.\n\nBest regards,\nACM Executive Team"
            )
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.message_templates.insert_one({
                "title": "Official WhatsApp Group Invitation",
                "content": default_template,
                "is_default": 1,
                "created_at": now_str,
                "updated_at": now_str
            })
    except Exception as e:
        print("Note on MongoDB index initialization:", e)

if __name__ == "__main__":
    init_db()
    print("MongoDB Atlas collections and indexes initialized successfully.")
