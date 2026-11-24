from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from database import create_database
from modules.discovery import SEARCH_BACKEND, search_public_sources, search_username_sources
from modules.open_sources import search_wikipedia, search_wikidata
from modules.evidence import (
    ResearchCaseCreate,
    ResearchCaseStatusUpdate,
    ExposureAlertUpdate,
    EvidenceRecord,
    VerificationUpdate,
    add_evidence,
    create_research_case,
    find_contact_categories,
    get_exposure_alerts,
    get_evidence,
    get_case_activity,
    get_research_case,
    get_research_cases,
    save_exposure_alerts,
    save_search_results,
    record_case_activity,
    update_exposure_alert,
    update_research_case_status,
    update_verification,
)

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(
    title="ATLAS OSINT",
    description="Lawful public-source research and evidence management",
    version="0.4.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup():
    create_database()


class ExposureCheckRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    case_id: int = Field(ge=1)
    authorized: Literal[True]

    @field_validator("username", mode="before")
    @classmethod
    def clean_username(cls, value):
        if isinstance(value, str):
            return value.strip().removeprefix("@").strip()
        return value

    @field_validator("platform")
    @classmethod
    def known_platform(cls, value):
        if value not in PLATFORM_DOMAINS:
            raise ValueError("Choose a supported service.")
        return value


PLATFORM_DOMAINS = {
    "GitHub": "github.com",
    "Reddit": "reddit.com",
    "Instagram": "instagram.com",
    "TikTok": "tiktok.com",
    "X": "x.com",
    "LinkedIn": "linkedin.com",
    "Facebook": "facebook.com",
    "YouTube": "youtube.com",
    "WhatsApp": "whatsapp.com",
    "Telegram": "t.me",
    "Snapchat": "snapchat.com",
    "ShareChat": "sharechat.com",
    "Discord": "discord.com",
    "Twitch": "twitch.tv",
    "Amazon India": "amazon.in",
    "Flipkart": "flipkart.com",
    "Myntra": "myntra.com",
    "Meesho": "meesho.com",
    "Swiggy": "swiggy.com",
    "Zomato": "zomato.com",
    "Paytm": "paytm.com",
    "PhonePe": "phonepe.com",
}

PLATFORM_REPORT_URLS = {
    "GitHub": "https://docs.github.com/en/site-policy/content-removal-policies/github-private-information-removal-policy",
    "Reddit": "https://support.reddithelp.com/hc/en-us/articles/360043066452-Personal-Information",
    "Instagram": "https://help.instagram.com/",
    "TikTok": "https://support.tiktok.com/en/safety-hc/report-a-problem/report-a-video",
    "X": "https://help.x.com/en/forms/privacy/report-content-violating-your-privacy-rights",
    "LinkedIn": "https://www.linkedin.com/help/linkedin/answer/a1378278/report-inappropriate-content-messages-or-safety-concerns",
    "Facebook": "https://www.facebook.com/help/203305893040179",
    "YouTube": "https://support.google.com/youtube/answer/2801895",
    "WhatsApp": "https://www.whatsapp.com/contact",
    "Telegram": "https://telegram.org/support",
    "Snapchat": "https://help.snapchat.com/hc/en-us/requests/new",
    "ShareChat": "https://sharechat.com/legal/privacy-policy",
    "Discord": "https://support.discord.com/hc/en-us/requests/new",
    "Twitch": "https://safety.twitch.tv/s/article/Reporting-a-User?language=en_US",
    "Amazon India": "https://www.amazon.in/gp/help/customer/display.html",
    "Flipkart": "https://www.flipkart.com/helpcentre",
    "Myntra": "https://www.myntra.com/contactus",
    "Meesho": "https://www.meesho.com/legal/privacy-policy",
    "Swiggy": "https://www.swiggy.com/support",
    "Zomato": "https://www.zomato.com/contact",
    "Paytm": "https://paytm.com/care",
    "PhonePe": "https://support.phonepe.com/",
}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "healthy", "engine": "ATLAS"}


def require_open_case(case_id: int) -> dict:
    case = get_research_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Research case not found.")
    if case["status"] != "open":
        raise HTTPException(status_code=409, detail="This research case is closed. Reopen it before collecting more sources.")
    return case


@app.get("/cases")
def list_cases():
    return get_research_cases()


@app.post("/cases", status_code=201)
def create_case(record: ResearchCaseCreate):
    try:
        return create_research_case(record)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The research case could not be created.") from exc


@app.patch("/cases/{case_id}")
def set_case_status(case_id: int, update: ResearchCaseStatusUpdate):
    try:
        result = update_research_case_status(case_id, update.status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The research case status could not be updated.") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Research case not found.")
    return result


@app.get("/cases/{case_id}/activity")
def list_case_activity(
    case_id: int,
    limit: int = Query(default=50, ge=1, le=200),
):
    if get_research_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Research case not found.")
    return get_case_activity(case_id, limit)


@app.post("/evidence")
def create_evidence(record: EvidenceRecord):
    try:
        require_open_case(record.case_id)
        return add_evidence(record)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The evidence record could not be saved.") from exc


@app.get("/evidence")
def list_evidence(
    status: Literal["unverified", "reviewed", "corroborated", "disputed"] | None = None,
    search: str | None = Query(default=None, max_length=200),
    case_id: int | None = Query(default=None, ge=1),
):
    return get_evidence(status=status, search=search, case_id=case_id)


@app.patch("/evidence/{evidence_id}/verification")
def verify_evidence(evidence_id: int, update: VerificationUpdate):
    try:
        result = update_verification(evidence_id, update)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The verification notes could not be saved.") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    return result


def run_and_save_search(query: str, limit: int, source_type: str, case_id: int):
    try:
        results = search_public_sources(query, limit)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="The public search provider could not complete the request.",
        ) from exc
    try:
        saved = save_search_results(results, case_id=case_id, search_query=query, source_type=source_type)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Search completed, but results could not be saved.",
        ) from exc
    try:
        record_case_activity(
            case_id,
            "public_search",
            f"Public search returned {len(results)} result(s); {saved['saved']} source(s) were saved.",
            {"provider": SEARCH_BACKEND, "result_count": len(results), "saved_count": saved["saved"]},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Search completed, but its case activity could not be recorded.") from exc
    return results, saved


@app.get("/search")
def public_search(
    q: str = Query(min_length=3, max_length=500),
    case_id: int = Query(ge=1),
    limit: int = Query(default=5, ge=1, le=25),
    save: bool = True,
):
    query = q.strip()
    require_open_case(case_id)
    if len(query) < 3:
        raise HTTPException(status_code=422, detail="Enter at least three non-space characters.")
    if save:
        results, saved = run_and_save_search(query, limit, "web_search", case_id)
    else:
        try:
            results = search_public_sources(query, limit)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="The public search provider could not complete the request.",
            ) from exc
        saved = {"saved": 0}
        try:
            record_case_activity(
                case_id,
                "public_search",
                f"Public search returned {len(results)} result(s); results were not saved.",
                {"provider": SEARCH_BACKEND, "result_count": len(results), "saved_count": 0},
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Search completed, but its case activity could not be recorded.") from exc
    return {
        "engine": "ATLAS",
        "provider": f"{SEARCH_BACKEND.title()} via DDGS",
        "case_id": case_id,
        "query": query,
        "results_count": len(results),
        "saved_to_database": saved["saved"],
        "results": results,
    }


@app.get("/research")
def multi_source_research(
    q: str = Query(min_length=3, max_length=500),
    case_id: int = Query(ge=1),
    limit: int = Query(default=5, ge=1, le=10),
    save: bool = True,
):
    """Search distinct public sources and report each source's coverage separately."""
    query = q.strip()
    require_open_case(case_id)
    if len(query) < 3:
        raise HTTPException(status_code=422, detail="Enter at least three non-space characters.")

    providers = [
        ("Yahoo web index", "yahoo", lambda: search_public_sources(query, limit)),
        ("Wikipedia", "wikipedia", lambda: search_wikipedia(query, limit)),
        ("Wikidata", "wikidata", lambda: search_wikidata(query, limit)),
    ]
    outcomes = {}
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        pending = {name: executor.submit(search_fn) for name, _, search_fn in providers}
        for name, _, _ in providers:
            try:
                outcomes[name] = {"results": pending[name].result(), "error": None}
            except Exception:
                outcomes[name] = {"results": [], "error": "Source temporarily unavailable."}

    all_results = []
    coverage = []
    for name, source_type, _ in providers:
        outcome = outcomes[name]
        source_results = outcome["results"]
        for result in source_results:
            result.setdefault("source", name)
            result.setdefault("source_type", source_type)
        saved_count = 0
        status = "unavailable" if outcome["error"] else ("results" if source_results else "no_results")
        if save and source_results:
            try:
                saved_count = save_search_results(
                    source_results,
                    case_id=case_id,
                    search_query=query,
                    source_type=source_type,
                )["saved"]
            except Exception:
                status = "save_failed"
                outcome["error"] = "Results found, but could not be saved."
        coverage.append({
            "source": name,
            "status": status,
            "result_count": len(source_results),
            "saved_count": saved_count,
            "note": outcome["error"] or (
                "This source returned no matching indexed items."
                if not source_results else
                ("Coverage is limited to pages indexed by this search service."
                 if name == "Yahoo web index" else
                 "Open knowledge candidates; a matching name is not proof of identity.")
            ),
        })
        all_results.extend(source_results)

    try:
        record_case_activity(
            case_id,
            "multi_source_search",
            f"Multi-source research returned {len(all_results)} result(s); {sum(item['saved_count'] for item in coverage)} source(s) were saved.",
            {
                "coverage": [
                    {"source": item["source"], "status": item["status"], "result_count": item["result_count"], "saved_count": item["saved_count"]}
                    for item in coverage
                ]
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Research completed, but its case activity could not be recorded.") from exc

    return {
        "case_id": case_id,
        "query": query,
        "results_count": len(all_results),
        "saved_to_database": sum(item["saved_count"] for item in coverage),
        "coverage": coverage,
        "results": all_results,
    }


@app.post("/exposure-check")
def exposure_check(
    request: ExposureCheckRequest,
    limit: int = Query(default=10, ge=1, le=25),
    save: bool = True,
):
    """Return redacted contact-detail alerts from public search snippets."""
    require_open_case(request.case_id)
    direct_check = {
        "status": "not_available",
        "message": "ATLAS has no approved direct connector for this platform yet. The separate web-index check still runs.",
        "profile_url": None,
    }
    if request.platform == "GitHub":
        direct_check = check_github_profile(request.username)

    query = f'site:{PLATFORM_DOMAINS[request.platform]} "{request.username}"'
    try:
        results, index_coverage = search_username_sources(query, limit, search_fn=search_public_sources)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="The public search provider could not complete the request.",
        ) from exc
    alerts = find_contact_categories(
        results, request.platform, PLATFORM_DOMAINS[request.platform]
    )
    if alerts:
        notice = "Possible contact details appeared in indexed snippets. Matches can be wrong; ATLAS keeps only the website, category, and reporting status."
    else:
        notice = "No email or phone pattern appeared in the checked snippets. This does not prove that no exposure exists."
    if save:
        try:
            saved = save_exposure_alerts(
                alerts, PLATFORM_REPORT_URLS[request.platform], request.case_id, request.platform
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="The redacted exposure alerts could not be saved.",
            ) from exc
    else:
        saved = alerts
        try:
            record_case_activity(
                request.case_id,
                "exposure_check",
                "A public account exposure check was completed; alerts were not saved.",
                {
                    "platform": request.platform,
                    "index_coverage": [
                        {"provider": item["provider"], "status": item["status"], "result_count": item["result_count"]}
                        for item in index_coverage
                    ],
                    "alerts_detected": len(alerts),
                    "alerts_saved": 0,
                },
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="The check completed, but its case activity could not be recorded.") from exc
    return {
        "platform": request.platform,
        "case_id": request.case_id,
        "provider": "Multiple web indexes via DDGS",
        "direct_check": direct_check,
        "index_check": {
            "status": "unavailable" if all(item["status"] == "unavailable" for item in index_coverage) else ("results" if results else "no_results"),
            "providers": index_coverage,
            "result_count": len(results),
            "note": (
                "These are pages returned by the listed search engines, not a complete scan of the platform."
                if results else
                "No listed search engine returned an indexed page. This is not proof the account or relevant pages do not exist."
            ),
        },
        "results_count": len(results),
        "alerts_detected": len(alerts),
        "alerts_saved": len(saved) if save else 0,
        "notice": notice,
        "alerts": saved,
    }


def check_github_profile(username: str) -> dict:
    """Check only public profile existence through GitHub's documented REST API."""
    endpoint = f"https://api.github.com/users/{username}"
    request = Request(endpoint, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ATLAS-public-account-check",
    })
    try:
        with urlopen(request, timeout=8) as response:
            profile = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return {"status": "not_found", "message": "GitHub returned no public profile for this username.", "profile_url": None}
        if exc.code in (403, 429):
            return {"status": "rate_limited", "message": "GitHub temporarily limited this lookup. Try again later.", "profile_url": None}
        return {"status": "unavailable", "message": "GitHub's profile service could not complete the lookup.", "profile_url": None}
    except (URLError, TimeoutError, ValueError, OSError):
        return {"status": "unavailable", "message": "GitHub's profile service could not be reached.", "profile_url": None}

    profile_url = profile.get("html_url")
    return {
        "status": "found" if profile_url else "unavailable",
        "message": "GitHub returned a public profile." if profile_url else "GitHub returned an incomplete profile response.",
        "profile_url": profile_url,
    }


@app.get("/exposure-alerts")
def list_exposure_alerts(
    status: Literal["needs_action", "reported", "removed", "false_positive"] | None = None,
    case_id: int | None = Query(default=None, ge=1),
):
    return get_exposure_alerts(status=status, case_id=case_id)


@app.patch("/exposure-alerts/{alert_id}")
def mark_exposure_alert(alert_id: int, update: ExposureAlertUpdate):
    try:
        result = update_exposure_alert(alert_id, update.status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The alert status could not be saved.") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Exposure alert not found.")
    return result
