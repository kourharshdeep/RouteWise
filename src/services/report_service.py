"""Field Report Management and State Machine Service.

Provides SQLite persistence for incident reports, spatial snapping to NH-44 corridor segments,
Pillow-based EXIF-stripped photo processing, strict state transition validation, and audit logging.
"""
from __future__ import annotations

import io
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import pyproj
from fastapi import HTTPException, UploadFile, status
from PIL import Image
from shapely import wkt
from shapely.geometry import Point

from src.api.config import settings
from src.api.schemas.auth import UserProfile, UserRole
from src.api.schemas.reports import (
    PublicReportItem,
    ReportCategory,
    ReportListResponse,
    ReportResponse,
    ReportStatus,
    ReportStatusHistoryItem,
    ReportSummaryStats,
)

# Server-enforced state transitions
ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    ReportStatus.SUBMITTED.value: [ReportStatus.VERIFIED.value, ReportStatus.REJECTED.value],
    ReportStatus.VERIFIED.value: [ReportStatus.ASSIGNED.value, ReportStatus.REJECTED.value],
    ReportStatus.ASSIGNED.value: [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value],
    ReportStatus.RESOLVED.value: [ReportStatus.VERIFIED.value],  # Reopening allowed with note
    ReportStatus.REJECTED.value: [],  # Terminal state
}

MAX_SEGMENT_DISTANCE_METERS = 500.0  # Max distance to associate incident with corridor segment


class ReportService:
    """Handles field reports, state machine transitions, spatial indexing, and media."""

    def __init__(
        self,
        db_path: Path | None = None,
        graph_path: Path | None = None,
        uploads_dir: Path | None = None,
    ) -> None:
        self.db_path = db_path or settings.db_path
        self.graph_path = graph_path or settings.corridor_graph_path
        self.uploads_dir = (uploads_dir or settings.uploads_dir) / "reports"
        self._transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
        self._segment_geometries: List[Tuple[str, Any]] = []
        self._init_db()
        self._load_segment_geometries()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes tables for reports and audit history."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    client_uuid TEXT UNIQUE NOT NULL,
                    reporter_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    nearest_segment_id TEXT,
                    nearest_segment_distance_m REAL,
                    photo_path TEXT,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    assigned_to INTEGER,
                    client_created_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_simulated INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(reporter_id) REFERENCES users(id),
                    FOREIGN KEY(assigned_to) REFERENCES users(id)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_client_uuid ON reports(client_uuid);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_segment ON reports(nearest_segment_id);")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS report_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    actor_id INTEGER NOT NULL,
                    actor_role TEXT NOT NULL,
                    note TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_report_history_report ON report_status_history(report_id);")
            conn.commit()

    def _load_segment_geometries(self) -> None:
        """Loads segment geometries from graphml file for fast spatial queries."""
        if not self.graph_path.exists():
            return
        G = nx.read_graphml(self.graph_path)
        for u, v, k, data in G.edges(keys=True, data=True):
            segment_id = f"{u}_{v}_{k}"
            geom_wkt = data.get("geometry")
            if geom_wkt:
                geom = wkt.loads(geom_wkt)
                self._segment_geometries.append((segment_id, geom))

    def snap_to_corridor(self, lat: float, lon: float) -> Tuple[Optional[str], Optional[float]]:
        """Finds nearest corridor segment within 500m using projected coordinates."""
        if not self._segment_geometries:
            return None, None

        # Project (lon, lat) to UTM 43N meters
        x, y = self._transformer.transform(lon, lat)
        point = Point(x, y)

        min_distance = float("inf")
        nearest_id = None

        for seg_id, geom in self._segment_geometries:
            dist = point.distance(geom)
            if dist < min_distance:
                min_distance = dist
                nearest_id = seg_id

        if min_distance <= MAX_SEGMENT_DISTANCE_METERS:
            return nearest_id, round(min_distance, 1)
        return None, round(min_distance, 1)

    def _validate_and_save_photo(self, photo: UploadFile) -> str:
        """Validates photo content, strips EXIF metadata for privacy, and stores securely."""
        file_bytes = photo.file.read()
        if len(file_bytes) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Photo exceeds maximum allowed size of {settings.max_upload_bytes // (1024*1024)} MB.",
            )

        # Magic bytes check
        is_jpeg = file_bytes.startswith(b"\xff\xd8\xff")
        is_png = file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        is_webp = file_bytes.startswith(b"RIFF") and len(file_bytes) > 12 and file_bytes[8:12] == b"WEBP"

        if not (is_jpeg or is_png or is_webp):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Invalid image format. Only authentic JPEG, PNG, or WebP files are accepted.",
            )

        try:
            image = Image.open(io.BytesIO(file_bytes))
            image_format = image.format
            if image_format not in ("JPEG", "PNG", "WEBP"):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported image format: {image_format}",
                )

            # Strip EXIF metadata by writing pure image buffer
            ext = "jpg" if image_format == "JPEG" else ("png" if image_format == "PNG" else "webp")
            filename = f"{uuid.uuid4().hex}.{ext}"
            file_path = self.uploads_dir / filename

            # Clean save without EXIF
            data = list(image.getdata())
            clean_image = Image.new(image.mode, image.size)
            clean_image.putdata(data)
            clean_image.save(file_path)

            return filename
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to process image: {str(e)}",
            )

    def create_report(
        self,
        client_uuid: str,
        category: str,
        description: Optional[str],
        latitude: float,
        longitude: float,
        client_created_at: Optional[str],
        photo: Optional[UploadFile],
        reporter: UserProfile,
        is_simulated: int = 0,
    ) -> ReportResponse:
        """Creates a new field report with idempotency on client_uuid."""
        # 1. Geographic corridor sanity check (J&K region)
        if not (32.0 <= latitude <= 35.0 and 74.0 <= longitude <= 76.5):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coordinates are outside the Ramban-Banihal NH-44 geographical region.",
            )

        # 2. Check Category
        valid_cats = [c.value for c in ReportCategory]
        if category not in valid_cats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category '{category}'. Must be one of: {', '.join(valid_cats)}",
            )

        # 3. Idempotency Check
        with self._get_connection() as conn:
            existing = conn.execute("SELECT * FROM reports WHERE client_uuid = ?", (client_uuid,)).fetchone()
            if existing:
                return self._row_to_report(conn, existing)

            # 4. Snap nearest segment
            nearest_seg, dist_m = self.snap_to_corridor(latitude, longitude)

            # 5. Handle optional photo
            photo_filename = None
            if photo and photo.filename:
                photo_filename = self._validate_and_save_photo(photo)

            report_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            init_status = ReportStatus.SUBMITTED.value

            conn.execute(
                """
                INSERT INTO reports (
                    id, client_uuid, reporter_id, category, description, latitude, longitude,
                    nearest_segment_id, nearest_segment_distance_m, photo_path, status, assigned_to,
                    client_created_at, created_at, updated_at, is_simulated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    client_uuid,
                    reporter.id,
                    category,
                    description.strip() if description else None,
                    latitude,
                    longitude,
                    nearest_seg,
                    dist_m,
                    photo_filename,
                    init_status,
                    client_created_at or now,
                    now,
                    now,
                    is_simulated,
                ),
            )

            # Insert initial audit history
            conn.execute(
                """
                INSERT INTO report_status_history (
                    report_id, from_status, to_status, actor_id, actor_role, note, timestamp
                )
                VALUES (?, NULL, ?, ?, ?, 'Field report submitted by reporter', ?)
                """,
                (report_id, init_status, reporter.id, reporter.role, now),
            )
            conn.commit()

            created = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            return self._row_to_report(conn, created)

    def get_user_reports(self, user_id: int) -> List[ReportResponse]:
        """Returns reports submitted by specific user."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE reporter_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._row_to_report(conn, r) for r in rows]

    def get_patrol_reports(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        segment_id: Optional[str] = None,
        assignee_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReportListResponse:
        """Paginated search for patrol operations dashboard."""
        query = "SELECT * FROM reports WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM reports WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            count_query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            count_query += " AND category = ?"
            params.append(category)
        if segment_id:
            query += " AND nearest_segment_id = ?"
            count_query += " AND nearest_segment_id = ?"
            params.append(segment_id)
        if assignee_id is not None:
            query += " AND assigned_to = ?"
            count_query += " AND assigned_to = ?"
            params.append(assignee_id)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"

        with self._get_connection() as conn:
            total = conn.execute(count_query, params).fetchone()[0]
            rows = conn.execute(query, params + [limit, offset]).fetchall()
            items = [self._row_to_report(conn, r) for r in rows]

        return ReportListResponse(items=items, total=total, limit=limit, offset=offset)

    def get_public_reports(self) -> List[PublicReportItem]:
        """Returns verified and assigned reports with reporter details redacted."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, category, description, latitude, longitude, nearest_segment_id,
                       photo_path, status, created_at, is_simulated
                FROM reports
                WHERE status IN ('verified', 'assigned')
                ORDER BY created_at DESC
                """
            ).fetchall()

            result = []
            for r in rows:
                has_photo = bool(r["photo_path"])
                photo_url = f"/api/v1/reports/{r['id']}/photo" if has_photo else None
                result.append(
                    PublicReportItem(
                        id=r["id"],
                        category=r["category"],
                        description=r["description"],
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        nearest_segment_id=r["nearest_segment_id"],
                        has_photo=has_photo,
                        photo_url=photo_url,
                        status=r["status"],
                        created_at=r["created_at"],
                        is_simulated=bool(r["is_simulated"]),
                    )
                )
            return result

    def get_report_by_id(self, report_id: str, current_user: UserProfile) -> ReportResponse:
        """Retrieves a single report enforcing object-level authorization."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

            # Patrol and Admin can view any report
            if current_user.role in (UserRole.PATROL.value, UserRole.ADMIN.value):
                return self._row_to_report(conn, row)

            # Reporters can view their own reports
            if current_user.id == row["reporter_id"]:
                return self._row_to_report(conn, row)

            # Public/guest can view only if verified/assigned
            if row["status"] in ("verified", "assigned"):
                return self._row_to_report(conn, row)

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view this report.",
            )

    def update_report_status(
        self,
        report_id: str,
        new_status: str,
        note: Optional[str],
        actor: UserProfile,
    ) -> ReportResponse:
        """Performs state machine transition with audit logging."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

            current_status = row["status"]
            allowed = ALLOWED_TRANSITIONS.get(current_status, [])

            if new_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Invalid status transition from '{current_status}' to '{new_status}'. "
                        f"Permitted transitions: {allowed}."
                    ),
                )

            # Notes are required when rejecting or reopening
            clean_note = note.strip() if note else ""
            if new_status == ReportStatus.REJECTED.value and not clean_note:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A rejection note is required to reject a report.",
                )
            if current_status == ReportStatus.RESOLVED.value and new_status == ReportStatus.VERIFIED.value and not clean_note:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A note is required when reopening a resolved report.",
                )

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE reports SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, report_id),
            )

            conn.execute(
                """
                INSERT INTO report_status_history (
                    report_id, from_status, to_status, actor_id, actor_role, note, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, current_status, new_status, actor.id, actor.role, clean_note or None, now),
            )
            conn.commit()

            updated = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            return self._row_to_report(conn, updated)

    def assign_report(
        self,
        report_id: str,
        assignee_id: int,
        note: Optional[str],
        actor: UserProfile,
    ) -> ReportResponse:
        """Assigns report to a verified patrol officer."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

            # Validate that assignee is a patrol user or admin
            assignee = conn.execute(
                "SELECT id, name, role FROM users WHERE id = ?",
                (assignee_id,),
            ).fetchone()
            if not assignee:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee user not found.")
            if assignee["role"] not in (UserRole.PATROL.value, UserRole.ADMIN.value):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Assignee must have role 'patrol' or 'admin'. Selected user role is '{assignee['role']}'.",
                )

            current_status = row["status"]
            # Assigning moves verified to assigned, or updates assignee if already assigned
            new_status = ReportStatus.ASSIGNED.value
            if current_status not in (ReportStatus.VERIFIED.value, ReportStatus.ASSIGNED.value):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot assign report with status '{current_status}'. Must be 'verified' or 'assigned'.",
                )

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE reports SET status = ?, assigned_to = ?, updated_at = ? WHERE id = ?",
                (new_status, assignee_id, now, report_id),
            )

            assign_note = f"Assigned to {assignee['name']} (Patrol)"
            if note and note.strip():
                assign_note += f": {note.strip()}"

            conn.execute(
                """
                INSERT INTO report_status_history (
                    report_id, from_status, to_status, actor_id, actor_role, note, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, current_status, new_status, actor.id, actor.role, assign_note, now),
            )
            conn.commit()

            updated = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            return self._row_to_report(conn, updated)

    def get_summary_stats(self) -> ReportSummaryStats:
        """Calculates breakdown counts by status."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM reports GROUP BY status").fetchall()
            counts = {r["status"]: r["cnt"] for r in rows}
            total = sum(counts.values())
            return ReportSummaryStats(
                total=total,
                submitted=counts.get("submitted", 0),
                verified=counts.get("verified", 0),
                assigned=counts.get("assigned", 0),
                resolved=counts.get("resolved", 0),
                rejected=counts.get("rejected", 0),
            )

    def get_photo_path(self, report_id: str, current_user: UserProfile) -> Path:
        """Returns verified local photo path for file response."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT reporter_id, status, photo_path FROM reports WHERE id = ?", (report_id,)).fetchone()
            if not row or not row["photo_path"]:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found.")

            # Access validation
            if current_user.role not in (UserRole.PATROL.value, UserRole.ADMIN.value):
                if current_user.id != row["reporter_id"] and row["status"] not in ("verified", "assigned"):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

            file_path = self.uploads_dir / row["photo_path"]
            if not file_path.exists():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo file not found on disk.")
            return file_path

    def _row_to_report(self, conn: sqlite3.Connection, row: sqlite3.Row) -> ReportResponse:
        """Maps database row and associated audit trail to response model."""
        # Fetch reporter name
        reporter = conn.execute("SELECT name FROM users WHERE id = ?", (row["reporter_id"],)).fetchone()
        reporter_name = reporter["name"] if reporter else "Unknown Reporter"

        # Fetch assignee name
        assignee_name = None
        if row["assigned_to"]:
            assignee = conn.execute("SELECT name FROM users WHERE id = ?", (row["assigned_to"],)).fetchone()
            assignee_name = assignee["name"] if assignee else None

        # Fetch audit history
        hist_rows = conn.execute(
            """
            SELECT h.*, u.name as actor_name
            FROM report_status_history h
            LEFT JOIN users u ON h.actor_id = u.id
            WHERE h.report_id = ?
            ORDER BY h.timestamp ASC
            """,
            (row["id"],),
        ).fetchall()

        history_items = [
            ReportStatusHistoryItem(
                id=h["id"],
                report_id=h["report_id"],
                from_status=h["from_status"],
                to_status=h["to_status"],
                actor_id=h["actor_id"],
                actor_name=h["actor_name"] or ("Guest" if h["actor_id"] == 0 else "System"),
                actor_role=h["actor_role"],
                note=h["note"],
                timestamp=h["timestamp"],
            )
            for h in hist_rows
        ]

        has_photo = bool(row["photo_path"])
        photo_url = f"/api/v1/reports/{row['id']}/photo" if has_photo else None

        return ReportResponse(
            id=row["id"],
            client_uuid=row["client_uuid"],
            reporter_id=row["reporter_id"],
            reporter_name=reporter_name,
            category=row["category"],
            description=row["description"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            nearest_segment_id=row["nearest_segment_id"],
            nearest_segment_distance_m=row["nearest_segment_distance_m"],
            has_photo=has_photo,
            photo_url=photo_url,
            status=row["status"],
            assigned_to=row["assigned_to"],
            assigned_to_name=assignee_name,
            client_created_at=row["client_created_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_simulated=bool(row["is_simulated"]),
            history=history_items,
        )


report_service = ReportService()
