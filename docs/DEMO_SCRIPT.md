# RouteWise Operational Demonstration Script (5–7 Minutes)

This script outlines the exact live demonstration flow for evaluators and stakeholders. It walks through the system under three distinct roles (**Guest**, **Commuter / User**, and **Highway Patrol**), proves offline-resilient report queueing, inspects genuine environmental features, and highlights operational role-based controls.

---

## 0. Clean State Setup & Seed Commands

Before starting the evaluation, ensure the local environment is prepared and clean:

### Step 1: Start Backend & Frontend Services
```bash
# Terminal 1 - Backend (FastAPI on Port 8000)
.\venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 - Frontend (Vite Dev Server on Port 5173)
cd frontend
npm run dev
```

### Step 2: Seed Simulated Operational Demo Data
To populate realistic sample reports and provision demo accounts without manual typing:
```bash
python -m app.seed_demo
```
*Seeded Accounts Created:*
- **Demo Commuter:** `commuter@routewise.local` / `Commuter2026!` (Role: `user`)
- **Demo Patrol Officer:** `patrol.ramban@routewise.local` / `DemoPatrol2026!` (Role: `patrol`, flagged `is_simulated = 1`)

*(To purge all simulated demo reports and accounts at any time, run: `python -m app.seed_demo --clear`)*

---

## 1. Role 1: Guest Observer (Read-Only Public Mode) — 1.5 Minutes

### Action & Navigation
1. Open `http://localhost:5173` in a fresh browser session (or Incognito).
2. On the **Welcome Landing Page**, click **"Continue as Guest"**.
3. Observe the immediate entry into the dashboard without entering credentials.

### What to Point Out
- **Guest Mode Indicator:** Note the prominent purple/blue callout in the sidebar: *"Guest mode — Read-only observation"*.
- **Role-Based Nav Gating:** Notice that the **Patrol Operations** tab is completely hidden from guests.
- **Continuous Corridor Strip:**
  - On the Overview page, inspect the 151-segment continuous horizontal Ramban–Banihal strip.
  - Hover over segments to see chainage landmarks (Dewal Km 0, Cafeteria Morh, Ramban, Maroog, Digdol, Ramsu, Banihal Km 36).
  - Point out that segments have non-color geometric cues (`●` Low, `■` Medium, `▲` High) for color-blind accessibility.
  - Use keyboard arrows (`←` / `→`) to step along the highway.
- **Risk Detail Drawer:**
  - Click on segment `SEG-042` or `SEG-110`.
  - The drawer slides out with **Genuine Input Features**: Mean elevation ASL (SRTM DEM), slope gradient, Copernicus ERA5-Land daily precipitation, and 7-day cumulative rainfall.
  - Show the honest scientific label: *"Input features for this segment; not a model explanation"*.
- **Enforced Read-Only Boundary:**
  - Click **"Incident Reporter"** from the navigation.
  - Point out the yellow notice: *"Guest mode: Please sign in or create an account to submit field incident observations"*. The backend rejects guest submissions with `HTTP 403 Forbidden`.

### Spoken Disclaimer #1 (Say Out Loud)
> *"RouteWise predictions on this corridor represent retrospective environmental reanalysis conditioned on historical Copernicus ERA5-Land weather and USGS SRTM topography. They provide advisory risk ranking for situational awareness; they do not represent live traffic or road safety guarantees."*

---

## 2. Role 2: Registered Commuter & Offline Sync Queue — 2 Minutes

### Action & Navigation
1. Click **"Exit Guest Session"** or navigate to `/auth/signin`.
2. Sign in as commuter: `commuter@routewise.local` / `Commuter2026!`.
3. Open the **Incident Reporter** tab (`/reports`).

### What to Point Out & Demonstrate
- **GPS Capture:** Click **"Acquire Current GPS Coordinates"** (or observe the Ramban fallback with estimated accuracy ±15m).
- **Incident Category Selection:** Select **"Shooting Stones"** or **"Landslide"**.
- **Evidence Attachment:** Attach a photo (JPEG/PNG/WebP). Show the privacy note: *"EXIF GPS and camera metadata are stripped on upload for privacy"*.
- **Offline-Resilient Persistent Queue Demonstration:**
  - Open DevTools -> Network Tab -> Toggle **Offline**.
  - Click **"Review & Submit Report"** -> **"Confirm and Submit to Dispatch"**.
  - Notice the green confirmation: *"Report Enqueued Successfully! Saved to local persistent queue..."*.
  - Switch to the **"Pending Queue"** subtab: see the item stored persistently in browser **IndexedDB** with its client UUID, photo preview, and status `pending`. Refresh the page to prove it survives reloads.
  - Toggle DevTools Network back to **Online**.
  - Watch the queue automatically trigger synchronization, change status to `syncing`, and transition to `sent`.
- **My Reports Timeline:** Switch to the **"My Reports"** tab to view the live status timeline of submitted reports.

### Spoken Disclaimer #2 (Say Out Loud)
> *"Photo uploads serve strictly as evidence for manual human patrol inspection. RouteWise does not perform automated computer-vision or ViT classification on field imagery."*

---

## 3. Role 3: Highway Patrol Operations Dashboard — 2 Minutes

### Action & Navigation
1. Sign out and sign in using the demo patrol officer account:
   - Email: `patrol.ramban@routewise.local`
   - Password: `DemoPatrol2026!`
2. Notice that the sidebar now displays the privileged **"Patrol Operations"** navigation item with a shield icon. Click it (`/patrol`).

### What to Point Out & Demonstrate
- **Operational Status Strip:** Review the live count cards across statuses: *Submitted (Pending Review)*, *Verified Hazards*, *Assigned Units*, and *Resolved Obstructions*.
- **Simulated Demo Data Badges:**
  - Notice the yellow **"SIMULATED"** badges on the seeded demo reports.
  - Highlight that demo records are never conflated with genuine field data and can be purged with one CLI flag.
- **Multi-Factor Filters:** Filter the queue by Category (*Landslide*, *Shooting Stones*) or Status.
- **Incident Inspection & State Machine Transition:**
  - Click **"Inspect & Take Action"** on a `submitted` report.
  - Review the report details: exact geographic coordinates, snapped corridor segment (e.g. `SEG-088`), reporter timestamp, and attached photographic evidence.
  - Demonstrate an allowed state machine transition:
    - Click **"Verify Incident"** -> Enter operational note: *"Patrol unit 1 confirms shooting stones at Maroog cutting"* -> Submit.
    - Notice the report immediately updates to `verified` and an append-only audit trail entry is created.
    - Next, assign the report to a patrol unit (`assigned`), and subsequently mark it `resolved`.
  - Point out that illegal transitions (e.g., attempting to resolve an unverified report) are rejected server-side with `HTTP 422 Unprocessable Content`.

---

## 4. Highway Reality, Advisories & Localization — 1.5 Minutes

### Action & Navigation
1. Open the **Journey Planner** (`/journey`).
   - Point out the honest highway disclosure: *"NH-44 between Ramban and Banihal is a single linear mountain corridor through the Chenab gorge. No parallel bypass roads or physical alternatives exist on this alignment."*
   - Change departure dates to compare historical risk exposure profiles across seasons (e.g., July monsoon vs October dry season).
2. Open the **Corridor Map** (`/map`).
   - Demonstrate the **Map Layer Control** toolbar in the top right:
     - Toggle **Risk Layer** (ST-GNN segment scores).
     - Toggle **Field Reports** (showing verified reports on the highway alignment).
     - Toggle **Weather Layer** (ERA5 daily rainfall overlay).
     - Toggle **Services Layer** (along-route hospitals, police, fuel, and recovery).
3. Return to **Overview** (`/overview`).
   - Scroll to **Official Traffic Advisories**: Show live handles and phone numbers for J&K Traffic Police and TCU Ramban/Banihal.
   - Scroll to **Along-Route Verified Services**: Show OSM-sourced medical and fuel facilities with verified sources.
4. **Theme & Localization Toggles:**
   - In the sidebar footer, click the **Theme Toggle** (`Sun` / `Moon`) to switch between Dark and Light mode. Point out that the Light mode uses WCAG AA charcoal-on-clean-surface contrast, not an unreadable inversion.
   - Click the **Language Toggle** (`EN` / `हिन्दी`) to demonstrate Hindi localization across all UI labels, hazard categories, and advisory banners.

### Spoken Disclaimer #3 (Say Out Loud)
> *"RouteWise provides predictive disruption modeling and operational dispatch support. Official J&K Traffic Police and Traffic Control Units (TCU) remain the sole legal authority on highway status and travel permission."*

---

## 5. Teardown / Post-Demo Reset

To return the database to a clean, production-like state with all simulated demo data purged:
```bash
python -m app.seed_demo --clear
```
Output confirms: `All simulated reports and demo accounts have been purged.`
