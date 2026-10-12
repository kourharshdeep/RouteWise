# RouteWise: Detailed 16-Week Development Plan

An Edge-Resilient GeoAI and Predictive Logistics Platform for Disruption-Aware Routing on the NH-44 Corridor (Jammu & Kashmir)

Minor Project Group 21 | B.Tech Computer Science and Engineering | MIET Jammu | 2026

## 1. Purpose and expected use

This brief converts the RouteWise abstract, the Plane work items (COM71121) and the work already completed in the repository into a 16-week implementation plan that can be supplied to Antigravity and used for weekly project reviews. It defines a credible MVP, technical work packages, interface expectations, measurable completion gates, and evidence the team should retain. Antigravity should act as an implementation assistant under student supervision; students remain responsible for understanding, testing, documenting, and defending every design and code change.

The plan is deliberately evidence-first and honest about progress. Weeks 1–6 are already complete and are recorded as such; each carries a short close-out checklist so the finished work can be reviewed as evidence. Week 7 closes the model stage, and Weeks 8–16 cover the remaining build, integration, validation and release. RouteWise must treat a forecast as a risk estimate, not a guarantee, and must show when its data is stale, sparse or uncertain rather than presenting a route as safe.

**Project outcome.** An offline-first field and routing system for the pilot corridor: field observers record geo-tagged hazards without connectivity; reports synchronise safely when a link returns; an ST-GNN predicts short-horizon disruption risk per road segment; a risk-aware router suggests safer paths and advisories; and a web dashboard shows risk, field reports and corridor status to administrators.

## 2. Scope and operating principles

### 2.1 MVP scope

- **Pilot corridor.** Ramban to Banihal on NH-44 (latitude 33.211 to 33.475, longitude 75.161 to 75.262), a landslide-prone stretch. Extending to the wider NH-44 corridor is a gated stretch goal, not an MVP requirement.

- **Hazards.** Landslide, snow and shooting-stone disruption, predicted per road segment at a short horizon chosen and justified in Week 7. Other hazards are reported by field users but are not modelled unless data supports them.

- **Model.** A spatio-temporal graph neural network (graph convolution plus temporal recurrent layers) over the corridor graph, using terrain, weather and historical disruption features, compared against the Week 5 baselines.

- **Offline-first field capture.** A Flutter app that records geo-tagged reports and photographs to local SQLite, queues them during connectivity loss, and tracks synchronisation status per record.

- **Synchronisation.** A FastAPI service that accepts queued reports idempotently, prevents duplicates using client IDs, timestamps and GPS proximity, and resolves concurrent submissions with documented rules.

- **Risk-aware routing.** A shortest-path search weighted by predicted risk, with re-routing when a segment crosses a risk threshold. Because the pilot stretch has few alternate roads, the router must also be able to return a delay/hold advisory rather than inventing an alternative.

- **Dashboard.** A web GIS dashboard with risk heat map, field-report markers and an administrative monitoring view.

- **Stretch (gated).** Wider-corridor coverage, additional hazard types, and model retraining from verified field reports. None may start until the Week 14 gate is passed.

### 2.2 Non-negotiable design principles

- **Risk is an estimate:** every prediction is shown with its horizon, model version, data timestamp and a stated limitation. The system supports decisions; it does not guarantee that a road is open or safe.

- **Offline is the normal case, not an error:** capture, local storage and queueing must work with no network, and the user must always see what has and has not been synchronised.

- **Provenance before conclusion:** every label, feature and prediction keeps its source (dataset, extraction date, geocoding method, snapping distance, model version).

- **Uncertainty is visible:** stale weather, unsnapped events, low-confidence geocodes and out-of-range inputs lead to a visible warning state, never a silent default.

- **Human authority:** field reports are unverified until reviewed; routing output is advisory for drivers and administrators.

- **Reproducibility:** data pipelines, training and evaluation are scripted, seeded and versioned so results can be regenerated from a clean checkout.

- **Measured claims only:** report metrics with sample counts, class balance and the evaluation split. Do not claim accuracy from a single ideal case or from training data.

- **Privacy and security by default:** collect only needed location and photo data, protect credentials and uploads, and define a retention policy for test data. Never commit secrets or personal data.

## 3. Current progress baseline and Plane mapping

The Plane board lists 12 weekly work items. This plan expands them to 16 weeks by adding a model-evaluation/serving week, separating backend foundation from synchronisation, and splitting mobile build from mobile–backend integration. The repository README currently records Weeks 1–3 and the dataset preparation as done, the ST-GNN architecture and training as done, and the FastAPI backend synchronisation as next. Please update the Plane states to match (several completed items still show Backlog or Todo).

| **Week** | **Topic**                                        | **Plane item**      | **Status** | **Existing artifacts (from repository)**                                                                                     |
|----------|--------------------------------------------------|---------------------|------------|------------------------------------------------------------------------------------------------------------------------------|
| 1        | GIS data and NH-44 corridor graph                | Week 1 (COM71121-4) | Done       | week1_graph_and_terrain.py, nh44_corridor_graph.graphml, corridor_dem.tif, segment_static.csv, segment_adjacency.csv         |
| 2        | Weather and historical disruption data           | Week 2 (-5)         | Done       | week2a–2c scripts, data/weather, weather_daily_by_segment.csv, disruption_log\*.csv, labelled_events.csv, geocode_report.csv |
| 3        | Offline-first SQLite schema                      | Week 3 (-6)         | Done       | week3_create_db.py, week3_offline_schema.sql, routewise_local.db                                                             |
| 4        | Model dataset preparation                        | Prep (feeds Wk 6–7) | Done       | week4_build_dataset.py, training_samples.csv                                                                                 |
| 5        | ST-GNN architecture and baselines                | Week 6 (-9)         | Done       | week6_stgnn.py, week6_baseline_metrics.json                                                                                  |
| 6        | ST-GNN training and tuning (Colab)               | Week 7 (-10)        | Done       | week7_train.py, stgnn_best.pt, stgnn_metrics.json, stgnn_metrics_default.json                                                |
| 7        | Model evaluation, calibration and serving export | Extends Week 7      | Next       | New: model card, serving wrapper, calibration                                                                                |
| 8        | Backend foundation and risk API                  | Week 5 part 1 (-8)  | Next       | New: FastAPI service                                                                                                         |
| 9        | Synchronisation and conflict resolution          | Week 5 part 2 (-8)  | Planned    | Builds on Week 3 sync metadata                                                                                               |
| 10       | Flutter app: capture UI and offline writes       | Week 4 (-7)         | Planned    | Builds on Week 3 schema                                                                                                      |
| 11       | Mobile–backend integration and sync hardening    | Weeks 4+5           | Planned    | New                                                                                                                          |
| 12       | Risk-aware routing                               | Week 8 (-11)        | Planned    | Uses corridor graph and model output                                                                                         |
| 13       | GIS dashboard                                    | Week 9 (-12)        | Planned    | New                                                                                                                          |
| 14       | Full integration, end-to-end tests, security     | Week 10 (-13)       | Planned    | New                                                                                                                          |
| 15       | Validation and performance benchmarking          | Week 11 (-14)       | Planned    | New                                                                                                                          |
| 16       | Deployment, documentation and demonstration      | Week 12 (-15)       | Planned    | New                                                                                                                          |

The model comes before the app because routing (Week 12) needs the model’s output. The order above keeps that dependency while giving the backend and sync work enough time before the app is integrated.

## 4. Antigravity working instructions

Paste this section before the week-specific ticket into Antigravity. Students should then provide the relevant Plane issue, acceptance criteria, and current repository context.

- Start by inspecting the existing repository, README, dependency files, current branch, open issues, and the linked Plane project. Do not overwrite or restructure working scripts, datasets, or the trained model before explaining the current architecture and proposing a small change set.

- Treat this plan, the abstract, approved project scope, and Plane issue acceptance criteria as requirements. If they conflict, identify the conflict and ask the student team to resolve it before implementing the dependent feature.

- Do not modify or regenerate files in data/, stgnn_best.pt, or routewise_local.db without explicit approval and a backup. Write new outputs to versioned paths and record how they were produced.

- Work in small vertical increments. Before editing, state the intended files and design. After editing, summarise changed files, commands run, test results, limitations, and any manual verification still required.

- Use typed request/response schemas, input validation, clear error states, structured logging without sensitive location or photo data, and configuration through environment variables. Never commit secrets, API keys, personal data, or credentials (check that .env is git-ignored).

- Add tests at module boundaries and for failure paths: offline writes, duplicate reports, out-of-order sync, stale risk data, missing weather, and routes with no safe alternative. Use deterministic, seeded fixtures. Do not claim a feature is complete because it runs on one ideal sample.

- Keep the mobile and web interfaces responsive and accessible: semantic labels, readable contrast, large touch targets for field use, and clear empty, loading, offline and error states.

- When proposing a library or model, state why it is needed, its license and deployment weight, and how it will be evaluated. Prefer the existing stack (Python, SQLite, PyTorch, FastAPI, Flutter) unless a documented technical reason justifies a change.

- Do not silently broaden the project. Mark work as MVP, stretch, or deferred, and obtain faculty review through the established project process for scope changes.

## 5. Product experience and interface direction

Create calm, professional interfaces that help a field observer record a hazard quickly with gloves on poor signal, and help an administrator understand corridor risk at a glance. Use established mapping and productivity tools as interaction references only; do not copy branding or proprietary assets.

### 5.1 Field app (Flutter) screens

- **Home / status:** connectivity state, count of unsynchronised reports, last successful sync, and a prominent “New report” action.

- **New report:** hazard type (landslide, snow, shooting stone, other), automatic GPS tag with manual correction, photo attachment, optional note, and severity. Works fully offline.

- **Outbox:** every saved report with a clear state (saved locally, queued, syncing, synced, failed, conflict) and a retry action.

- **Corridor risk view:** segment risk levels with the prediction time and horizon, a staleness indicator, and a clear note when the data is from the last known sync.

- **Route advice:** suggested path or delay/hold advisory, why it was chosen, and the risk values used.

### 5.2 Dashboard (web) screens

- **Corridor overview:** map with risk heat map by segment, filters for hazard type and time, and a legend that states horizon and model version.

- **Field reports:** markers with photo, time, status (unverified, verified, rejected), and sync origin; reviewer actions are audited.

- **Administration:** monitoring view for NH-44 status, report volume, sync health, and data freshness, with denominators shown for every figure.

- **About and limitations:** data sources, model version, supported corridor, and a clear statement that predictions are advisory.

### 5.3 Visual and interaction standards

- Use a consistent design system: restrained neutral canvas, strong typographic hierarchy, one primary accent colour, semantic risk colours, and reusable spacing tokens.

- Use text labels and icons in addition to colour for risk levels, and use a colour-blind-safe sequential palette for the heat map.

- Show uncertainty: prediction time, horizon, and data age beside every risk value. Never present a stale or missing prediction as “low risk”.

- Show progress for sync and long-running tasks, allow retry after recoverable errors, and never discard a locally saved report on failure.

- Use realistic synthetic demo records labelled as demo data. Do not show real observers’ identities or locations in screenshots.

## 6. Suggested architecture and technical contracts

**Data and model layer (existing).** Python scripts and CSV/GraphML/GeoTIFF artifacts for the corridor graph, terrain, weather and disruption labels; PyTorch ST-GNN trained in Google Colab. Wrap the trained model in a versioned inference module with a documented input and output contract.

**Edge layer.** Flutter application with local SQLite (schema from Week 3), an outbox table for queued reports, and a connectivity monitor. Photos are stored on device with a content hash until uploaded.

**Backend.** Python FastAPI with versioned REST endpoints, Pydantic validation, and separate services for ingestion/sync, risk prediction, routing, and reports. Persist server data in PostgreSQL (PostGIS optional) or, if the team documents the reason, SQLite for a clearly labelled prototype. Store images outside relational rows with references and hashes.

**Routing.** Graph-based search over the corridor graph (for example NetworkX) with an edge cost that combines travel cost and predicted risk; the weighting must be configurable and evaluated against a distance-only baseline.

**Dashboard.** React or a lightweight web front end with a map library such as Leaflet or MapLibre, consuming the same API.

**Deployment.** Docker Compose for reproducible local setup, health checks, migrations, and a sample environment file without secrets. Cloud deployment only after a reproducible local demonstration and an access-control review.

### 6.1 Core data objects

- **RoadSegment:** segment ID, geometry, length, elevation/slope/terrain features, adjacency, and the corridor graph version.

- **WeatherObservation:** segment or grid reference, timestamp (with time zone), variables, source, and processing version.

- **DisruptionEvent:** event ID, hazard type, start/end, raw location text, geocode method and confidence, snapped segment and snap distance, label source, and review state.

- **FieldReport:** client-generated UUID, observer ID, hazard type, GPS and accuracy, device timestamp, server receive timestamp, photo hashes, sync status, verification state.

- **SyncRecord:** report ID, attempt count, last error, server version, and conflict outcome.

- **RiskPrediction:** segment ID, hazard type, horizon, valid-from time, probability/score, model version, input data timestamps, and uncertainty or staleness flags.

- **RouteAdvice:** origin, destination, selected path or advisory, risk values used, alternatives considered, weighting parameters, and software/model version.

- **AuditEvent:** actor, action, timestamp, object, before/after summary, and correlation ID, without secrets or unnecessary personal data.

### 6.2 API and processing contracts

- Document endpoints for authentication, uploading queued reports and photos, reading sync status, requesting segment risk for a time window, requesting route advice, listing field reports, and administrative review.

- Make uploads idempotent: the client UUID is the idempotency key, so a retry after a dropped connection can never create a duplicate record.

- Validate file type, size, coordinates (inside the supported bounding box, with accuracy), and timestamps (including clock skew from offline devices). Use opaque object IDs; do not trust client-supplied paths.

- Return actionable error codes: invalid payload, duplicate (already accepted), conflict, stale model data, out-of-corridor location, and processing failure.

- Make predictions reproducible by recording the model version, feature timestamps and parameters used for each run.

- Publish an OpenAPI contract and keep the mobile, dashboard and backend schemas synchronised.

## 7. Sixteen-week implementation plan

Each weekly review should assess the deliverables and acceptance gate below, not just the amount of code written. Teams should show a running demo or reproducible artifact where the week calls for one, update Plane issues, and retain a short review note with evidence. For completed weeks (1–6) the work is already done; the review is a close-out check that the evidence is documented, reproducible and consistent with the gates.

### Week 01: GIS data acquisition and NH-44 corridor modelling

**Status: DONE** Completed before this plan. Close-out only.

**Weekly objective.** Establish the spatial foundation for the pilot corridor: road geometry, terrain and a graph of road segments.

#### Implementation work

- Road segments for the pilot corridor extracted from OpenStreetMap; SRTM elevation processed into a terrain profile (corridor_dem.tif); the road network represented as a graph with segments as nodes and connectivity as edges (nh44_corridor_graph.graphml, segment_static.csv, segment_adjacency.csv).

- Close-out: record the OSM extract date, SRTM source and resolution, coordinate reference system, bounding box, and the segment-ID scheme in a short data note.

- Close-out: run and save graph sanity checks (connected components, segment count, length totals, no orphan nodes) and confirm the corridor map (week1_corridor_map.png) matches the graph.

- Close-out: state whether the graph models segments as nodes or edges consistently across the code, and note any simplifications.

#### Acceptance gate for review

- The corridor graph and terrain features regenerate from week1_graph_and_terrain.py on a clean checkout, with documented inputs.

- Segment IDs are stable and referenced identically by every later dataset.

- Data note lists sources, dates, licences and known limitations.

**Review evidence to attach in Plane.** Data note, graph checks output, corridor map, scripts, and the Plane item (COM71121-4) marked Done.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 02: Meteorological and historical disruption data integration

**Status: DONE** Completed before this plan. Close-out only.

**Weekly objective.** Assemble the environmental and historical-event datasets that become model features and labels.

#### Implementation work

- Gridded weather data downloaded and processed to daily values per segment (week2a, week2b, weather_daily_by_segment.csv); historical disruption records collected, geocoded and snapped to graph segments (week2c scripts, disruption_candidates.csv, disruption_log.csv, disruption_log_snapped.csv, labelled_events.csv, events_map.png).

- Close-out: build a label-provenance register recording the source and date of each disruption record, its geocoding method and confidence, and the snap distance to the segment.

- Close-out: resolve or explicitly document every row in needs_manual_coordinates.csv and geocode_report.csv, and state how many events were excluded and why. Unresolved rows must not silently become negative labels.

- Close-out: document time-zone and temporal-alignment rules between weather and event timestamps, and the hazard-type taxonomy (landslide, snow, shooting stone).

#### Acceptance gate for review

- Every labelled event traces to a source and a segment with a stated snap tolerance.

- Counts of events per hazard, per segment and per period are reported, including excluded records.

- Weather features align in time with labels without using information from after the event.

**Review evidence to attach in Plane.** Label-provenance register, geocode and manual-coordinate resolution notes, event counts table, events_map.png, scripts, and Plane item (-5) marked Done.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 03: Offline-first field reporting schema

**Status: DONE** Completed before this plan. Close-out only.

**Weekly objective.** Define the local database that lets field observers record hazards with no connectivity and later reconcile them.

#### Implementation work

- SQLite schema for geo-tagged hazard reports and photographs, queueing logic for connectivity loss, and metadata for synchronisation status (week3_create_db.py, week3_offline_schema.sql, routewise_local.db).

- Close-out: produce an ERD and data dictionary, including the sync-metadata fields (client UUID, status, attempt count, device and server timestamps, version).

- Close-out: add schema versioning/migration notes and a small test that inserts, queues, marks synced, and marks failed.

- Close-out: confirm that no real personal data or real observer locations are stored in routewise_local.db or committed to the repository.

#### Acceptance gate for review

- A report can be created, queued, and have its sync state updated purely through the schema, with a documented example.

- The schema supports duplicate detection (client UUID, timestamp, GPS) needed in Week 9.

- Schema is documented and reproducible from week3_create_db.py.

**Review evidence to attach in Plane.** ERD, data dictionary, schema test output, sample queued-report record, and Plane item (-6) marked Done.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 04: Model dataset preparation

**Status: DONE** Completed before this plan (recorded as Prep in the README). Close-out only.

**Weekly objective.** Turn the processed features and labels into a leakage-safe training dataset for the ST-GNN.

#### Implementation work

- Feature and label tensors assembled per segment and time step (week4_build_dataset.py, training_samples.csv).

- Close-out: write a dataset card covering feature list, prediction horizon, label definition, class balance, time coverage and known biases (rare events, reporting bias towards accessible areas).

- Close-out: document the train/validation/test split. Use a chronological split so that no future information leaks into training, and state the periods used.

- Close-out: record how missing weather values and unsnapped events are handled, with counts.

#### Acceptance gate for review

- Dataset regenerates from week4_build_dataset.py with a fixed seed and documented inputs.

- The split is time-ordered and leakage checks (no overlap of windows across splits) are documented.

- Class balance per hazard and per split is reported.

**Review evidence to attach in Plane.** Dataset card, split manifest, leakage check output, class-balance table, and script.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 05: ST-GNN architecture development and baselines

**Status: DONE** Completed before this plan (Plane Week 6). Close-out only.

**Weekly objective.** Build the spatio-temporal model and establish simple baselines to compare against.

#### Implementation work

- Graph convolution layers for spatial dependency, temporal recurrent layers for sequence-based prediction, and a loss function based on historical disruption labels (week6_stgnn.py); baseline metrics recorded (week6_baseline_metrics.json).

- Close-out: document the architecture (layers, input shape, output shape), the loss and any class-imbalance handling, and the baselines used (for example persistence or climatology/threshold models).

- Close-out: add a smoke test that builds the model and runs a forward pass on a tiny deterministic batch.

#### Acceptance gate for review

- The architecture is reproducible from the script and the documented configuration.

- Baselines are defined, run on the same split, and their metrics are saved.

- Smoke test passes on a clean environment.

**Review evidence to attach in Plane.** Architecture diagram, model configuration, baseline metrics table, smoke test output, and Plane item (-9) marked Done.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 06: ST-GNN training and hyperparameter tuning

**Status: DONE** Completed before this plan (Plane Week 7, trained in Google Colab). Close-out only.

**Weekly objective.** Train the model on the prepared dataset and tune it for short-horizon prediction.

#### Implementation work

- Training cycles and hyperparameter tuning completed in Colab (week7_train.py), producing the best checkpoint (stgnn_best.pt) and metrics files (stgnn_metrics.json, stgnn_metrics_default.json).

- Close-out: record the exact configuration, seed, training environment (library versions, hardware), epochs, and how the best checkpoint was selected (on validation data only).

- Close-out: confirm the test set was not used for tuning and keep the default-versus-tuned comparison as evidence.

- Close-out: store a checksum for stgnn_best.pt and decide where large artifacts live (for example Git LFS or an external store) so the repository stays small.

#### Acceptance gate for review

- Training can be rerun from the script and configuration, and reaches comparable metrics.

- Test metrics come from a held-out period that was not used for model selection.

- The checkpoint is identified by version and hash.

**Review evidence to attach in Plane.** Training configuration, environment note, metrics files, comparison of default and tuned models, checkpoint hash, and Plane item (-10) marked Done.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 07: Model evaluation, calibration and serving export

**Status: NEXT** Extends the completed training work; bridges to the backend.

**Weekly objective.** Turn the trained model into an evaluated, documented and serveable component, with honest reporting on rare events and uncertainty.

#### Implementation work

- Evaluate on the held-out chronological test set with metrics suited to rare events: precision, recall, F1 and precision–recall AUC per hazard and per horizon, with sample counts and positive-event counts. Do not rely on accuracy alone.

- Compare against the Week 5 baselines and report failure cases (missed events, false alarms) by segment, season and hazard type.

- Assess probability calibration (reliability curve, Brier score) and choose risk-level thresholds (for example low/medium/high) with a documented rationale. If calibration is poor, apply and evaluate a calibration step.

- Write the model card: intended use, data, horizon, metrics, limitations, and the statement that outputs are advisory risk estimates.

- Build a versioned inference module with a typed input/output contract that returns a risk score for every segment for a given timestamp, plus a batch pre-compute script so the backend and router do not need to run the model per request. Measure CPU inference latency.

#### Acceptance gate for review

- Metrics are reproducible from scripts on the frozen test period and are not tuned on it.

- Loading the checkpoint on a clean checkout returns segment risk for a sample timestamp, validated by a test.

- Model card states limitations, thresholds and the data window the model was trained on.

**Review evidence to attach in Plane.** Evaluation report with tables and plots, calibration results, threshold note, model card, inference module with tests, latency measurement.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 08: Backend foundation and risk API

**Status: NEXT** The README lists the FastAPI backend as next.

**Weekly objective.** Create a thin, working server foundation with typed contracts, safe file handling and a first risk endpoint.

#### Implementation work

- Create the FastAPI application structure with configuration through environment variables, Pydantic schemas, API versioning, health checks, a common error model, structured request logging, and generated OpenAPI documentation.

- Define the server database schema and migrations for observers/devices, field reports, photos, sync records, predictions and audit events; keep seed/demo data clearly separate from real records.

- Implement a basic authentication scheme for field devices and administrators with least-privilege roles (field observer, reviewer, administrator), enforced server-side.

- Implement GET endpoints for segments and segment risk for a time window, reading from pre-computed model output with the model version and data timestamp in every response.

- Add an object-storage abstraction for photos (local development and S3-compatible), store hashes and references rather than blobs in rows, and validate size and type on upload.

- Add CI for formatting, linting, type checks, unit tests and migration validation, plus Docker Compose for local setup.

#### Acceptance gate for review

- The service starts from documented commands or Docker Compose, and the health endpoint and OpenAPI page load.

- The risk endpoint returns segment risk with model version and timestamp, and returns an explicit stale/unavailable state when data is missing.

- Unauthenticated and unauthorised requests fail safely; no secrets are present in the repository; CI catches an intentionally failing test.

**Review evidence to attach in Plane.** Running API, OpenAPI document, migrations, role matrix, upload validation tests, CI workflow, and architecture notes.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 09: Synchronisation protocol and conflict resolution engine

**Status: PLANNED** Plane Week 5 (COM71121-8).

**Weekly objective.** Make queued offline reports reconcile safely and predictably once connectivity returns.

#### Implementation work

- Design and document the sync protocol: batch upload of queued reports, per-record acknowledgement, resumable photo upload with hash verification, and exponential-backoff retry rules.

- Implement idempotent ingestion using the client UUID, and duplicate prevention for near-identical reports using timestamps and GPS proximity (document the time window and distance thresholds and justify them).

- Implement server-side conflict resolution for concurrent submissions about the same hazard (for example merge as corroborating evidence rather than overwrite), keeping all original reports and recording the outcome in the sync record.

- Handle device clock skew, out-of-order delivery, partial uploads, and reports outside the corridor, each with a defined result and error code.

- Write tests with simulated duplicates, retries after dropped connections, out-of-order batches, and concurrent submissions.

#### Acceptance gate for review

- Replaying the same batch multiple times creates no duplicates and loses no reports.

- Conflicting or corroborating reports are merged by documented rules, and the original reports remain retrievable.

- Failure cases return clear codes, and the client can resume without data loss.

**Review evidence to attach in Plane.** Sync protocol document, ingestion and conflict-resolution code, duplicate and conflict test suite, sequence diagram, and results of the simulated failure runs.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 10: Flutter field app: capture UI and offline writes

**Status: PLANNED** Plane Week 4 (COM71121-7).

**Weekly objective.** Give field observers a fast, reliable way to record hazards with no connectivity.

#### Implementation work

- Build the home/status, new-report, and outbox screens with hazard type, GPS tagging with accuracy display and manual correction, photo attachment, severity, and optional note.

- Implement local write operations against the Week 3 SQLite schema so that every saved report survives app restarts and low-battery shutdowns.

- Develop the background service that monitors connectivity and updates the outbox state; keep the app usable in airplane mode.

- Handle permission states (location, camera, storage), low GPS accuracy, photo compression and storage limits with clear messages.

- Build empty, loading, saved-offline, failed and unsupported-device states, and test on at least one low-end phone profile and one emulator.

#### Acceptance gate for review

- A user can create, edit, and delete a draft report in airplane mode, close the app, and find the report still queued.

- Outbox shows accurate states for every report.

- Interface is usable one-handed with large touch targets and readable in bright light.

**Review evidence to attach in Plane.** App screens and walkthrough recording, offline-write tests, permission-state tests, device notes, and usability observations.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 11: Mobile–backend integration and sync hardening

**Status: PLANNED** Combines the integration half of Plane Weeks 4 and 5.

**Weekly objective.** Connect the app to the sync API and prove that data survives real-world connectivity patterns.

#### Implementation work

- Wire the app to the sync endpoints, with background sync on connectivity restoration, retry with backoff, and display of conflict or rejection outcomes to the user.

- Show the latest risk data in the app with its timestamp and staleness indicator, and cache it locally for offline use.

- Run network-failure simulations: drop mid-upload, long offline periods with many queued reports, poor-bandwidth photo uploads, and clock changes.

- Review privacy: minimise location and photo metadata sent, strip unnecessary EXIF data where appropriate, and document retention.

- Field reports remain “unverified” until reviewed; document that reports are not automatically used for model retraining in the MVP.

#### Acceptance gate for review

- End-to-end test: a report created offline appears on the server exactly once after reconnection, with the photo hash verified.

- The queue recovers from induced failures without loss or duplication.

- The app clearly shows data age when working offline.

**Review evidence to attach in Plane.** Integration test results, failure-simulation log, sync metrics (success rate, duplicates, loss), privacy note, and demo recording.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 12: Risk-aware routing

**Status: PLANNED** Plane Week 8 (COM71121-11).

**Weekly objective.** Use predicted risk to suggest safer paths and advisories on the corridor graph.

#### Implementation work

- Implement a shortest-path search weighted by travel cost plus a configurable multiple of predicted segment risk, using the corridor graph and Week 7 risk output.

- Implement dynamic re-routing when a segment exceeds the risk threshold, and a defined advisory output (proceed with caution, delay, or hold) when no safe alternative exists in the pilot corridor.

- Define the fallback when risk data is stale or unavailable: use the last known risk with a visible staleness warning, never a silent “safe” default.

- Evaluate against a distance-only baseline on historical event periods: risk exposure reduction, added distance or time, and the fraction of cases where no alternative exists. Report these honestly, including cases where the router adds no value.

- Expose routing through the API and add tests for thresholds, blocked segments, disconnected graph cases and tie-breaking.

#### Acceptance gate for review

- Routing is deterministic for the same inputs, model version and parameters.

- Every route response lists the risk values and parameters used and explains why a path or advisory was chosen.

- The evaluation compares risk-aware and distance-only routes with the sample counts stated.

**Review evidence to attach in Plane.** Routing module, API endpoint, parameter note, evaluation against the baseline, edge-case tests, and example route explanations.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 13: GIS dashboard visualisation

**Status: PLANNED** Plane Week 9 (COM71121-12).

**Weekly objective.** Give administrators a clear, trustworthy view of corridor risk and field reports.

#### Implementation work

- Build the web dashboard with a risk heat map by segment, hazard and horizon filters, and a legend stating model version and data time.

- Display field-report markers with photo, status (unverified, verified, rejected), and sync origin; support reviewer actions with an audit record.

- Create the administrative monitoring view for NH-44: report volume, sync health, data freshness, and open reviews, with denominators on every figure.

- Handle empty, loading, stale-data and error states, and ensure the layout works on desktop and tablet.

- Reconcile dashboard numbers against the database with automated tests.

#### Acceptance gate for review

- Dashboard values match the underlying filtered records.

- Selecting a segment or report shows its source, time, and model version.

- Stale or missing predictions are visibly marked, not shown as low risk.

**Review evidence to attach in Plane.** Dashboard build, screenshots using demo data, reconciliation tests, accessibility check, and reviewer-action audit sample.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 14: Full-system integration, end-to-end testing and security hardening

**Status: PLANNED** Plane Week 10 (COM71121-13).

**Weekly objective.** Prove the whole chain works together and harden it, then decide on any gated extension.

#### Implementation work

- Test the full flow from offline report capture to dashboard update, and verify that model predictions correctly influence routing suggestions.

- Stress the synchronisation queue under simulated network failure with large backlogs and concurrent devices.

- Perform a threat review covering authentication, authorisation, upload handling, file access, injection, dependency exposure, logging and data retention; fix high-risk items and run a dependency scan.

- Add rate limits, secure headers, safe image decoding, strict file limits, and verify users cannot read other users’ reports or photos by changing an identifier.

- Extension gate: only if Weeks 1–13 gates pass, prototype coverage beyond the pilot corridor or an additional hazard. Otherwise record a written deferral decision.

#### Acceptance gate for review

- The end-to-end scenario passes repeatably from a clean environment.

- Security checklist has evidence for each control, and high-risk findings are resolved.

- Any extension is labelled experimental and cannot affect the core results.

**Review evidence to attach in Plane.** End-to-end test report, stress-test results, threat review, access-control tests, dependency scan, and the extension decision note.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 15: System validation and performance benchmarking

**Status: PLANNED** Plane Week 11 (COM71121-14).

**Weekly objective.** Measure the platform with a defensible protocol and report limitations honestly.

#### Implementation work

- Measure latency for synchronisation, prediction inference (or lookup of pre-computed risk), and route computation, reporting hardware, payload size, median and tail percentiles.

- Validate prediction quality retrospectively against historical events and, where available, recent field reports, with sample counts and the caveat that field-report volume is small.

- Run ablations where feasible (for example without terrain, weather or graph structure) and compare against baselines. Avoid unsupported superiority claims.

- Run a short usability test with representative users on the app and dashboard (task completion, time, observed errors), describing participants and limitations.

- Fix defects and refine the UI based on findings, and re-run regression tests.

#### Acceptance gate for review

- Evaluation is reproducible from scripts and configuration and does not tune on the held-out test period.

- False negatives (missed disruptions) and uncertainty failures receive explicit analysis.

- Usability results state sample size and avoid overstating generalisation.

**Review evidence to attach in Plane.** Evaluation protocol, metrics tables and plots, latency report, ablation notes, error analysis, usability notes, and regression results.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

### Week 16: Deployment, documentation and demonstration

**Status: PLANNED** Plane Week 12 (COM71121-15).

**Weekly objective.** Deliver a reproducible, understandable prototype and a clear technical demonstration.

#### Implementation work

- Containerise the API, database, worker and dashboard with health checks, migrations, a sample environment file and one-command local setup; run a clean deployment rehearsal.

- Complete the README, user guide, architecture and API documentation, data and label documentation, model card, evaluation report, limitations, setup and troubleshooting.

- Document the ST-GNN architecture and the synchronisation protocol, and prepare the final project report and technical manual.

- Prepare a demonstration with a complete flow (offline report, sync, dashboard, risk-aware route) and at least two failure cases (connection loss during sync and stale or missing risk data).

- Prepare the final presentation (problem, objectives, architecture, technical depth, innovation, results, failure analysis, societal impact, limitations, future work) and a demonstration video.

#### Acceptance gate for review

- A reviewer can start the application from documented instructions and repeat the demonstration.

- The demo shows data-to-decision traceability and responsible handling of uncertain or stale data.

- All final Plane issues are updated with status, artifacts and known limitations.

**Review evidence to attach in Plane.** Containerised release candidate, tagged repository version, documentation set, reproducible demo script, final evaluation, presentation and video.

*Review question: Can the team demonstrate the acceptance gate using the current build, tests, data, or a traceable design artifact?*

## 8. Evaluation definitions and reporting discipline

Use the following definitions consistently. Report the evaluation population and denominators beside every metric, and keep prediction quality separate from routing and synchronisation quality.

| **Area**              | **Measures**                                                                     | **Reporting requirement**                                                                                           |
|-----------------------|----------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| Disruption prediction | Precision, recall, F1 and precision–recall AUC per hazard and horizon            | Chronological held-out test period; positive-event counts; comparison with baselines; no tuning on the test period. |
| Calibration           | Brier score, reliability curve                                                   | State the bins and thresholds; show whether higher scores really correspond to higher event rates.                  |
| Missed disruptions    | Recall and false-negative rate on verified events                                | Define matching between predicted and observed events (segment, time window); analyse each miss.                    |
| Routing               | Risk exposure reduction, added distance/time, share of cases with no alternative | Compare with a distance-only baseline on the same historical periods; state sample counts.                          |
| Synchronisation       | Delivery success rate, duplicate rate, loss count, time to convergence           | Report under simulated failures (drops, clock skew, out-of-order, concurrent devices) with the number of trials.    |
| Efficiency            | Latency for sync, inference or lookup, and routing                               | Report hardware, payload size, median and tail percentile.                                                          |
| Data quality          | Share of events geocoded and snapped, snap distance, weather coverage            | Report excluded records and the handling of missing data.                                                           |
| Usability             | Task completion, time, observed errors, brief feedback                           | Describe participants, tasks and devices; do not generalise from a very small sample.                               |

## 9. Innovation, trend alignment and societal value

- **Disruption-aware routing.** Routes are chosen on predicted safety and not just distance, using a graph model of the corridor.

- **Spatio-temporal learning on a real road graph.** The ST-GNN captures how risk spreads across connected segments and over time, using terrain and weather features.

- **Edge resilience.** The offline-first design lets the system keep collecting evidence where connectivity is poor, and synchronise safely afterwards with idempotent, conflict-aware logic.

- **Trustworthy decision support.** Predictions carry model version, horizon and data age; stale or missing data is shown as such, and field reports remain unverified until reviewed.

- **Societal and industrial impact.** A validated tool could help travellers, logistics operators and administrators plan around landslide, snow and shooting-stone disruption on a critical highway. These are potential contributions to be evaluated, not guaranteed outcomes.

## 10. Project-wide review gates and risk controls

- **Data gate (Weeks 1–4, close-out):** sources, dates, label provenance, geocoding and snapping tolerances, and the chronological split are documented before any performance claim is made.

- **Model gate (Weeks 5–7):** results come from a held-out period, include rare-event metrics and baselines, and are reproducible from scripts; the model card states limitations.

- **Sync gate (Weeks 9–11):** no report is lost or duplicated under simulated failures; conflicts keep the original reports.

- **Safety gate (Week 12):** stale, missing or low-confidence risk data can never produce a silent “safe” route; the advisory output is used when no alternative exists.

- **Security gate (Week 14):** authorisation, upload handling and data retention are reviewed, and high-risk findings are fixed.

- **Extension gate (Week 14):** wider-corridor or extra-hazard work is postponed if the core flow or evaluation is incomplete.

- **Release gate (Week 16):** clean setup, permissions, sync flow, results, known limitations and a reproducible demonstration are reviewed.

### Key risks and mitigations

| **Risk**                                      | **Why it matters**                                                        | **Mitigation**                                                                                 |
|-----------------------------------------------|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| Few historical events (rare labels)           | Metrics can look good while missing real disruptions; models can overfit. | Report per-class counts, use PR-AUC and recall, compare with baselines, and state uncertainty. |
| Geocoding and snapping errors in labels       | Events attached to the wrong segment corrupt training and evaluation.     | Label-provenance register, snap-distance limits, manual review of flagged rows.                |
| Few alternate roads on the pilot stretch      | Risk-aware routing may often have no alternative.                         | Support delay/hold advisories and report the “no alternative” share honestly.                  |
| Small volume of real field reports            | Validation against field data is statistically weak.                      | Use retrospective backtesting plus synthetic demo reports clearly labelled, and state limits.  |
| Time pressure in the last weeks               | Integration and documentation can be squeezed.                            | Freeze scope after Week 11, keep stretch work gated, and keep a weekly demo.                   |
| Large artifacts and secrets in the repository | Slow clones, leaked credentials.                                          | Use git-ignore, Git LFS or external storage for checkpoints, and a secrets scan in CI.         |

## 11. Definition of done for every Plane issue

- The issue links to the relevant objective and week and states its user-visible or technical outcome.

- Acceptance criteria are checked off with an attached screenshot, test output, data sample, design artifact, or short demo recording as appropriate.

- Code is committed in a traceable branch and commit, reviewed by another student, and does not contain secrets or unexplained generated files.

- Automated tests pass for the changed behaviour and at least one relevant failure path; known gaps are stated.

- Documentation, API or schema and screenshots are updated if behaviour changed.

- The Plane state matches reality (no finished work left in Backlog or Todo).

- The team can explain the implementation, dependencies, assumptions and limitations during review.

## 12. Student handoff prompt for Antigravity

Use the following prompt, then append the specific Plane issue and current task context:

> *“You are assisting us with RouteWise, an edge-resilient GeoAI and predictive logistics platform that forecasts road-segment disruption risk (landslide, snow, shooting stone) on the Ramban–Banihal pilot corridor of NH-44 and supports offline-first field reporting and risk-aware routing. Follow the attached Detailed 16-Week Development Plan and the linked Plane issue. Weeks 1 to 6 are already complete; do not change existing datasets, stgnn_best.pt or routewise_local.db without our approval. First inspect the repository and report its current structure, working features, tests and relevant constraints. Do not make changes until you provide a concise implementation proposal naming the files and modules to change, data and API impacts, risks and tests. Preserve the MVP scope. Treat predictions as advisory risk estimates, always carry model version and data timestamp, and never convert stale, missing or low-confidence data into a ‘safe’ result. Keep offline-first behaviour and idempotent synchronisation. After approval by the student team, implement only this issue in small steps, add tests for success and failure paths, run relevant checks, and report changed files, commands and results, limitations, and manual verification. Do not add credentials, broaden scope, or claim accuracy beyond what we have measured on the held-out data.”*
