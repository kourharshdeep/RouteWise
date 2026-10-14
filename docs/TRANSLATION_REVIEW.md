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
