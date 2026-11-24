
from datetime import datetime, timezone
from typing import Literal
import json
import re
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from urllib.parse import urlparse

from database import Base, SessionLocal


class EvidenceRecord(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl
    description: str = Field(default="", max_length=10000)
    source_type: str = Field(default="manual", min_length=1, max_length=100)
    case_id: int = Field(ge=1)


class ResearchCaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    question: str = Field(min_length=10, max_length=2000)
    scope: str = Field(min_length=10, max_length=2000)
    authorization_basis: Literal["self_audit", "explicit_consent", "official_duties", "public_interest"]
    authorized: Literal[True]

    @field_validator("title", "question", "scope", mode="before")
    @classmethod
    def trim_case_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ResearchCaseStatusUpdate(BaseModel):
    status: Literal["open", "closed"]


class VerificationUpdate(BaseModel):
    status: Literal["unverified", "reviewed", "corroborated", "disputed"]
    note: str = Field(default="", max_length=2000)


class ExposureAlertUpdate(BaseModel):
    status: Literal["needs_action", "reported", "removed", "false_positive"]


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("research_cases.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(100))
    verification_status: Mapped[str] = mapped_column(
        String(30), default="unverified"
    )
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


class ExposureAlert(Base):
    __tablename__ = "exposure_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("research_cases.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(40))
    source_domain: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80))
    report_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="needs_action")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ResearchCase(Base):
    __tablename__ = "research_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    question: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    authorization_basis: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="open")
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CaseActivity(Base):
    __tablename__ = "case_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("research_cases.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(500))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def _add_case_activity(db, case_id: int, event_type: str, summary: str, details: dict | None = None):
    item = CaseActivity(
        case_id=case_id,
        event_type=event_type,
        summary=summary,
        details_json=json.dumps(details or {}, sort_keys=True, separators=(",", ":")),
    )
    db.add(item)
    return item


def record_case_activity(case_id: int, event_type: str, summary: str, details: dict | None = None) -> dict:
    """Append a case event. Callers must omit personal search identifiers."""
    db = SessionLocal()
    try:
        if db.get(ResearchCase, case_id) is None:
            raise ValueError("Research case not found.")
        item = _add_case_activity(db, case_id, event_type, summary, details)
        db.commit()
        db.refresh(item)
        return _activity_dict(item)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _activity_dict(item: CaseActivity) -> dict:
    return {
        "id": item.id,
        "case_id": item.case_id,
        "event_type": item.event_type,
        "summary": item.summary,
        "details": json.loads(item.details_json or "{}"),
        "occurred_at": item.occurred_at.isoformat(),
    }


def get_case_activity(case_id: int, limit: int = 50) -> list[dict]:
    db = SessionLocal()
    try:
        items = (
            db.query(CaseActivity)
            .filter(CaseActivity.case_id == case_id)
            .order_by(CaseActivity.occurred_at.desc(), CaseActivity.id.desc())
            .limit(limit)
            .all()
        )
        return [_activity_dict(item) for item in items]
    finally:
        db.close()


def _case_dict(item: ResearchCase, evidence_count: int = 0, alert_count: int = 0) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "question": item.question,
        "scope": item.scope,
        "authorization_basis": item.authorization_basis,
        "status": item.status,
        "authorized_at": item.authorized_at.isoformat(),
        "created_at": item.created_at.isoformat(),
        "evidence_count": evidence_count,
        "alert_count": alert_count,
    }


def create_research_case(record: ResearchCaseCreate) -> dict:
    db = SessionLocal()
    try:
        item = ResearchCase(
            title=record.title.strip(),
            question=record.question.strip(),
            scope=record.scope.strip(),
            authorization_basis=record.authorization_basis,
            status="open",
            authorized_at=datetime.now(timezone.utc),
        )
        db.add(item)
        db.flush()
        _add_case_activity(
            db, item.id, "case_created", "Case created with a stated question, scope, and authority basis.",
            {"authorization_basis": record.authorization_basis},
        )
        db.commit()
        db.refresh(item)
        return _case_dict(item)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_research_cases() -> list[dict]:
    db = SessionLocal()
    try:
        cases = db.query(ResearchCase).order_by(ResearchCase.created_at.desc(), ResearchCase.id.desc()).all()
        return [
            _case_dict(
                item,
                evidence_count=db.query(func.count(Evidence.id)).filter(Evidence.case_id == item.id).scalar() or 0,
                alert_count=db.query(func.count(ExposureAlert.id)).filter(ExposureAlert.case_id == item.id).scalar() or 0,
            )
            for item in cases
        ]
    finally:
        db.close()


def get_research_case(case_id: int) -> dict | None:
    db = SessionLocal()
    try:
        item = db.get(ResearchCase, case_id)
        if item is None:
            return None
        return _case_dict(
            item,
            evidence_count=db.query(func.count(Evidence.id)).filter(Evidence.case_id == item.id).scalar() or 0,
            alert_count=db.query(func.count(ExposureAlert.id)).filter(ExposureAlert.case_id == item.id).scalar() or 0,
        )
    finally:
        db.close()


def update_research_case_status(case_id: int, status: str) -> dict | None:
    db = SessionLocal()
    try:
        item = db.get(ResearchCase, case_id)
        if item is None:
            return None
        if item.status != status:
            _add_case_activity(
                db, case_id, f"case_{status}",
                "Case closed; further collection is blocked." if status == "closed" else "Case reopened for collection.",
            )
        item.status = status
        db.commit()
        db.refresh(item)
        return _case_dict(item)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")


def add_evidence(record: EvidenceRecord):
    db = SessionLocal()

    try:
        entry = Evidence(
            case_id=record.case_id,
            title=record.title,
            source_url=str(record.source_url),
            description=record.description,
            source_type=record.source_type,
            verification_status="unverified",
        )

        db.add(entry)
        db.flush()
        _add_case_activity(
            db, record.case_id, "source_added", "A source was added to the case.",
            {"evidence_id": entry.id, "source_type": record.source_type},
        )
        db.commit()
        db.refresh(entry)

        return {
            "id": entry.id,
            "case_id": entry.case_id,
            "title": entry.title,
            "source_url": entry.source_url,
            "description": entry.description,
            "source_type": entry.source_type,
            "verification_status": entry.verification_status,
            "verification_note": entry.verification_note,
            "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
            "search_query": entry.search_query,
            "recorded_at": entry.recorded_at.isoformat()
        }
    finally:
        db.close()


def get_evidence(status: str | None = None, search: str | None = None, case_id: int | None = None):
    db = SessionLocal()

    try:
        query = db.query(Evidence)
        if case_id is not None:
            query = query.filter(Evidence.case_id == case_id)
        if status:
            query = query.filter(Evidence.verification_status == status)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                (Evidence.title.ilike(pattern))
                | (Evidence.description.ilike(pattern))
                | (Evidence.source_url.ilike(pattern))
            )
        records = query.order_by(Evidence.recorded_at.desc(), Evidence.id.desc()).all()

        return [
            {
                "id": item.id,
                "case_id": item.case_id,
                "title": item.title,
                "source_url": item.source_url,
                "description": item.description,
                "source_type": item.source_type,
                "verification_status": item.verification_status,
                "verification_note": item.verification_note,
                "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                "search_query": item.search_query,
                "recorded_at": item.recorded_at.isoformat()
            }
            for item in records
        ]
    finally:
        db.close()


def save_search_results(
    results: list[dict], case_id: int, search_query: str = "", source_type: str = "web_search"
) -> dict:
    """Save usable public search results as unverified evidence records."""
    db = SessionLocal()
    saved = 0

    try:
        for result in results:
            title = (result.get("title") or "").strip()
            url = (result.get("url") or "").strip()
            parsed_url = urlparse(url)

            # Search providers can return incomplete or non-web results.
            valid_web_url = parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)
            if not title or not valid_web_url:
                continue
            if len(title) > 300:
                title = title[:297].rstrip() + "..."

            db.add(Evidence(
                case_id=case_id,
                title=title,
                source_url=url,
                description=(result.get("snippet") or "").strip(),
                source_type=source_type,
                verification_status="unverified",
                search_query=search_query,
            ))
            saved += 1

        db.commit()
        return {"saved": saved}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_verification(evidence_id: int, update: VerificationUpdate):
    db = SessionLocal()
    try:
        item = db.get(Evidence, evidence_id)
        if item is None:
            return None
        item.verification_status = update.status
        item.verification_note = update.note.strip() or None
        item.reviewed_at = datetime.now(timezone.utc) if update.status != "unverified" else None
        if item.case_id is not None:
            _add_case_activity(
                db, item.case_id, "source_reviewed", f"A source review status was set to {update.status}.",
                {"evidence_id": item.id, "verification_status": update.status},
            )
        db.commit()
        db.refresh(item)
        return {
            "id": item.id,
            "verification_status": item.verification_status,
            "verification_note": item.verification_note,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def find_contact_categories(results: list[dict], platform: str, platform_domain: str) -> list[dict]:
    """Detect only broad contact-detail categories from snippets; discard raw text and page paths."""
    found = set()
    expected = platform_domain.lower()
    for result in results:
        url = urlparse((result.get("url") or "").strip())
        host = (url.hostname or "").lower().rstrip(".")
        if url.scheme not in {"http", "https"} or not (host == expected or host.endswith("." + expected)):
            continue
        snippet = result.get("snippet") or ""
        categories = set()
        if EMAIL_PATTERN.search(snippet):
            categories.add("Possible email address")
        if PHONE_PATTERN.search(snippet):
            categories.add("Possible phone number")
        found.update((host, category) for category in categories)
    return [
        {"platform": platform, "source_domain": host, "category": category}
        for host, category in sorted(found)
    ]


def save_exposure_alerts(
    alerts: list[dict], report_url: str, case_id: int, platform: str
) -> list[dict]:
    """Save redacted alert metadata only: no identifier, snippet, or result-page path."""
    db = SessionLocal()
    try:
        saved = []
        for alert in alerts:
            item = ExposureAlert(
                case_id=case_id,
                platform=alert["platform"],
                source_domain=alert["source_domain"],
                category=alert["category"],
                report_url=report_url,
                status="needs_action",
            )
            db.add(item)
            saved.append(item)
        _add_case_activity(
            db, case_id, "exposure_check", "A public account exposure check was completed.",
            {"platform": platform, "alerts_saved": len(saved)},
        )
        db.commit()
        return [
            {
                "id": item.id,
                "case_id": item.case_id,
                "platform": item.platform,
                "source_domain": item.source_domain,
                "category": item.category,
                "report_url": item.report_url,
                "status": item.status,
                "recorded_at": item.recorded_at.isoformat(),
            }
            for item in saved
        ]
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_exposure_alerts(status: str | None = None, case_id: int | None = None):
    db = SessionLocal()
    try:
        query = db.query(ExposureAlert)
        if case_id is not None:
            query = query.filter(ExposureAlert.case_id == case_id)
        if status:
            query = query.filter(ExposureAlert.status == status)
        alerts = query.order_by(ExposureAlert.recorded_at.desc(), ExposureAlert.id.desc()).all()
        return [
            {
                "id": item.id,
                "case_id": item.case_id,
                "platform": item.platform,
                "source_domain": item.source_domain,
                "category": item.category,
                "report_url": item.report_url,
                "status": item.status,
                "recorded_at": item.recorded_at.isoformat(),
            }
            for item in alerts
        ]
    finally:
        db.close()


def update_exposure_alert(alert_id: int, status: str):
    db = SessionLocal()
    try:
        item = db.get(ExposureAlert, alert_id)
        if item is None:
            return None
        item.status = status
        if item.case_id is not None:
            _add_case_activity(
                db, item.case_id, "alert_status_changed", f"An exposure alert was marked {status.replace('_', ' ')}.",
                {"alert_id": item.id, "status": status},
            )
        db.commit()
        return {"id": item.id, "status": item.status}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
