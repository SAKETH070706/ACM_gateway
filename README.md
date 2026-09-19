# WhatsApp One-Time Link Gateway & EBM Dispatching Portal

A secure, anti-forwarding invitation gateway and multi-user Executive Board Member (EBM) team dispatching platform designed to protect private WhatsApp communities from unauthorized access and mass forwarding.

---

## Project Structure

```
wp_add_auto/
├── backend/
│   ├── app.py                 # Core Flask application, Blueprint registration, and SPA serving
│   ├── database.py            # SQLite connection pooling (get_db) and schema initialization (init_db)
│   ├── config.py              # Configuration manager (environment variables + settings table)
│   ├── invites.db             # Persistent SQLite database storage
│   ├── config.json            # Gateway runtime configuration
│   ├── requirements.txt       # Python dependencies (Flask, pandas, gunicorn)
│   ├── routes/
│   │   ├── auth.py            # Admin and EBM login/logout session APIs
│   │   ├── admin.py           # Student/EBM CSV parsing (overwrite & sync), batch splitting, tokens, templates
│   │   ├── ebm.py             # EBM personal dashboard APIs and live checkmark syncing
│   │   └── gateway.py         # Single-use public /join/<token> route with bot filters and device cookies
│   ├── samples/               # Sample data files
│   │   ├── sample_students.csv# Ready-to-use sample student roster
│   │   └── sample_ebm_team.csv# Ready-to-use sample EBM team credentials
│   └── templates/             # Gateway HTML templates (redirect.html, expired.html, invalid.html)
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.js      # Centralized REST client with credentials and error handling
│   │   ├── components/
│   │   │   ├── Navbar.jsx     # Top header with role badges, logout, and back-to-admin controls
│   │   │   ├── ProgressBar.jsx# Visual progress meters for student contact milestones
│   │   │   ├── Toast.jsx      # Action feedback notification system
│   │   │   └── Modal.jsx      # Dialog popups for tokens, EBMs, and templates
│   │   ├── pages/
│   │   │   ├── AdminDashboard.jsx # Master admin control center
│   │   │   ├── EbmDashboard.jsx   # Individual EBM dispatch queue, 1-click WhatsApp launcher, live sync
│   │   │   └── Login.jsx      # Unified login portal (Admin vs EBM tabs)
│   │   ├── App.jsx            # React Router (/admin, /login, /ebm/:username)
│   │   ├── index.css          # Custom CSS design system (--primary, --success, --border, etc.)
│   │   └── main.jsx
│   ├── dist/                  # Compiled production single-page application bundle
│   ├── index.html
│   ├── package.json
│   └── vite.config.js         # Local dev proxy targeting Flask on port 5000
├── run.bat                    # Windows 1-click launch script
├── Procfile                   # Process definition for cloud deployments (Render, Heroku)
├── vercel.json                # Serverless deployment configuration
├── .gitignore
└── README.md
```

---

## Core Security Features

1. **Automated Link-Preview and Crawler Filtering**:
   - Chat clients (WhatsApp, Telegram, Apple iMessage) automatically fetch preview cards.
   - The gateway inspects user agents and prefetch headers, serving preview metadata without consuming the one-time token.

2. **Device-Bound 15-Minute Grace Window**:
   - The first human visit claims the token (`is_used = 1`) and issues a secure `HttpOnly` cookie (`dev_token_<token>`).
   - For 15 minutes, the claiming browser can refresh or retry the redirect to WhatsApp.
   - After 15 minutes, the link permanently expires with an HTTP 410 error.

3. **Anti-Forwarding Across Shared Wi-Fi (NAT Isolation)**:
   - Forwarding the link to another person on the same Wi-Fi or hotspot will fail because their browser lacks the device cookie, immediately blocking access.

---

## Key Platform Capabilities

- **Dynamic CSV Ingestion via Pandas**:
  - Upload student lists of any size with automatic column matching (Name, Mobile, ACM ID, Branch).
  - **Clean Overwrite Mode**: Purges previous rosters and issues fresh single-use tokens.
  - **Smart Sync Mode**: Updates existing student info without invalidating already claimed tokens.
- **EBM Team Management & UPSERT**:
  - Upload or edit EBM team rosters with passwords and weights.
  - UPSERT guarantees no duplicate key errors.
- **Weighted Batch Splitting**:
  - Proportional round-robin distribution based on custom weights (e.g., 6 for team leads, 4 for regular members).
- **Message Template Builder**:
  - Dynamic placeholders (`{name}`, `{link}`, `{acm_id}`, `{phone}`, `{branch}`).
- **Personalized EBM Portals (`/ebm/:username`)**:
  - Scoped to assigned students with personal progress bars.
  - 1-click WhatsApp launcher (`wa.me`) with pre-filled encoded text.
  - 1-click copy message.
  - Instant checkmark toggle syncing back to SQLite.
- **Global Navigation**:
  - Persistent navigation bars with role badges, logout, and "Back to Master Admin" buttons.

---

## Installation & Running

### Prerequisites
- Python 3.9+
- Node.js 18+ (for frontend development)

### Quick Start (Windows)
Double-click `run.bat` or run:
```bash
python -m backend.app
```

### Accessing the Portals
- **Master Admin Dashboard**: `http://localhost:5000/admin` (Default password: `admin`)
- **EBM Member Login**: `http://localhost:5000/login`

### Default Pre-Seeded Accounts (from `sample_ebm_team.csv`)
- **EBM Lead Alpha (Lead, Weight 6)**: `ebm_lead_alpha` / `lead123`
- **EBM Lead Beta (Lead, Weight 6)**: `ebm_lead_beta` / `lead456`
- **EBM Member 01 (Member, Weight 4)**: `ebm01` / `pass123`
- **EBM Member 02 (Member, Weight 4)**: `ebm02` / `pass456`
- **EBM Coordinator 01 (Coordinator, Weight 4)**: `ebm_coord01` / `pass789`

### Development Mode
To run Flask and Vite concurrently with live hot-reloading:
```bash
# Terminal 1 (Flask API Backend)
python -m backend.app

# Terminal 2 (Vite React Frontend)
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser. All API requests are automatically proxied to Flask on port 5000.

---

## Decoupled Production Deployment (Vercel + Render)

### 1. Render (Flask Backend + SQLite)
1. Create a new **Web Service** on Render connected to your repository.
2. Configure build & start settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `gunicorn backend.app:app`
3. Add Environment Variables:
   - `FLASK_SECRET_KEY`: Random cryptographic secret (e.g., generated with `python -c "import secrets; print(secrets.token_hex(24))"`)
   - `FRONTEND_URL`: Your Vercel frontend URL (e.g., `https://your-frontend.vercel.app`)
   - `ADMIN_PASSWORD`: Custom master admin password (e.g., `strongpassword123`)
   - (Optional) Set up a Render **Disk** mount for `backend/` if you want persistent SQLite storage across free-tier spindowns.

### 2. Vercel (React Frontend Single Page App)
1. Import the repository into Vercel.
2. In the project settings, set:
   - **Root Directory**: `frontend`
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Add Environment Variable:
   - `VITE_API_BASE_URL`: Your Render backend URL (e.g., `https://your-backend.onrender.com`)
4. Deploy! All API requests from Vercel will send credentials/cookies across domains seamlessly to Render.
