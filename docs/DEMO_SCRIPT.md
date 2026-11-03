# RouteWise Operational Demonstration Script (5–7 Minutes)

This script outlines the exact live demonstration flow for evaluators and stakeholders. It walks through the system under three distinct roles (**Guest**, **Commuter / User**, and **Highway Patrol**), proves offline-resilient report queueing, inspects genuine environmental features, and highlights operational role-based controls.

---

## 0. Clean State Setup & Seed Commands

Before starting the evaluation, ensure the local environment is prepared and clean:

### Step 1: Database Bootstrap & Service Launch
```bash
# Prepare database tables and load segment weather data (first-time setup)
python -m app.bootstrap_db

# Terminal 1 - Backend (FastAPI on Port 8000)
.\venv\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

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
- **Demo Commuter:** `demo@routewise.ai` (Password configured via `DEMO_USER_PASSWORD` in `.env`, Role: `user`)
- **Demo Patrol Officer:** `patrol@routewise.ai` (Password configured via `DEMO_PATROL_PASSWORD` in `.env`, Role: `patrol`, flagged `is_simulated = 1`)

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
2. Sign in as commuter: `demo@routewise.ai` using the password configured in `DEMO_USER_PASSWORD`.
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
   - Email: `patrol@routewise.ai`
   - Password: password configured via `DEMO_PATROL_PASSWORD` in `.env`
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

## 5. Real-Time Intelligence & Demonstration Replay Walkthrough (Steps 1–7)

### Preparation & Mode Switch
1. In your environment or `.env`, configure:
   ```bash
   ROUTEWISE_LIVE_MODE=replay
   ```
2. Start the FastAPI backend:
   ```powershell
   .\venv\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
   ```
3. Open `http://localhost:5173` in your browser.

### What to Point Out & Demonstrate

1. **Live vs Historical Mode Toggle:**
   - In the dashboard header, locate the **Live / Historical Mode Toggle**.
   - With the toggle set to **Historical**, confirm that the view remains strictly on retrospective ERA5-Land reanalysis (2021–2025 backtest catalog) with 100% existing parity.
   - Switch the toggle to **Live Intelligence**:
     - Observe the persistent amber experimental banner: **"Live data - Experimental - not validated"**.
     - Note the telemetry metadata: telemetry age (e.g. `< 1h`), provider source badge (`replay` or `open-meteo`), and last-updated timestamp.
     - Note the honest scientific disclaimer explaining that live numerical weather represents a distribution shift from training data.

2. **July 2023 Multi-Day Storm Scenario Progression (5 Phases):**
   - In the Overview header or Scenario Player widget, step through the accelerated monsoon storm scenario:
     - **Phase 0 (Clear Baseline - 2023-07-06):** Calm conditions across all 151 segments. Model risk is Low (`●`). Journey Planner recommendation: **`PROCEED`**.
     - **Phase 1 (Early Advisory - 2023-07-07):** Atmospheric front arrives. Light precipitation rolls into 3-day window; initial cautionary warnings appear.
     - **Phase 2 (Severe Storm - 2023-07-08):** Torrential downpours (>120 mm). 72 segments escalate to High risk (`▲`). System generates active advisory alerts with a 1-hour de-duplication cooldown. Journey recommendation shifts to **`DELAY`**.
     - **Phase 3 (Landslide & Road Closure - 2023-07-09):** Critical simulated landslide strikes Ramban Gateway entrance segment (`2477017966_12734157829_0`). Operational status transitions to **`CLOSED`**.
     - **Phase 4 (Clearance & Recovery - 2023-07-10):** Weather stabilizes, debris is cleared, simulated hazards are purged. Segment risks drop below 0.60, and active alerts automatically clear.

3. **Single-Corridor Honesty in Journey Planning:**
   - Open **Journey Planner** (`/journey`) during Phase 3 (Road Closure).
   - Review the calculated route from Ramban to Banihal:
     - The baseline shortest distance remains ~36.2 km.
     - The risk-aware journey displays a prominent red banner: **`HOLD`**.
     - The reason explicitly states: *"Segment 2477017966_12734157829_0 is physically CLOSED due to active landslide. Traffic must halt."*
     - Point out the single-corridor disclosure: *"NH-44 is a single physical alignment through the Chenab gorge. No topological bypass exists; RouteWise will never invent synthetic detours."*

4. **Real-Time Streaming & In-Place UI Updates:**
   - Open browser DevTools -> Network -> inspect the Server-Sent Events stream: `GET /api/v1/live/stream`.
   - Observe periodic `heartbeat` events (every 20 seconds).
   - Advance a scenario step or trigger a hazard simulation: observe immediate dispatch of `risk_update`, `event_update`, `alert`, and `route_update` SSE messages.
   - Point out that the Corridor Strip and Map update smoothly in place without requiring full page reload.

5. **Active Alert Drawer & In-App Delivery Boundary:**
   - In the navigation bar, observe the Alert Bell badge displaying the active alert count. Click it to open the **Alert Drawer**.
   - Review bilingual alert notifications (English title/message and unreviewed Hindi translation).
   - Point out the honest delivery boundary note: *"RouteWise alerts are strictly delivered in-app; no external SMS gateways or cellular push daemons are claimed or utilized."*
   - Sign in as a Patrol Officer (`patrol@routewise.ai`): observe the **"Acknowledge"** and **"Clear"** action buttons, verifying that guest/commuter accounts cannot dismiss emergency alerts.

6. **Operator Hazard Simulation Control:**
   - Sign in as Administrator (`admin@routewise.ai`).
   - Use the simulated incident trigger panel or endpoint `POST /api/v1/events/simulate` to simulate hazards (`landslide`, `shooting_stones`, `single_lane`, `snow_ice`, `road_damage`).
   - Confirm all simulated incidents are explicitly badged **"SIMULATED"** and isolated strictly in `data/runtime/routewise_live.db`.
   - Click **"Clear All Simulated"** (`POST /api/v1/events/simulate/clear`) to instantly wipe all simulated hazards and return the highway to genuine observations.

### Spoken Disclaimer #4 (Say Out Loud)
> *"RouteWise live intelligence operates under an unvalidated distribution shift from its ERA5-Land reanalysis training data. Operational status overlays combine model risk with verified ground reports; on this single-road corridor, closures strictly prompt travel holds rather than imaginary detours."*

---

## 6. Teardown / Post-Demo Reset

To return the database to a clean, production-like state with all simulated demo data purged:
```bash
python -m app.seed_demo --clear
```
Output confirms: `All simulated reports and demo accounts have been purged.`
