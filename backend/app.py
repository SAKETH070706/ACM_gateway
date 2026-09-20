import os
import secrets
from flask import Flask, render_template, send_from_directory, redirect, session, request, jsonify
from flask_cors import CORS
from backend.config import TEMPLATES_DIR, FRONTEND_DIST, load_config, save_config, get_db
from backend.database import init_db
from backend.routes.gateway import gateway_bp
from backend.routes.auth import auth_bp
from backend.routes.admin import admin_bp
from backend.routes.ebm import ebm_bp

# ----------------- PRODUCTION ENVIRONMENT CHECK -----------------
is_prod = bool(
    os.environ.get("RENDER") or
    os.environ.get("VERCEL") or
    os.environ.get("FLASK_ENV") == "production" or
    os.environ.get("ENVIRONMENT") == "production"
)

if is_prod:
    missing_vars = []
    if not os.environ.get("MONGO_URI"):
        missing_vars.append("MONGO_URI")
    if not os.environ.get("ADMIN_PASSWORD"):
        missing_vars.append("ADMIN_PASSWORD")
    if not os.environ.get("FLASK_SECRET_KEY"):
        missing_vars.append("FLASK_SECRET_KEY")
    if missing_vars:
        raise RuntimeError(
            f"FATAL: Missing mandatory production environment variables: {', '.join(missing_vars)}. "
            "Application boot halted for security."
        )

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=None)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(24)

# ----------------- CORS & CREDENTIAL CONFIGURATION -----------------
# Default development origins and safe Vercel pattern matching
default_origins = [
    r"^https?://localhost(:\d+)?$",
    r"^https?://127\.0\.0\.1(:\d+)?$",
    r"^https?://([a-zA-Z0-9-]+\.)*vercel\.app$",  # Automatically matches any Vercel deployment URL
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Read optional environment overrides for Vercel/Render decoupled deployment
env_origins = []
for env_var in ["FRONTEND_URL", "CORS_ORIGINS", "VERCEL_URL"]:
    val = os.environ.get(env_var)
    if val:
        for item in val.split(","):
            cleaned = item.strip().rstrip("/")
            if cleaned:
                if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
                    cleaned = f"https://{cleaned}"
                if cleaned not in env_origins:
                    env_origins.append(cleaned)

allowed_origins = list(dict.fromkeys(default_origins + env_origins))

# Configure CORS with credentials support for /api/* endpoints
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": allowed_origins,
            "supports_credentials": True,
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "expose_headers": ["Content-Type", "Set-Cookie"]
        }
    }
)

# Cross-Site Cookie Configuration for Decoupled Production (Vercel <-> Render)
same_site_env = os.environ.get("SESSION_COOKIE_SAMESITE")
if same_site_env:
    app.config["SESSION_COOKIE_SAMESITE"] = same_site_env
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
elif is_prod:
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = True
else:
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = False

app.config["SESSION_COOKIE_HTTPONLY"] = True

# ----------------- CSRF & STATE-CHANGING SECURITY GUARD -----------------
@app.before_request
def csrf_guard():
    # Enforce custom header on all state-changing API requests to prevent CSRF
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        if request.method == "OPTIONS":
            return None
        if request.path.startswith("/api/"):
            x_req = request.headers.get("X-Requested-With")
            if not x_req or x_req.lower() != "xmlhttprequest":
                return jsonify({"error": "CSRF verification failed: missing or invalid X-Requested-With header"}), 403

# Initialize database schema and tables
init_db()

# Register Blueprints
app.register_blueprint(gateway_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ebm_bp)

# ----------------- ROUTING & ERROR HANDLING -----------------
@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found", "path": request.path}), 404
    if os.path.exists(FRONTEND_DIST):
        index_file = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_file):
            return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("invalid.html"), 404

# Root route
@app.route("/")
def index():
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("index.html")

# React SPA Client-side Route Catch-All
@app.route("/<path:path>")
def serve_spa(path):
    if path.startswith("api/"):
        return jsonify({"error": "API endpoint not found", "path": f"/{path}"}), 404
    if os.path.exists(FRONTEND_DIST):
        file_path = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(file_path):
            return send_from_directory(FRONTEND_DIST, path)
        if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
            return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("invalid.html"), 404

if __name__ == "__main__":
    print("\n=======================================================")
    print(" WhatsApp One-Time Link Gateway + EBM Portal (Backend)")
    print(" Master Admin: http://localhost:5000/admin")
    print(" EBM Portal:   http://localhost:5000/login")
    print("=======================================================\n")
    app.run(host="0.0.0.0", port=5000, debug=False)