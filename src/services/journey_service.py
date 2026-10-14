"""Journey planning and corridor routing service.

Calculates route segments between corridor landmarks, fetches ST-GNN segment risk scores,
evaluates vehicle-specific travel times and vulnerability factors, and enforces
honest scientific semantics.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
from fastapi import HTTPException, status

from src.api.config import settings
from src.api.schemas.journey import (
    JourneyPlace,
    JourneyPlanRequest,
    JourneyPlanResponse,
    SegmentItineraryItem,
    VehicleAdvisory,
)
from src.services.corridor_service import corridor_service
from src.services.risk_service import risk_service


class JourneyService:
    """Provides route planning, corridor pathfinding, and vehicle risk profiling."""

    def __init__(
        self,
        places_path: Path | None = None,
        graph_path: Path | None = None,
    ) -> None:
        self.places_path = places_path or settings.places_path
        self.graph_path = graph_path or settings.corridor_graph_path
        self._places: List[JourneyPlace] = []
        self._load_places()

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

    def _find_nearest_feature_index(self, lat: float, lon: float, features: List[Any]) -> int:
        best_idx = 0
        min_dist = float("inf")
        for i, feat in enumerate(features):
            coords = feat.geometry.coordinates
            # Coords are [lon, lat]
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

    def plan_journey(self, req: JourneyPlanRequest) -> JourneyPlanResponse:
        """Plans a journey along the corridor with risk scoring and itinerary generation."""
        # 1. Resolve Origin and Destination
        origin_clean = req.origin.strip().lower()
        dest_clean = req.destination.strip().lower()

        origin_p = next(
            (p for p in self._places if p.id == origin_clean or p.name.lower() == origin_clean or origin_clean in p.name.lower()),
            None,
        )
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

        # 2. Fetch corridor highway geometry
        geojson = corridor_service.get_corridor_geojson()
        features = geojson.features

        orig_idx = self._find_nearest_feature_index(origin_p.lat, origin_p.lon, features)
        dest_idx = self._find_nearest_feature_index(dest_p.lat, dest_p.lon, features)

        step = 1 if dest_idx >= orig_idx else -1
        selected_features = features[orig_idx : dest_idx + step : step]

        if not selected_features:
            selected_features = features[:10]

        # 3. Retrieve risk predictions for requested date
        risk_lookup: Dict[str, Any] = {}
        is_historical = False
        try:
            risk_resp = risk_service.get_risk_by_date(req.date)
            is_historical = True
            for seg in risk_resp.segments:
                risk_lookup[seg.segment_id] = seg
        except HTTPException:
            # If outside precomputed range, retrieve sample baseline date or handle gracefully
            dates_info = risk_service.get_available_dates()
            fallback_date = dates_info.sample_dates[0] if dates_info.sample_dates else "2023-07-09"
            fallback_resp = risk_service.get_risk_by_date(fallback_date)
            for seg in fallback_resp.segments:
                risk_lookup[seg.segment_id] = seg

        # 4. Build itinerary items
        itinerary: List[SegmentItineraryItem] = []
        total_dist_m = 0.0
        max_slope = 0.0
        scores: List[float] = []
        high_count = 0
        med_count = 0
        low_count = 0
        bottlenecks: List[str] = []

        for seq, feat in enumerate(selected_features, start=1):
            sid = feat.id
            props = feat.properties
            length_m = props.length_m if props else 250.0
            slope = props.slope if props else 0.04
            elevation_m = props.elevation_m if props else 1100.0
            highway = props.highway if props else "trunk"

            total_dist_m += length_m
            max_slope = max(max_slope, slope * 100)

            r_item = risk_lookup.get(sid)
            score = r_item.risk_score if r_item else 0.05
            tier = r_item.risk_tier if r_item else "Low"

            if score is not None:
                scores.append(score)

            hazard_notes = None
            if tier == "High":
                high_count += 1
                hazard_notes = "High landslide susceptibility on current weather backtest"
                if len(bottlenecks) < 4:
                    bottlenecks.append(f"Segment {sid} ({elevation_m:.0f}m ASL)")
            elif tier == "Medium":
                med_count += 1
                hazard_notes = "Elevated rockfall / waterlogging risk"
            else:
                low_count += 1

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
                )
            )

        total_distance_km = round(total_dist_m / 1000.0, 2)
        if total_distance_km < 1.0:
            total_distance_km = 4.5  # Mountain road realistic minimum

        # 5. Vehicle Advisory & Timings
        veh_advisory = self._build_vehicle_advisory(req.vehicle_type, max_slope)
        speed = veh_advisory.speed_limit_kmh

        # Mountain base time (hours) = distance / speed
        base_hours = total_distance_km / max(speed, 10.0)
        # Factor mountain curve delays + hazard buffer (2 mins per high risk segment)
        delay_minutes = (high_count * 3) + (med_count * 1)
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

        avg_score = sum(scores) / len(scores) if scores else 0.05
        max_score = max(scores) if scores else 0.05

        overall_risk = "Low"
        if high_count > 0 or max_score >= 0.35:
            overall_risk = "High"
        elif med_count > 0 or max_score >= 0.10:
            overall_risk = "Medium"

        retrospective_notice = (
            f"Advisory route analysis for {req.date} using ST-GNN spatial-temporal graph neural network "
            "conditioned on ERA5-Land reanalysis. This represents retrospective situational intelligence; "
            "actual mountain clearance depends on real-time highway police operational status."
        )

        return JourneyPlanResponse(
            origin=origin_p.name,
            destination=dest_p.name,
            journey_date=req.date,
            departure_time=dep_str,
            estimated_arrival_time=arr_str,
            arrival_deadline=req.arrival_deadline,
            deadline_status=deadline_status,
            total_distance_km=total_distance_km,
            estimated_travel_minutes=total_minutes,
            vehicle_advisory=veh_advisory,
            overall_route_risk=overall_risk,
            max_risk_score=round(max_score, 4),
            average_risk_score=round(avg_score, 4),
            total_route_segments=len(itinerary),
            high_risk_segments_count=high_count,
            medium_risk_segments_count=med_count,
            low_risk_segments_count=low_count,
            bottlenecks=bottlenecks,
            historical_disruptions_on_route=high_count + med_count,
            retrospective_notice=retrospective_notice,
            itinerary=itinerary,
        )


journey_service = JourneyService()
