import sqlite3
from datetime import datetime
from backend.config import get_db

def init_db():
    with get_db() as conn:
        # 1. Base invites table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                assigned_to TEXT,
                student_id INTEGER,
                is_used INTEGER DEFAULT 0,
                used_at TEXT,
                ip_address TEXT,
                created_at TEXT,
                device_id TEXT
            )
        """)
        try:
            conn.execute("ALTER TABLE invites ADD COLUMN device_id TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE invites ADD COLUMN student_id INTEGER")
        except Exception:
            pass

        # 2. Settings table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 3. EBM Members table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ebm_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'ebm',
                weight INTEGER DEFAULT 4,
                created_at TEXT
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ebm_username ON ebm_members(username)")

        # 4. Students table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                acm_id TEXT,
                branch TEXT,
                extra_data TEXT,
                assigned_ebm_id INTEGER REFERENCES ebm_members(id),
                token TEXT UNIQUE,
                is_contacted INTEGER DEFAULT 0,
                contacted_at TEXT,
                created_at TEXT
            )
        """)

        # 5. Message Templates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()

        # Seed default message template if none exists
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM message_templates")
        if cursor.fetchone()[0] == 0:
            default_template = (
                "Hello {name}, welcome to the ACM Student Chapter!\n\n"
                "Here is your exclusive, one-time invitation link to join our official WhatsApp group:\n"
                "{link}\n\n"
                "⚠️ Note: This link is single-use and bound to your device for security. "
                "Do not forward it.\n\nBest regards,\nACM Executive Team"
            )
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO message_templates (title, content, is_default, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
            """, ("Official WhatsApp Group Invitation", default_template, now_str, now_str))
            conn.commit()

        # Repair any legacy semicolon-glommed EBM entries
        repair_ebm_records(conn)

def repair_ebm_records(conn):
    """Repairs EBM records where semicolons merged name, username, password, weight into name"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, username, password, weight FROM ebm_members")
        rows = cursor.fetchall()
        for r in rows:
            raw_name = r["name"] if isinstance(r, sqlite3.Row) else r[1]
            row_id = r["id"] if isinstance(r, sqlite3.Row) else r[0]
            if ";" in raw_name:
                parts = [p.strip() for p in raw_name.split(";")]
                name = parts[0]
                user = parts[1] if len(parts) > 1 and parts[1] else (r["username"] if isinstance(r, sqlite3.Row) else r[2])
                pwd = parts[2] if len(parts) > 2 and parts[2] else (r["password"] if isinstance(r, sqlite3.Row) else r[3])
                try:
                    wt = int(parts[3]) if len(parts) > 3 else (r["weight"] if isinstance(r, sqlite3.Row) else r[4])
                except Exception:
                    wt = 4
                wt = min(20, max(1, wt))
                cursor.execute("""
                    UPDATE ebm_members
                    SET name = ?, username = ?, password = ?, weight = ?
                    WHERE id = ?
                """, (name, user, pwd, wt, row_id))
        conn.commit()
    except Exception as e:
        print(f"EBM record cleanup note: {e}")

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
