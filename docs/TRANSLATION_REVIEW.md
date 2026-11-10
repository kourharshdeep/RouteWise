# RouteWise Translation Review & Localization Notes

**Date:** 2026-10-14  
**Supported Locales:** English (`en`), Hindi (`hi`)  
**Status:** Operational Demonstration / Prototype Localization

---

## 1. Professional Translation Disclaimer
> [!IMPORTANT]
> The Hindi translations provided in `frontend/src/i18n/locales/hi.json` were generated using domain-informed technical term mapping and machine-assisted translation. They **have not yet been formally reviewed or certified by a native Hindi-speaking professional linguist** or official transport safety authority.

## 2. Terminology Concordance
| English Technical Term | Hindi Localization | Context & Notes |
| :--- | :--- | :--- |
| **Landslide** | भूस्खलन (Landslide) | Standard NHAI / IMD geophysical term. |
| **Shooting Stones** | पत्थर गिरना (Shooting Stones) | Common local term along Cafeteria Morh & Panthyal. |
| **Waterlogging / Flooding** | जलभराव / बाढ़ | Culvert overflow and drainage blockage. |
| **Road Surface Damage** | सड़क सतह क्षति | Potholes, subsidence, and asphalt erosion. |
| **Single Lane / Obstruction** | एकल लेन / अवरोध | Breakdown or partial blockage requiring marshaling. |
| **Snow / Icy Surface** | बर्फबारी / फिसलन | High altitude winter conditions near Banihal. |
| **Low Risk** | कम जोखिम | Advisory tier (< 0.10). |
| **Medium Risk** | मध्यम जोखिम | Advisory tier (0.10 - 0.35). |
| **High Risk** | उच्च जोखिम | Advisory tier (≥ 0.35). |
| **Submitted** | दर्ज | Initial incident creation. |
| **Verified** | सत्यापित | Patrol officer or TCU confirmation. |
| **Assigned** | सौंपा गया | Dispatch to dedicated patrol officer. |
| **Resolved** | हल किया गया | Clearance complete, normal traffic restored. |
| **Rejected** | अस्वीकृत | Unsubstantiated or spurious report. |

---

## 3. Scope of Alert Delivery
- **In-App Display Only:** All advisory alerts and state notifications are delivered purely within the web application interface (Corridor Strip, Risk Detail Drawer, Overview banners, and Patrol Dashboard).
- **No SMS or Push Notifications:** RouteWise does NOT integrate with SMS gateways, push notification daemons, or cellular broadcast systems. No claims of cellular dispatch are made.

---

## 4. Layout & Typography Safeguards
- Hindi Devanagari text typically requires 15% to 25% more horizontal width than Latin characters.
- Font stack fallback includes `'Noto Sans Devanagari'`, `'Mukta'`, and system Indic typography.
- UI components use flexible wrapping and minimum heights to avoid text truncation.

---

## 5. Unreviewed Additions (Hardening Pass 1)
The following strings were added for Journey Planner correctness and incomplete hazard awareness, and are marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| `journey.unknown_segments_count` | `{{count}} Unknown` | `{{count}} अज्ञात` | Displays count of unmonitored segments |
| `journey.incomplete_data_title` | `Incomplete Hazard Assessment Notice` | `अपूर्ण जोखिम मूल्यांकन सूचना` | Alert banner header |
| `journey.incomplete_data_notice` | `{{count}} segment(s) on this route lack precomputed ST-GNN risk evaluations. Because missing data is never certified as safe, the overall route risk is designated as Unknown.` | `इस मार्ग के {{count}} खंडों में पूर्व-परिकलित ST-GNN जोखिम मूल्यांकन उपलब्ध नहीं है। चूँकि अनुपलब्ध डेटा को कभी सुरक्षित प्रमाणित नहीं माना जाता, इसलिए समग्र मार्ग जोखिम को अज्ञात के रूप में निर्दिष्ट किया गया है।` | Retains truthful scientific semantics |
| `journey.assumed_speed_label` | `Estimated Transit Time (Assumed Speed)` | `अनुमानित पारगमन समय (कल्पित गति)` | Clarifies that transit duration is modeled, not telemetry |
| `journey.date_out_of_range` | `Observation date is outside the supported historical window ({{minDate}} to {{maxDate}}).` | `अवलोकन तिथि समर्थित ऐतिहासिक सीमा ({{minDate}} से {{maxDate}}) से बाहर है।` | Date bounds error message |

---

## 6. Unreviewed Additions (Step 5 - Live Intelligence)
The following strings were added for the Real-Time Intelligence dashboard, Server-Sent Events status indicators, distribution shift disclosures, and operational status representations, and are marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| `live.toggle_label` | `Operational Mode` | `परिचालन मोड` | Switch between Historical and Live |
| `live.historical_mode` | `Historical Reanalysis` | `ऐतिहासिक विश्लेषण` | Default mode label |
| `live.live_mode` | `Live Intelligence` | `लाइव इंटेलिजेंस` | Real-time streaming mode label |
| `live.experimental_badge` | `Live data - Experimental - not validated` | `लाइव डेटा - प्रायोगिक - अप्रमाणित` | Mandatory distribution shift badge |
| `live.experimental_notice` | `Live meteorological observations from Open-Meteo represent an unvalidated distribution shift from the ERA5-Land training dataset. Predictions are advisory relative-risk indices, not statistical disruption probabilities.` | `ओपन-मेटियो से लाइव मौसम संबंधी अवलोकन ERA5-लैंड प्रशिक्षण डेटासेट से एक अप्रमाणित वितरण बदलाव का प्रतिनिधित्व करते हैं। भविष्यवाणियां सलाहकारी सापेक्ष-जोखिम सूचकांक हैं, सांख्यिकीय व्यवधान संभावनाएं नहीं।` | Honest framing disclosure |
| `live.last_updated` | `Last updated` | `अंतिम अद्यतन` | Telemetry timestamp label |
| `live.data_age` | `Data age` | `डेटा आयु` | Hours elapsed since fetch |
| `live.data_stale` | `Stale Data (>24h)` | `बासी डेटा (>24 घंटे)` | Amber stale indicator |
| `live.connection_connected` | `Connected (Real-time Stream)` | `जुड़ा हुआ (रीयल-टाइम स्ट्रीम)` | SSE status indicator |
| `live.connection_lost` | `Connection Lost - Polling Every 60s` | `कनेक्शन टूट गया - प्रत्येक 60 सेकंड में पुनः जांच जारी` | SSE disconnect fallback |
| `live.unknown_segments` | `Unknown / Stale Telemetry` | `अज्ञात / बासी टेलीमेट्री` | Segment missing data label |
| `live.operational_status` | `Operational Status` | `परिचालन स्थिति` | Derived operational status |
| `live.status_open` | `Open` | `खुला` | Road passability status |
| `live.status_caution` | `Caution` | `सावधानी` | Elevated risk advisory |
| `live.status_restricted` | `Restricted` | `प्रतिबंधित` | Single-lane or hazard restriction |
| `live.status_closed` | `Closed` | `बंद` | Complete closure |
| `live.status_unknown` | `Unknown` | `अज्ञात` | Missing telemetry safe-fallback |
| `live.simulated_events` | `Active Simulated Events` | `सक्रिय सिमुलेटेड घटनाएं` | Operator simulation overlay count |
| `live.verified_events` | `Active Verified Hazards` | `सक्रिय सत्यापित खतरे` | Verified patrol incident count |
| `live.refresh_now` | `Refresh Live Telemetry` | `लाइव टेलीमेट्री रीफ़्रेश करें` | Manual trigger button |

---

## 7. Unreviewed Additions (Step 6 - Dynamic Route Recalculation)
The following strings were added for dynamic route recalculation, operational journey recommendations, side-by-side alternative comparison, and single-corridor honesty disclosures, and are marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| `routing.recommendation_hold` | `HOLD` | `रुकें (HOLD)` | Route impassable due to closed segment |
| `routing.recommendation_no_data` | `NO DATA` | `डेटा उपलब्ध नहीं (NO DATA)` | Missing or stale telemetry |
| `routing.recommendation_delay` | `DELAY` | `विलंब (DELAY)` | High risk conditions |
| `routing.recommendation_proceed_caution` | `PROCEED WITH CAUTION` | `सावधानीपूर्वक आगे बढ़ें (PROCEED WITH CAUTION)` | Medium hazard conditions |
| `routing.recommendation_proceed` | `PROCEED` | `आगे बढ़ें (PROCEED)` | Low hazard baseline conditions |
| `routing.route_updated` | `Route updated at {time} - {reason}` | `मार्ग अद्यतन {time} पर - {reason}` | Real-time SSE recomputation alert |
| `routing.baseline_route` | `Distance-Only Baseline` | `दूरी-आधारित आधार रेखा` | Shortest path alternative |
| `routing.risk_aware_route` | `Risk-Aware Route` | `जोखिम-सजग मार्ग` | Multi-objective router result |
| `routing.single_corridor_notice` | `Single physical corridor: No alternative bypass exists on NH-44 Ramban–Banihal.` | `एकल भौतिक गलियारा: NH-44 रामबन-बनिहाल पर कोई वैकल्पिक बाईपास मौजूद नहीं है।` | Corridor topology truth disclosure |
| `routing.passable` | `Passable` | `मार्ग खुला` | Segment clear for transit |
| `routing.impassable` | `Impassable / Hold` | `अवरुद्ध / रुकें` | Segment blocked by hazard |
| `routing.compare_previous` | `Compare with Previous Route Calculation` | `पिछले मार्ग परिकलन से तुलना करें` | Dynamic route change comparison |

---

## 8. Unreviewed Additions (Step 7 - Alerts and Real-Time Monitoring)
The following strings were added for the in-app corridor alerts drawer, lifecycle state tracking, acknowledgement controls, and demo multi-day storm scenario player, and are marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| `alerts.title` | `Corridor Alerts` | `गलियारा अलर्ट` | Alert drawer title |
| `alerts.active_alerts` | `Active Alerts` | `सक्रिय अलर्ट` | Active counter badge |
| `alerts.no_alerts` | `No active corridor disruption alerts` | `इस समय कोई सक्रिय व्यवधान अलर्ट नहीं है` | Empty state text |
| `alerts.in_app_notice` | `In-App Delivery Boundary: Delivered exclusively via web application interface.` | `इन-ऐप वितरण सीमा: विशेष रूप से वेब एप्लिकेशन इंटरफ़ेस के माध्यम से वितरित।` | In-app only boundary notice |
| `alerts.acknowledge` | `Acknowledge` | `स्वीकार करें` | Patrol officer acknowledgement action |
| `alerts.clear` | `Clear Alert` | `अलर्ट हटाएं` | Manual clear action |
| `alerts.acknowledged` | `Acknowledged` | `स्वीकृत` | Status badge |
| `alerts.active` | `Active` | `सक्रिय` | Status badge |
| `alerts.simulated_tag` | `SIMULATED` | `सिम्युलेटेड` | Simulation badge |
| `alerts.scenario_title` | `Multi-Day Storm Scenario` | `बहु-दिवसीय तूफान परिदृश्य` | Demo scenario player header |
| `alerts.advance_phase` | `Advance Storm Phase` | `तूफान चरण आगे बढ़ाएं` | Scenario step button |
| `alerts.reset_baseline` | `Reset to Baseline` | `आधार रेखा पर रीसेट करें` | Scenario reset button |

---

## 9. Unreviewed Additions (Task 2d - Stale Alert Metadata)
The following string was added for model-derived alerts when live telemetry exceeds staleness thresholds, and is explicitly marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| `alerts.lastKnownDataStale` | `Last known, data stale` | `अंतिम ज्ञात स्थिति, डेटा पुराना है` | Stale risk context indicator for model-derived alerts (Unreviewed) |

---

## 10. Unreviewed Additions (Task 3 - Current-Date Live Risk Experience)
The following strings were added for the current-date live risk experience, operational mode separation, replay labeling, and weather window indicator, and are explicitly marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| `live.replay_mode` | `REPLAY / simulated scenario` | `रीप्ले / सिम्युलेटेड परिदृश्य` | Operational banner tag for demonstration replay mode |
| `live.mode_off_notice` | `Live mode not enabled (ROUTEWISE_LIVE_MODE is 'off')` | `लाइव मोड सक्षम नहीं है (ROUTEWISE_LIVE_MODE 'off' है)` | Advisory when live ingestion is configured off |
| `live.weather_window_end` | `Weather data window through` | `मौसम डेटा विंडो समाप्ति` | Label for last complete meteorological observation day |
| `live.source_label` | `Source` | `स्रोत` | Label for atmospheric telemetry data provider |

---

## 11. Unreviewed Additions (Task 3a - Accessible Non-Color Cues & Aria Labels)
The following strings were added for corridor segment accessibility non-color cues and screen reader telemetry labels, and are explicitly marked as **Unreviewed**:

| Key | English String | Hindi Localization (Unreviewed) | Notes |
| :--- | :--- | :--- | :--- |
| live.aria_stale_telemetry | Stale Telemetry (>24h) | पुराना टेलीमेट्री डेटा (>24 घंटे) | Accessibility label for stale segment telemetry |
| live.aria_unknown_telemetry | Unknown / Missing Telemetry | अज्ञात / अनुपलब्ध टेलीमेट्री | Accessibility label for missing or neighbour-missing segment data |
| live.aria_high_hazard | High Hazard (≥0.35) | उच्च जोखिम (≥0.35) | Accessibility label for high hazard segment |
| live.aria_elevated_hazard | Elevated Hazard (0.10–0.35) | मध्यम जोखिम (0.10–0.35) | Accessibility label for medium hazard segment |
| live.aria_baseline_hazard | Baseline Hazard (<0.10) | आधार रेखा जोखिम (<0.10) | Accessibility label for low hazard segment |
