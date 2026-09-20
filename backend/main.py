import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.config import FRONTEND_DIST, init_async_db, close_async_db
from backend.routes.auth_api import auth_router
from backend.routes.admin_api import admin_router
from backend.routes.ebm_api import ebm_router
from backend.routes.gateway_api import gateway_router

# ----------------- PRODUCTION ENVIRONMENT CHECK -----------------
is_prod = bool(
    os.environ.get("RENDER") or
    os.environ.get("VERCEL") or
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
        print(f"WARNING: Missing production environment variables: {', '.join(missing_vars)}.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure async mongo client is initialized in running loop
    from backend.config import init_async_db, close_async_db
    db = init_async_db()
    try:
        await db.command("ping")
        print("Async MongoDB connection initialized successfully.")
    except Exception as e:
        print("Note on MongoDB ping at startup:", e)
    yield
    # Shutdown
    close_async_db()
    print("Async MongoDB connection closed.")

app = FastAPI(
    title="WhatsApp One-Time Link Gateway & EBM Dispatcher",
    description="High-Performance Asynchronous FastAPI + Motor MongoDB Application",
    version="2.0.0",
    lifespan=lifespan
)

# ----------------- SESSION MIDDLEWARE -----------------
secret_key = os.environ.get("FLASK_SECRET_KEY") or "ace_acm_portal_super_secret_session_key_2026_deterministic"
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    session_cookie="acm_session",
    max_age=86400 * 7,  # 7 days
    same_site="none" if is_prod else "lax",
    https_only=is_prod
)

# ----------------- CORS CONFIGURATION -----------------
default_origins = [
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

allow_origins = list(set(default_origins + env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=r"^https?://([a-zA-Z0-9-]+\.)*vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- MOUNT API ROUTERS -----------------
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(ebm_router)
app.include_router(gateway_router)

# ----------------- SERVE REACT SPA & STATIC ASSETS -----------------
assets_dir = os.path.join(FRONTEND_DIST, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/")
async def serve_index():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        {"message": "ACM Gateway API is running. Build frontend with 'npm run build' to view the web dashboard."},
        status_code=status.HTTP_200_OK
    )

@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # If request is intended for an API or join route that doesn't exist, return 404 JSON
    if full_path.startswith("api/") or full_path.startswith("join/"):
        return JSONResponse({"error": "Endpoint not found", "path": f"/{full_path}"}, status_code=404)

    # Check if exact static file exists in dist (e.g. favicon.ico, logo.png)
    file_path = os.path.join(FRONTEND_DIST, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)

    # SPA Fallback to index.html for client-side routing
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return JSONResponse(
        {"error": "Page not found", "path": f"/{full_path}"},
        status_code=status.HTTP_404_NOT_FOUND
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
