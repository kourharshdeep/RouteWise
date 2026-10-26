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

