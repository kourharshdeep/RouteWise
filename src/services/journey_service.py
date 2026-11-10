"""Journey planning and corridor routing service.

Calculates route segments between corridor landmarks, fetches ST-GNN segment risk scores,
evaluates vehicle-specific travel times and vulnerability factors, and enforces
honest scientific semantics and dynamic routing across historical and live modes.
"""
from __future__ import annotations

import csv
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from src.api.config import settings
from src.api.schemas.journey import (
    JourneyPlace,
    JourneyPlanRequest,
    JourneyPlanResponse,
    RouteAlternative,
    SegmentItineraryItem,
    VehicleAdvisory,
)
from src.services.corridor_service import corridor_service
from src.services.risk_service import risk_service
from src.services.routing_engine import MultiObjectiveRouter

logger = logging.getLogger(__name__)

# Named modeling assumptions for travel time estimation (not measured live telemetry)
ASSUMED_HIGH_RISK_DELAY_MINUTES: int = 3
ASSUMED_MEDIUM_RISK_DELAY_MINUTES: int = 1
ASSUMED_VEHICLE_SPEEDS_KMH: Dict[str, float] = {
    "Motorcycle": 40.0,
    "Car": 45.0,
    "Bus": 32.0,
    "Truck": 26.0,
    "Other": 35.0,
}


class JourneyService:
    """Provides route planning, corridor pathfinding, and vehicle risk profiling."""

    def __init__(
        self,
        places_path: Path | None = None,
        graph_path: Path | None = None,
        sorted_segments_path: Path | None = None,
    ) -> None:
        self.places_path = places_path or settings.places_path
        self.graph_path = graph_path or settings.corridor_graph_path
        self.sorted_segments_path = sorted_segments_path or settings.sorted_segments_path
        self._places: List[JourneyPlace] = []
        self._sorted_segment_ids: List[str] = []
        self._places_by_id: Dict[str, JourneyPlace] = {}
        self._places_by_name: Dict[str, JourneyPlace] = {}
        self._place_to_sorted_idx: Dict[str, int] = {}
        self._features_by_id: Dict[str, Any] = {}
        self._segment_props: Dict[str, Any] = {}
        self._load_places()
        self._load_sorted_segments()
        self._init_static_lookups()

    def _init_static_lookups(self) -> None:
        """Precomputes immutable static maps for landmarks, segment properties, and indices."""
        for p in self._places:
            self._places_by_id[p.id.lower()] = p
            self._places_by_name[p.name.lower()] = p

        geojson = corridor_service.get_corridor_geojson()
        self._features_by_id = {f.id: f for f in geojson.features}
        self._segment_props = {f.id: f.properties for f in geojson.features if f.properties}

        if not self._sorted_segment_ids:
            self._sorted_segment_ids = [f.id for f in geojson.features]

        # Precompute nearest sorted segment index for each known landmark
        for p in self._places:
            self._place_to_sorted_idx[p.id] = self._find_nearest_sorted_segment_index(
                p.lat, p.lon, self._features_by_id
            )

    def reset_static_cache(self) -> None:
        """Resets and re-indexes static corridor geometry and landmarks (for tests)."""
        self._places.clear()
        self._sorted_segment_ids.clear()
        self._places_by_id.clear()
        self._places_by_name.clear()
        self._place_to_sorted_idx.clear()
        self._features_by_id.clear()
        self._segment_props.clear()
        corridor_service._geojson_cache = None
        self._load_places()
        self._load_sorted_segments()
        self._init_static_lookups()

    def _load_sorted_segments(self) -> None:
        """Loads monotonically chainage-ordered corridor segment IDs."""
        if not self.sorted_segments_path.exists():
            return
        with open(self.sorted_segments_path, "r", encoding="utf-8") as f:
            self._sorted_segment_ids = json.load(f)

    def _load_places(self) -> None:
        """Loads known landmarks from place_coordinates.csv."""
        if not self.places_path.exists():
            return

        name_map = {
            "ramban": "Ramban Gateway",
            "seri": "Seri",
            "maroog": "Maroog Sector",
            "cafeteria morh": "Cafeteria Morh",
            "digdol": "Digdol Rockfall Zone",
            "panth": "Panthyal High-Hazard Pass",
            "monkey morh": "Monkey Morh",
            "banihal": "Banihal Gateway",
            "meh": "Mehar Zone",
            "teli": "Teli Nallah",
            "chak narwah": "Chak Narwah",
            "jakh": "Jakheni / Banihal Approach",
            "dewal": "Dewal South Entry",
            "karool": "Karool Sector",
            "chamba": "Chamba",
            "riha": "Riha Border",
        }

        with open(self.places_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                kw = row.get("keyword", "").strip().lower()
                lat = float(row.get("lat", 0.0))
                lon = float(row.get("lon", 0.0))
                display_name = name_map.get(kw, kw.title())
                self._places.append(
                    JourneyPlace(
                        id=kw.replace(" ", "_"),
                        name=display_name,
                        lat=lat,
                        lon=lon,
                        description=f"NH-44 Landmark: {display_name} ({lat:.3f}°N, {lon:.3f}°E)",
                    )
                )

        # Sort places south to north by latitude
        self._places.sort(key=lambda p: p.lat)

    def get_corridor_places(self) -> List[JourneyPlace]:
        """Returns the list of selectable origin/destination points along the corridor."""
        return self._places

    def _find_nearest_sorted_segment_index(
        self, lat: float, lon: float, features_by_id: Dict[str, Any]
    ) -> int:
        best_idx = 0
        min_dist = float("inf")
        for i, sid in enumerate(self._sorted_segment_ids):
            feat = features_by_id.get(sid)
            if not feat or not feat.geometry or not feat.geometry.coordinates:
                continue
            coords = feat.geometry.coordinates
            mid_lon = (coords[0][0] + coords[-1][0]) / 2.0
            mid_lat = (coords[0][1] + coords[-1][1]) / 2.0
            dist = math.hypot(lat - mid_lat, lon - mid_lon)
            if dist < min_dist:
                min_dist = dist
                best_idx = i
        return best_idx

    def _build_vehicle_advisory(self, vehicle_type: str, max_slope: float) -> VehicleAdvisory:
        veh = vehicle_type.strip().capitalize()
        if veh == "Motorcycle":
            return VehicleAdvisory(
                vehicle_type="Motorcycle",
                speed_limit_kmh=40.0,
                vulnerability_level="Extreme",
                operational_clearance="High Caution",
                advisory_text=(
                    "Two-wheelers face acute exposure to loose gravel, falling rock fragments, and mud slicks. "
                    "Protective helmets, high-visibility rain gear, and daylight travel are strongly advised. "
                    "Avoid traveling through Panthyal or Digdol under active rainfall."
                ),
                model_applicability_note=(
                    "The ST-GNN model estimates geophysical corridor landslide probability based on rainfall and terrain. "
                    "It does not vary segment slope by vehicle type, but motorcycles carry the highest injury risk per incident."
                ),
            )
        elif veh == "Truck":
            return VehicleAdvisory(
                vehicle_type="Truck",
                speed_limit_kmh=26.0,
                vulnerability_level="High",
                operational_clearance="Restricted",
                advisory_text=(
                    f"Commercial freight trucks encounter high brake thermal wear and turning delays on steep gradients "
                    f"(maximum corridor slope: {max_slope:.1f}%). Heavy multi-axle trailers risk getting stranded on single-lane "
                    f"debris bypasses near Cafeteria Morh and Maroog. Verify axle clearance before transit."
                ),
                model_applicability_note=(
                    "The ST-GNN model evaluates slope, elevation, and 7-day cumulative precipitation. "
                    "Heavy freight vehicles have longer stopping distances on wet mountain inclines."
                ),
            )
        elif veh == "Bus":
            return VehicleAdvisory(
                vehicle_type="Bus",
                speed_limit_kmh=32.0,
                vulnerability_level="High",
                operational_clearance="Caution",
                advisory_text=(
                    "Public transit and passenger buses require strict safety compliance. "
                    "Hold at nearest designated staging yard (Ramban or Banihal) if corridor risk exceeds High tier (≥0.35). "
                    "Do not attempt night overtaking on blind curves."
                ),
                model_applicability_note=(
                    "The underlying ST-GNN model evaluates segment-level physical disruption. "
                    "Passenger transit routes follow conservative administrative safety protocols."
                ),
            )
        elif veh == "Other":
            return VehicleAdvisory(
                vehicle_type="Other / Emergency",
                speed_limit_kmh=35.0,
                vulnerability_level="Medium",
                operational_clearance="Standard / Emergency Protocol",
                advisory_text=(
                    "Special vehicle transit requires dedicated traffic police convoy clearance. "
                    "Maintain continuous two-way radio contact with Ramban and Banihal control rooms."
                ),
                model_applicability_note="Standard geophysical hazard rating applies.",
            )
        else:  # Default: Car
            return VehicleAdvisory(
                vehicle_type="Car",
                speed_limit_kmh=45.0,
                vulnerability_level="Standard",
                operational_clearance="Cleared with Standard Caution",
                advisory_text=(
                    "Light passenger vehicles maintain standard mountain clearance. "
                    "Keep safe following distances behind heavy trucks. Maintain headlight beams on dipped mode in fog and rain."
                ),
                model_applicability_note=(
                    "The ST-GNN disruption score reflects geophysical terrain hazard and weather triggers. "
                    "Light vehicles possess better acceleration and agility but remain vulnerable to direct rockfall."
                ),
            )

    def plan_journey(self, req: JourneyPlanRequest, now: Optional[datetime] = None) -> JourneyPlanResponse:
        """Plans a corridor journey with segment hazard profiling, vehicle advisories, and MultiObjectiveRouter."""
        # 1. Resolve Origin and Destination
        origin_clean = req.origin.strip().lower()
        dest_clean = req.destination.strip().lower()

        origin_p = self._places_by_id.get(origin_clean) or self._places_by_name.get(origin_clean)
        if not origin_p:
            origin_p = next(
                (p for p in self._places if p.id == origin_clean or p.name.lower() == origin_clean or origin_clean in p.name.lower()),
                None,
            )
        dest_p = self._places_by_id.get(dest_clean) or self._places_by_name.get(dest_clean)
        if not dest_p:
            dest_p = next(
                (p for p in self._places if p.id == dest_clean or p.name.lower() == dest_clean or dest_clean in p.name.lower()),
                None,
            )

        if not origin_p:
            origin_p = self._places[0] if self._places else JourneyPlace(
                id="ramban", name="Ramban", lat=33.253, lon=75.207, description="Southern Entry"
            )
        if not dest_p:
            dest_p = self._places[-1] if self._places else JourneyPlace(
                id="banihal", name="Banihal", lat=33.438, lon=75.191, description="Northern Entry"
            )

        if origin_p.id == dest_p.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Origin and Destination must be different corridor locations.",
            )

        # 2. Fetch corridor highway geometry and segment indices
        orig_idx = self._place_to_sorted_idx.get(origin_p.id)
        if orig_idx is None:
            orig_idx = self._find_nearest_sorted_segment_index(origin_p.lat, origin_p.lon, self._features_by_id)

        dest_idx = self._place_to_sorted_idx.get(dest_p.id)
        if dest_idx is None:
            dest_idx = self._find_nearest_sorted_segment_index(dest_p.lat, dest_p.lon, self._features_by_id)

        if (
            orig_idx is None
            or dest_idx is None
            or orig_idx >= len(self._sorted_segment_ids)
            or dest_idx >= len(self._sorted_segment_ids)
        ):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Data integrity error: Corridor segment index out of range "
                    f"(origin={orig_idx}, destination={dest_idx}, total_segments={len(self._sorted_segment_ids)})."
                ),
            )

        step = 1 if dest_idx >= orig_idx else -1
        selected_segment_ids = self._sorted_segment_ids[orig_idx : dest_idx + step : step]

        if not selected_segment_ids:
            selected_segment_ids = [self._sorted_segment_ids[orig_idx]]

        # 3. Resolve Mode (historical vs live)
        mode = (req.mode or "historical").lower().strip()
        if mode not in ("historical", "live"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid planning mode '{req.mode}'. Supported modes: 'historical', 'live'.",
            )

        risk_lookup: Dict[str, Any] = {}
        blocking_segments: List[str] = []
        is_live_stale = False
        journey_date_str = req.date

        if mode == "live":
            from src.services.live_risk_service import MAX_DATA_AGE_HOURS, live_risk_service

            live_risk = live_risk_service.get_latest_live_risk(as_of=req.date, eval_time=now)

            journey_date_str = req.date or live_risk.get("as_of") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

            for seg in live_risk.get("segments", []):
                risk_lookup[seg["segment_id"]] = seg

            effective_now = now or datetime.now(timezone.utc)
            comp_at_str = live_risk.get("computed_at")
            is_older_than_24h = False
            if not comp_at_str:
                is_older_than_24h = True
            else:
                try:
                    comp_dt = datetime.fromisoformat(comp_at_str.replace("Z", "+00:00"))
                    if (effective_now - comp_dt).total_seconds() > MAX_DATA_AGE_HOURS * 3600:
                        is_older_than_24h = True
                except Exception:
                    is_older_than_24h = True

            is_live_stale = (
                is_older_than_24h
                or any(seg.get("is_stale", False) for seg in live_risk.get("segments", []))
                or (live_risk.get("as_of") is None)
            )
        else:
            if not req.date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="date parameter is required in historical planning mode.",
                )
            risk_resp = risk_service.get_risk_by_date(req.date)
            journey_date_str = req.date
            for seg in risk_resp.segments:
                risk_lookup[seg.segment_id] = seg

        # 4. Build itinerary items
        itinerary: List[SegmentItineraryItem] = []
        total_dist_m = 0.0
        max_slope = 0.0
        scores: List[float] = []
        high_count = 0
        med_count = 0
        low_count = 0
        unknown_count = 0
        bottlenecks: List[str] = []

        for seq, sid in enumerate(selected_segment_ids, start=1):
            props = self._segment_props.get(sid)
            if not props:
                feat = self._features_by_id.get(sid)
                props = feat.properties if feat else None
            if (
                props is None
                or props.length_m is None
                or props.slope is None
                or props.elevation_m is None
                or not props.highway
            ):
                logger.error(f"Data integrity error: Corridor segment '{sid}' is missing required static attributes: {props}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Data integrity error: Corridor segment '{sid}' is missing required physical properties.",
                )

            length_m = props.length_m
            slope = props.slope
            elevation_m = props.elevation_m
            highway = props.highway

            total_dist_m += length_m
            max_slope = max(max_slope, slope * 100)

            r_item = risk_lookup.get(sid)
            op_status = None

            if r_item is None:
                score = None
                tier = "UNKNOWN"
                unknown_count += 1
                hazard_notes = "Segment risk data unavailable in precomputed model cache"
            else:
                score = r_item.get("risk_score") if isinstance(r_item, dict) else r_item.risk_score
                tier = r_item.get("risk_tier") if isinstance(r_item, dict) else r_item.risk_tier
                op_status = r_item.get("operational_status") if isinstance(r_item, dict) else getattr(r_item, "operational_status", None)

                if op_status == "CLOSED":
                    blocking_segments.append(sid)

                if score is not None:
                    scores.append(score)

                hazard_notes = None
                if op_status == "CLOSED":
                    hazard_notes = "Segment is CLOSED due to active hazard disruption"
                elif tier == "High":
                    high_count += 1
                    hazard_notes = "High landslide susceptibility on current weather backtest"
                    if len(bottlenecks) < 4:
                        bottlenecks.append(f"Segment {sid} ({elevation_m:.0f}m ASL)")
                elif tier == "Medium":
                    med_count += 1
                    hazard_notes = "Elevated rockfall / waterlogging risk"
                elif tier == "Low":
                    low_count += 1
                else:
                    unknown_count += 1
                    tier = "UNKNOWN"
                    hazard_notes = "Segment risk status unclassified"

            itinerary.append(
                SegmentItineraryItem(
                    segment_id=sid,
                    sequence=seq,
                    length_m=round(length_m, 1),
                    slope=round(slope, 4),
                    elevation_m=round(elevation_m, 1),
                    risk_score=score,
                    risk_tier=tier,
                    highway=highway,
                    hazard_notes=hazard_notes,
                    operational_status=op_status,
                )
            )

        total_distance_km = round(total_dist_m / 1000.0, 2)

        # 5. Vehicle Advisory & Timings
        veh_advisory = self._build_vehicle_advisory(req.vehicle_type, max_slope)
        speed = ASSUMED_VEHICLE_SPEEDS_KMH.get(veh_advisory.vehicle_type, 45.0)

        # Mountain base time (hours) = distance / speed
        base_hours = total_distance_km / max(speed, 10.0)
        # Factor mountain curve delays + hazard buffer from modeling assumptions
        delay_minutes = (high_count * ASSUMED_HIGH_RISK_DELAY_MINUTES) + (med_count * ASSUMED_MEDIUM_RISK_DELAY_MINUTES)
        total_minutes = int(math.ceil(base_hours * 60)) + delay_minutes

        # Calculate departure & arrival times
        dep_str = req.departure_time or "08:00"
        try:
            dep_dt = datetime.strptime(dep_str, "%H:%M")
        except ValueError:
            dep_dt = datetime.strptime("08:00", "%H:%M")
            dep_str = "08:00"

        arr_dt = dep_dt + timedelta(minutes=total_minutes)
        arr_str = arr_dt.strftime("%H:%M")

        # Arrival deadline check
        deadline_status = None
        if req.arrival_deadline:
            try:
                deadline_dt = datetime.strptime(req.arrival_deadline, "%H:%M")
                if deadline_dt < dep_dt:
                    deadline_dt += timedelta(days=1)
                diff = (deadline_dt - arr_dt).total_seconds() / 60
                if diff < 0:
                    deadline_status = "Exceeded"
                elif diff < 20:
                    deadline_status = "At Risk"
                else:
                    deadline_status = "Achievable"
            except ValueError:
                deadline_status = None

        avg_score = round(sum(scores) / len(scores), 4) if scores else None
        max_score = round(max(scores), 4) if scores else None

        overall_risk = "Low"
        if high_count > 0 or (max_score is not None and max_score >= 0.35):
            overall_risk = "High"
        elif med_count > 0 or (max_score is not None and max_score >= 0.10):
            overall_risk = "Medium"
        elif unknown_count > 0 or is_live_stale:
            overall_risk = "Unknown"
        else:
            overall_risk = "Low"

        # 6. MultiObjectiveRouter Integration (Task 4)
        router = MultiObjectiveRouter()
        for i, sid in enumerate(selected_segment_ids):
            u_node = f"node_{i}"
            v_node = f"node_{i + 1}"
            props = self._segment_props.get(sid)
            seg_len = props.length_m if props else 200.0
            seg_travel_time = (seg_len / 1000.0) / max(speed, 10.0) * 3600.0
            r_entry = risk_lookup.get(sid)
            s_val = r_entry.get("risk_score") if isinstance(r_entry, dict) else getattr(r_entry, "risk_score", None) if r_entry else None
            is_seg_blocked = sid in blocking_segments

            router.add_edge(
                u=u_node,
                v=v_node,
                edge_id=sid,
                length_m=seg_len,
                travel_time_sec=seg_travel_time,
                risk_score=s_val if s_val is not None else 0.5,
                is_blocked=is_seg_blocked,
            )

        start_node = "node_0"
        end_node = f"node_{len(selected_segment_ids)}"
        baseline_res = router.find_route(start_node, end_node, lambda_risk=0.0, risk_block_threshold=1.0)
        risk_aware_res = router.find_route(start_node, end_node, lambda_risk=5.0, risk_block_threshold=0.85)

        # 7. Operational Recommendation Decision Matrix
        if blocking_segments:
            recommendation = "HOLD"
            recommendation_reason = (
                f"Corridor segment {blocking_segments[0]} is CLOSED due to active hazard. "
                "NH-44 is a single physical mountain road with no bypass; hold at nearest staging yard."
            )
        elif unknown_count > 0 or is_live_stale:
            recommendation = "NO_DATA"
            recommendation_reason = (
                f"Route includes {unknown_count} unmonitored or stale segments. "
                "Conditions cannot be certified safe; proceed only under official traffic authority instructions."
            )
        elif high_count > 0 or (max_score is not None and max_score >= 0.35):
            recommendation = "DELAY"
            recommendation_reason = (
                f"High disruption hazard tier (>=0.35) detected on {high_count} segment(s); "
                "delay transit or hold departure until mountain weather conditions improve."
            )
        elif med_count > 0 or (max_score is not None and max_score >= 0.10):
            recommendation = "PROCEED_WITH_CAUTION"
            recommendation_reason = (
                f"Elevated disruption risk tier (0.10-0.35) on {med_count} segment(s); "
                "proceed with heightened caution, avoid night travel, and observe local marshaling."
            )
        else:
            recommendation = "PROCEED"
            recommendation_reason = "Corridor baseline clear (<0.10); proceed under standard mountain driving precautions."

        # Side-by-side alternative RouteAlternative objects
        base_travel_minutes = int(math.ceil(base_hours * 60))
        baseline_route = RouteAlternative(
            name="baseline_shortest",
            total_distance_km=total_distance_km,
            estimated_travel_minutes=base_travel_minutes,
            overall_risk=overall_risk,
            max_risk_score=max_score,
            average_risk_score=avg_score,
            high_risk_segments_count=high_count,
            medium_risk_segments_count=med_count,
            low_risk_segments_count=low_count,
            unknown_segments_count=unknown_count,
            blocking_segments=blocking_segments,
            is_passable=len(blocking_segments) == 0,
            trade_off_explanation=(
                baseline_res.trade_off_explanation
                if baseline_res
                else f"Baseline path impassable: blocked by {len(blocking_segments)} closed segment(s)."
            ),
        )

        risk_aware_route = RouteAlternative(
            name="risk_aware",
            total_distance_km=total_distance_km,
            estimated_travel_minutes=total_minutes,
            overall_risk=overall_risk,
            max_risk_score=max_score,
            average_risk_score=avg_score,
            high_risk_segments_count=high_count,
            medium_risk_segments_count=med_count,
            low_risk_segments_count=low_count,
            unknown_segments_count=unknown_count,
            blocking_segments=blocking_segments,
            is_passable=len(blocking_segments) == 0,
            trade_off_explanation=(
                risk_aware_res.trade_off_explanation
                if risk_aware_res
                else f"Risk-aware route impassable: blocked by {len(blocking_segments)} closed segment(s); hold or delay."
            ),
        )

        if mode == "live":
            notice = (
                "Live advisory route analysis using real-time ST-GNN inference and Open-Meteo telemetry. "
                "Experimental — not validated. Actual road clearance depends on Highway Traffic Police operational status."
            )
        else:
            notice = (
                f"Advisory route analysis for {req.date} using ST-GNN spatial-temporal graph neural network "
                "conditioned on ERA5-Land reanalysis. This represents retrospective situational intelligence; "
                "actual mountain clearance depends on real-time highway police operational status."
            )

        return JourneyPlanResponse(
            origin=origin_p.name,
            destination=dest_p.name,
            journey_date=journey_date_str,
            departure_time=dep_str,
            estimated_arrival_time=arr_str,
            arrival_deadline=req.arrival_deadline,
            deadline_status=deadline_status,
            total_distance_km=total_distance_km,
            estimated_travel_minutes=total_minutes,
            travel_time_disclaimer=(
                "Estimated transit time calculated from assumed vehicle speeds and hazard buffers; "
                "not measured live telemetry."
            ),
            vehicle_advisory=veh_advisory,
            overall_route_risk=overall_risk,
            max_risk_score=max_score,
            average_risk_score=avg_score,
            total_route_segments=len(itinerary),
            high_risk_segments_count=high_count,
            medium_risk_segments_count=med_count,
            low_risk_segments_count=low_count,
            unknown_segments_count=unknown_count,
            is_incomplete_data=unknown_count > 0,
            bottlenecks=bottlenecks,
            historical_disruptions_on_route=high_count + med_count,
            retrospective_notice=notice,
            itinerary=itinerary,
            mode=mode,
            recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            blocking_segments=blocking_segments,
            has_alternative=False,  # NH-44 is physically a single road
            baseline_route=baseline_route,
            risk_aware_route=risk_aware_route,
        )


journey_service = JourneyService()
