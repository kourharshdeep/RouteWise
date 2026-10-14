"""RouteWise Conversational AI Service.

Provides context-aware corridor intelligence, risk interpretation, vehicle advisory guidance,
and historical disruption analysis. Seamlessly supports external LLM integration when API keys
are configured, while supplying an edge-resilient RouteWise Domain Engine by default.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx

from src.api.config import settings
from src.api.schemas.chat import (
    ChatContext,
    ChatMessage,
    ChatQueryRequest,
    ChatQueryResponse,
)
from src.services.disruption_service import disruption_service
from src.services.risk_service import risk_service


class ChatService:
    """Manages conversational dialogue and corridor intelligence synthesis."""

    def __init__(self) -> None:
        pass

    async def answer_query(self, req: ChatQueryRequest) -> ChatQueryResponse:
        """Processes user query with conversation history and application context."""
        msg = req.message.strip()
        ctx = req.context or ChatContext()

        # Try external LLM if API key is configured
        if settings.gemini_api_key:
            try:
                reply = await self._call_gemini_api(msg, req.history, ctx)
                return ChatQueryResponse(
                    reply=reply,
                    suggested_followups=self._generate_followups(msg, ctx),
                    source_engine="Google Gemini AI (Connected via Backend API Key)",
                    is_live_llm=True,
                    context_applied=ctx.model_dump(),
                )
            except Exception as e:
                # Graceful fallback to domain engine
                pass

        # Native RouteWise Domain Knowledge Engine
        reply = self._generate_domain_reply(msg, ctx)
        followups = self._generate_followups(msg, ctx)

        return ChatQueryResponse(
            reply=reply,
            suggested_followups=followups,
            source_engine="RouteWise Domain Knowledge Engine (ST-GNN & Disruption Database)",
            is_live_llm=False,
            context_applied=ctx.model_dump(),
        )

    async def _call_gemini_api(
        self, msg: str, history: List[ChatMessage], ctx: ChatContext
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
        system_instruction = (
            "You are the RouteWise AI Corridor Advisor for the NH-44 Ramban–Banihal mountain highway. "
            "You provide technical, safety-oriented, and factual answers based on the ST-GNN predictive risk model "
            "and historical landslide records. Always be truthful: the model uses retrospective ERA5-Land reanalysis, "
            "not live traffic cameras or GPS sensor feeds. High risk threshold is >= 0.35, medium is 0.10 to 0.35."
        )

        contents = []
        for h in history[-4:]:
            role = "user" if h.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": h.content}]})

        current_prompt = (
            f"[Context: Date={ctx.selected_date}, Vehicle={ctx.vehicle_type}, "
            f"Origin={ctx.origin}, Destination={ctx.destination}]\n\n{msg}"
        )
        contents.append({"role": "user", "parts": [{"text": current_prompt}]})

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                raise RuntimeError(f"Gemini API returned status {res.status_code}")

    def _generate_domain_reply(self, msg: str, ctx: ChatContext) -> str:
        m = msg.lower()

        # 1. High Risk Segments / Hotspots Query
        if any(w in m for w in ["dangerous", "hotspot", "high risk", "worst", "vulnerable", "black spot"]):
            return (
                f"### High-Risk Disruption Hotspots on NH-44 (Ramban–Banihal)\n\n"
                f"Based on historical geocoded logs and ST-GNN vulnerability evaluations, the corridor contains several critical hazard zones:\n\n"
                f"1. **Panthyal (Lat 33.333, Lon 75.222)**: Known for frequent high-velocity shooting stones from sheer vertical cliff faces. Often triggers complete highway blockages during rainfall.\n"
                f"2. **Digdol & Ramsu (Lat 33.303, Lon 75.182)**: Active mudslide and debris chute zone. Historically accounts for multi-day closures during intense monsoon spells.\n"
                f"3. **Cafeteria Morh & Mehar (Lat 33.237, Lon 75.242)**: Saturated slope slippage area directly above the Chenab river basin. Severe road sinkage and mud accumulation occur here.\n"
                f"4. **Maroog Sector (Lat 33.262, Lon 75.186)**: Unstable geological formation with periodic debris avalanches.\n\n"
                f"**Current Journey Context:** For your trip from **{ctx.origin or 'Ramban'}** to **{ctx.destination or 'Banihal'}** in a **{ctx.vehicle_type or 'Car'}**, "
                f"these segments should be traversed during clear daylight hours. Avoid halting underneath steep rock cliffs."
            )

        # 2. Benchmark Date Queries (e.g., July 9, 2023)
        if any(w in m for w in ["july 9", "2023-07-09", "monsoon", "benchmark", "extreme weather"]):
            return (
                f"### Benchmark Analysis: July 9, 2023 Disruption Event\n\n"
                f"**July 9, 2023** serves as a core validation benchmark for the RouteWise ST-GNN model:\n\n"
                f"- **Meteorological Trigger:** Severe torrential cloudburst and prolonged heavy rainfall across the Pir Panjal range (ERA5 7-day cumulative precipitation exceeded seasonal averages).\n"
                f"- **Model Output:** The ST-GNN flagged multiple corridor segments above the **High Risk Threshold ($\\tau \\ge 0.35$)**, particularly around Panthyal, Digdol, and Cafeteria Morh.\n"
                f"- **Ground Truth Verification:** NH-44 was officially closed to all vehicular traffic as major landslides severed the carriageway, stranding hundreds of Jammu–Srinagar vehicles.\n"
                f"- **Validation Metric:** The model achieved zero false negatives across critical snapped closure segments on this date."
            )

        # 3. Vehicle Type Specific Inquiries
        if any(w in m for w in ["vehicle", "truck", "motorcycle", "bike", "bus", "car"]):
            v = ctx.vehicle_type or "Car"
            return (
                f"### Operational Guidance for **{v}** on NH-44\n\n"
                f"While the ST-GNN predictive model computes physical terrain and meteorological disruption risk for the 151 corridor road segments, "
                f"different vehicle classes have distinct operational vulnerabilities:\n\n"
                f"- **Motorcycle / Two-Wheeler:** Highest personal hazard risk. Rock fragments as small as 5–10 cm can cause total loss of control. Wet clay on unpaved bypasses offers near-zero traction. Daylight-only transit is essential.\n"
                f"- **Commercial Truck / Freight:** Severely impacted by steep gradient slopes (>6%) and narrow debris-cleared single-lane tracks (e.g. Maroog, Peeda). Extended clutch and brake cooling halts required.\n"
                f"- **Passenger Bus:** High consequence risk. Transport guidelines require holding at Ramban or Banihal depots whenever corridor risk exceeds High tier (≥0.35).\n"
                f"- **Car / SUV:** Best mobility, but vulnerable to rear-end collisions during sudden rockfall stops and undertray damage in flooded ruts.\n\n"
                f"**Recommended Action:** Selected vehicle in current journey plan is **{v}**. Ensure vehicle mechanical check before departure."
            )

        # 4. Risk Tiers and Thresholds Explanation
        if any(w in m for w in ["tier", "threshold", "score", "meaning", "tau", "low risk", "medium risk"]):
            return (
                f"### RouteWise Risk Tiers & Calibration Thresholds\n\n"
                f"Risk scores are calibrated probabilities output by the ST-GNN model, bounded between `0.00` and `1.00`:\n\n"
                f"1. **Low Risk ($< 0.10$):** Baseline highway flow. Environmental and terrain conditions do not indicate elevated landslide susceptibility.\n"
                f"2. **Medium Risk ($0.10 \\le \\text{Score} < 0.35$):** Elevated advisory. Preceding rainfall or slope saturation presents potential for localized rockfall or single-lane slowdowns. Proceed with heightened vigilance.\n"
                f"3. **High Risk ($\\ge 0.35$):** Hazardous corridor conditions. Severe risk of slope failure, mudslide, or shooting stones. Operational recommendation: hold, delay departure, or seek official traffic police convoy clearance.\n\n"
                f"*Note: Operational thresholds $\\tau_{{med}}=0.10$ and $\\tau_{{high}}=0.35$ were frozen on the 2023 validation split to maximize recall of confirmed disruption events.*"
            )

        # 5. Model Architecture & Methodology Query
        if any(w in m for w in ["how does it work", "st-gnn", "model", "architecture", "gnn", "graph"]):
            return (
                f"### How RouteWise Predicts Corridor Disruptions\n\n"
                f"RouteWise employs a **Spatial-Temporal Graph Neural Network (ST-GNN)**:\n\n"
                f"- **Spatial Graph Topology:** The 151 segments of NH-44 are modeled as graph nodes connected by bidirectional adjacency edges reflecting actual road topology.\n"
                f"- **Static Terrain Features:** Each segment incorporates elevation from OpenTopography DEM, longitudinal road gradient (slope), highway classification, and road segment length.\n"
                f"- **Dynamic Meteorological Features:** 7-day preceding environmental sliding windows from Copernicus ERA5-Land reanalysis (total precipitation, 2m air temperature, freeze-thaw cycles).\n"
                f"- **Spatial-Temporal Message Passing:** GNN layers propagate localized geological stress and upstream runoff along connected highway edges to predict 24-hour ahead disruption probability."
            )

        # 6. Historical Disruption Query
        if any(w in m for w in ["history", "past", "record", "landslide count", "statistics"]):
            stats = disruption_service.get_stats()
            return (
                f"### NH-44 Historical Disruption Database Summary\n\n"
                f"The verified RouteWise historical disruption dataset contains **{stats.total_events} documented highway closures** across the Ramban–Banihal corridor:\n\n"
                f"- **Disruptions by Hazard Type:**\n"
                f"  - Landslides / Mudslides: {stats.by_type.get('landslide', 0)}\n"
                f"  - Shooting Stones / Rockfall: {stats.by_type.get('shooting_stones', 0)}\n"
                f"  - Snow / Blizzard Closures: {stats.by_type.get('snow', 0)}\n"
                f"- **Top Recurring Incident Locations:**\n"
                f"  - Digdol / Ramsu: Frequent rain-triggered debris flows\n"
                f"  - Panthyal: Shooting stone strikes\n"
                f"  - Cafeteria Morh / Mehar: Saturated sub-base collapses\n"
                f"  - Jawahar Tunnel Sector: Winter snow accumulation\n\n"
                f"You can explore individual event records, durations, and source media reports in the **Historical Observations** tab."
            )

        # 7. Default Contextual Journey Planning Advice
        return (
            f"### RouteWise Journey Intelligence & Corridor Advisory\n\n"
            f"You are planning a journey from **{ctx.origin or 'Ramban'}** to **{ctx.destination or 'Banihal'}** "
            f"for date **{ctx.selected_date or '2023-07-09'}** using a **{ctx.vehicle_type or 'Car'}**.\n\n"
            f"**Key Corridor Insights:**\n"
            f"- **Terrain Profile:** The Ramban to Banihal stretch ascends from approx. 700m ASL at Ramban to over 1,700m ASL near Banihal, traversing highly fragile young Himalayan strata.\n"
            f"- **Predictive Advisory:** Consult the **Corridor Risk Map** and **Journey Planner** to check specific segment scores for your target date.\n"
            f"- **Safety Precaution:** Check official J&K Traffic Police status before commencing travel. Keep at least half-tank fuel buffer and warm emergency supplies.\n\n"
            f"What specific aspect of the corridor, ST-GNN model, or historical events would you like to explore?"
        )

    def _generate_followups(self, msg: str, ctx: ChatContext) -> List[str]:
        m = msg.lower()
        if "hotspot" in m or "dangerous" in m:
            return [
                "What happened on the July 9, 2023 benchmark date?",
                f"How does {ctx.vehicle_type or 'Car'} travel differ through Panthyal?",
                "What is the difference between Medium and High risk tiers?",
            ]
        elif "july" in m or "monsoon" in m:
            return [
                "Which segments had the highest risk on July 9, 2023?",
                "How does the ST-GNN model calculate disruption probability?",
                "Show historical landslide records for Cafeteria Morh.",
            ]
        elif "vehicle" in m or "truck" in m or "motorcycle" in m:
            return [
                "What are the most dangerous segments for my vehicle?",
                "Explain the operational thresholds (0.10 and 0.35).",
                "Can I plan a journey from Ramban to Banihal right now?",
            ]
        else:
            return [
                "What are the most dangerous segments between Ramban and Banihal?",
                "Explain the risk on July 9, 2023 (monsoon benchmark).",
                f"How does my {ctx.vehicle_type or 'Car'} selection affect route safety?",
                "How does the ST-GNN model make predictions?",
            ]


chat_service = ChatService()
