# RouteWise Live Date and Timezone Semantics

This document establishes the authoritative operational specification for date, lookback window, timezone, and data-freshness semantics across the RouteWise atmospheric pipeline (`WeatherScheduler`, `WeatherStorage`, `LiveRiskService`, `JourneyService`, and `AlertService`).

---

## 1. Timezone Mandate: Strict UTC Alignment

- **Canonical Timezone:** Universal Coordinated Time (`UTC`, `+00:00`).
- **Rationale:** The RouteWise Spatio-Temporal Graph Neural Network (ST-GNN) was trained on ECMWF ERA5-Land reanalysis observations, which aggregate atmospheric fluxes across strictly defined UTC calendar days: `[00:00:00Z to 23:59:59Z]`.
- **Prohibition:** Local time (`Asia/Kolkata`, IST, `UTC+05:30`), system clock offsets, and unparameterized `datetime.date.today()` are strictly prohibited in temporal window calculations.
- **Clock Injection:** All services and schedulers accept an injectable `clock` callable or `eval_time` parameter for reproducible simulation and deterministic frozen-clock verification.

---

## 2. Temporal Fields and Mathematical Definitions

Given a wall-clock or evaluation timestamp $\tau \in \text{UTC}$:

$$\text{today}_{\text{UTC}} = \text{date}(\tau)$$
$$\text{yesterday}_{\text{UTC}} = \text{today}_{\text{UTC}} - 1 \text{ day}$$

### 2.1 `as_of` (Target Advisory Date)
- **Live Mode:** Represents the forward operational target date for which route advisories and relative hazard indices are published:
  $$\text{as\_of} = \text{today}_{\text{UTC}}$$
- **Replay Mode:** Represents the simulated corridor target date (e.g. `2024-07-15`), derived from the latest replay observation date in storage.
- **Historical Mode:** Explicit date requested by the user from the retrospective archive (e.g. `2023-07-09`).

### 2.2 `weather_window_end` (Last Complete Meteorological Day)
- **Ongoing UTC Day Incompleteness:** On any current day $\text{today}_{\text{UTC}}$, atmospheric measurements are partial and incomplete. Ingesting ongoing hours would corrupt 24-hour aggregations (daily precipitation sum, minimum temperature, snow depth).
- **Window End Rule:** Live inference queries strictly complete historical days. The latest complete day is yesterday UTC:
  $$\text{weather\_window\_end} = \text{yesterday}_{\text{UTC}}$$
- **Persistence:** `weather_window_end` is persisted as a dedicated column in the `live_risk` SQLite table. It is an immutable physical datum, never dynamically derived as `as_of - 1` at read time.

### 2.3 The 7-Day Lookback Window
The ST-GNN architecture requires a contiguous 7-day temporal window ($W = 7$ days) across all $N = 151$ corridor segments ($1,057$ dynamic feature vectors):

$$\text{Lookback Window} = [\text{weather\_window\_end} - 6 \text{ days}, \quad \text{weather\_window\_end}]$$

If any segment lacks complete observations for all 7 dates, or exceeds the missing-data threshold ($25\%$), the corridor evaluates safely to `risk_tier="UNKNOWN"` and `status="MISSING_DATA"`.

---

## 3. Data Freshness and Staleness Rule

RouteWise enforces a single unified freshness threshold across all components:

$$\text{MAX\_DATA\_AGE\_HOURS} = 24.0 \text{ hours}$$

### 3.1 Live Mode Staleness Rule
A risk evaluation is classified as **Fresh** (`is_stale = False`) if and only if both conditions hold:
1. **Window Alignment:** The underlying weather lookback window closed yesterday UTC relative to the evaluation clock:
   $$\text{weather\_window\_end} = \text{yesterday}_{\text{UTC}}$$
2. **Elapsed Compute Age:** The time elapsed since model inference was computed does not exceed the operational threshold:
   $$\tau - \text{computed\_at} \le 24.0 \text{ hours}$$

If $\text{weather\_window\_end} < \text{yesterday}_{\text{UTC}}$ (e.g. 2 or more days old) or $\tau - \text{computed\_at} > 24.0\text{h}$, the evaluation is classified as **Stale** (`is_stale = True`).

### 3.2 Read-Time Invariant
When live data is stale:
- `risk_score` maps to `None`.
- `risk_tier` maps to `"UNKNOWN"`.
- `status` maps to `"STALE_DATA"`.
- Active hazard alerts retain their state with `is_stale_context = True` (alerts are never silently auto-cleared on stale data).
- The journey planner marks the route recommendation as `"NO DATA"`.

---

## 4. Daily UTC-Midnight Gap Analysis & Mitigation Proposal

### 4.1 Root Cause of the Midnight Gap
At `00:00:00Z` on any calendar day $D$:
1. The calendar clock shifts `today_utc` to $D$, and `yesterday_utc` becomes $D-1$.
2. The weather database's latest complete historical day is $(D-1)-1 = D-2$ until the daily batch fetch for day $D-1$ executes.
3. Because $\text{weather\_window\_end} = D-2 < \text{yesterday}_{\text{UTC}} = D-1$, condition 1 of the freshness rule fails immediately.
4. If the scheduler runs periodically (e.g. every 60 minutes), there is an operational window between `00:00:00Z` and the subsequent scheduled fetch (up to 60 minutes) during which the corridor evaluates safely to `risk_tier="UNKNOWN"` and `status="STALE_DATA"`.

### 4.2 Engineering Proposal to Shrink the Midnight Window
To minimize or eliminate this daily transition window without sacrificing meteorological integrity:
1. **Targeted Midnight Fetch Trigger (`00:05 UTC`):** Configure an explicit cron/scheduler tick at `00:05 UTC` (5 minutes after UTC midnight) specifically to poll and archive yesterday's 24-hour observation window as soon as Open-Meteo seals the day. This shrinks the maximum gap from 60 minutes to under 5 minutes.
2. **Provider Upstream Latency Grace Period (Optional Architectural Enhancement):** If upstream weather archiving exhibits a publication delay (e.g., Open-Meteo publishing yesterday's final hourly measurements at 00:30 UTC), downstream read endpoints can support a configurable 60-to-120 minute grace period: between `00:00:00Z` and `01:30:00Z`, if $\text{weather\_window\_end} = D-2$ and $\tau - \text{computed\_at} \le 24.0\text{h}$, the advisory displays as `PENDING_DAILY_UPDATE` with last-known risk preserved rather than dropping abruptly to `UNKNOWN`.


