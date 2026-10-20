"""Live endpoint smoke tests: one call per /we-work-remotely/* route against
a running service, with example values proven to return data (2026-10-19).
The listing tooling reads each route's FIRST call from this file's AST as
its working example, so the values stay literals.

Skipped unless WEWORKREMOTELY_BASE points at a running service:

    SCRAPERS_PORT=6081 ONLY_SCRAPER=we-work-remotely python run.py
    WEWORKREMOTELY_BASE=http://127.0.0.1:6081 python -m pytest weworkremotely/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("WEWORKREMOTELY_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set WEWORKREMOTELY_BASE to run live endpoint tests")


def call(path, status=200, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=180)
    assert resp.status_code == status, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def _live_job():
    """Listings expire after 30 days, so job routes use a fresh one."""
    return call("/we-work-remotely/jobs/latest", limit=1)["jobs"][0]


def test_jobs_search():
    page = call("/we-work-remotely/jobs/search", query="engineer", category="programming", posted_within="14d")
    assert page["jobs"] and page["current_page"] == 1 and page["count"] == len(page["jobs"]) or page["total_pages"] > 1
    first = page["jobs"][0]
    assert first["slug"] and first["link"].startswith("https://weworkremotely.com/remote-jobs/") and first["company"]["slug"]
    assert first["category"]["slug"] in ("full-stack-programming", "front-end-programming", "back-end-programming")
    assert page["applied"]["posted_within"] == "14d" and page["site_total_count"] is not None
    # the whole board: every section recovered from the complete category pages, paged 50 at a time
    board = call("/we-work-remotely/jobs/search")
    assert board["count"] > 300 and board["is_truncated"] is False and len(board["jobs"]) == 50 and board["next"].endswith("page=2")
    # a country code or name, a salary bucket, hot jobs only, a region chip
    us = call("/we-work-remotely/jobs/search", country="United States")
    assert us["jobs"] and us["applied"]["country"] == ["US"]
    paid = call("/we-work-remotely/jobs/search", salary_range="100k+")
    assert paid["jobs"] and all(j["salary_range"]["key"] == "100k+" for j in paid["jobs"])
    hot = call("/we-work-remotely/jobs/search", filter="hot")
    assert hot["jobs"] and all(j["flags"]["is_hot"] for j in hot["jobs"])
    # a weworkremotely.com link as the query carries its own filters
    linked = call("/we-work-remotely/jobs/search", query="https://weworkremotely.com/categories/remote-design-jobs")
    assert linked["applied"]["category"] == ["design"] and linked["jobs"]
    call("/we-work-remotely/jobs/search", status=400, category="mars")
    call("/we-work-remotely/jobs/search", status=400, skills="NoSuchSkillXyz")


def test_jobs_latest():
    body = call("/we-work-remotely/jobs/latest", category="full-stack-programming", limit=5)
    assert body["count"] == 5 and all(j["category"]["slug"] == "full-stack-programming" for j in body["jobs"])
    assert body["jobs"][0]["posted_at"] and body["jobs"][0]["expires_at"] and body["jobs"][0]["description_text"]


def test_jobs_details():
    job = _live_job()
    body = call("/we-work-remotely/jobs/details", job=job["slug"])
    assert body["slug"] == job["slug"] and body["title"] == job["title"] and body["description_text"]
    assert body["posted_at"] and body["apply_before"] and body["category"]["slug"] and body["company"]["slug"]
    assert body["apply"]["requires_account"] is True and body["fetched_at"]
    by_link = call("/we-work-remotely/jobs/details", job=job["link"])
    assert by_link["slug"] == job["slug"]
    call("/we-work-remotely/jobs/details", status=404, job="this-job-does-not-exist-xyz")


def test_jobs_by_category():
    body = call("/we-work-remotely/jobs/by-category", category="sales-and-marketing", page=1)
    assert body["jobs"] and body["count"] >= len(body["jobs"]) and body["category"]["id"] == 9 and body["feed_link"].endswith(".rss")
    assert all(j["category"]["slug"] == "sales-and-marketing" for j in body["jobs"])


def test_jobs_by_region():
    body = call("/we-work-remotely/jobs/by-region", region="anywhere")
    assert len(body["jobs"]) == 50 and body["total_pages"] > 1 and body["next"].endswith("page=2")
    assert body["region"]["link"] == "https://weworkremotely.com/100-percent-remote-jobs"
    europe = call("/we-work-remotely/jobs/by-region", region="Europe")
    assert europe["region"]["slug"] == "europe"


def test_jobs_by_type():
    body = call("/we-work-remotely/jobs/by-type", job_type="contract")
    assert body["jobs"] and all(j["job_type"] == "contract" for j in body["jobs"])


def test_jobs_by_keyword():
    body = call("/we-work-remotely/jobs/by-keyword", keyword="python")
    assert body["keyword"]["link"] == "https://weworkremotely.com/remote-python-jobs" and body["keyword"]["title"]
    call("/we-work-remotely/jobs/by-keyword", status=404, keyword="zzqq-nothing")


def test_jobs_trending():
    body = call("/we-work-remotely/jobs/trending")
    assert len(body["jobs"]) == 50 and body["total_pages"] > 1


def test_companies_details():
    body = call("/we-work-remotely/companies/details", company="stripe")
    assert body["name"] == "Stripe" and body["is_top_100"] is True and body["website_link"] and body["jobs"]
    assert body["jobs"][0]["company"]["slug"] == "stripe" and body["categories_hiring"]
    by_link = call("/we-work-remotely/companies/details", company="https://weworkremotely.com/company/toptal")
    assert by_link["name"] == "Toptal" and by_link["about_text"]
    call("/we-work-remotely/companies/details", status=404, company="no-such-company-xyz-123")


def test_companies_jobs():
    body = call("/we-work-remotely/companies/jobs", company="toptal", category="full-stack-programming")
    assert body["company"]["name"] == "Toptal" and all(j["category"]["slug"] == "full-stack-programming" for j in body["jobs"])


def test_companies_top():
    body = call("/we-work-remotely/companies/top", limit=10)
    assert body["count"] == 10 and body["companies"][0]["rank"] == 1 and body["companies"][0]["jobs_posted_count"] > 100


def test_categories():
    body = call("/we-work-remotely/categories")
    assert body["count"] == 12 and body["total_active_jobs"] > 300
    full = next(c for c in body["categories"] if c["slug"] == "full-stack-programming")
    assert full["id"] == 2 and full["active_jobs_count"] > 0 and full["feed_link"].endswith(".rss")


def test_skills_countries_filters():
    assert call("/we-work-remotely/skills", query="python")["skills"] == [{"id": 144, "name": "Python"}]
    assert {"code": "US", "name": "United States of America"} in call("/we-work-remotely/countries", query="united")["countries"]
    body = call("/we-work-remotely/filters")
    assert len(body["regions"]) == 13 and len(body["salary_ranges"]) == 5 and body["skills_count"] > 600


def test_statistics():
    body = call("/we-work-remotely/statistics")
    assert body["total_active_jobs"] > 300 and body["by_category"]["full-stack-programming"] > 0
    assert body["flags"]["hot"] >= 0 and body["top_hiring_companies"][0]["active_jobs_count"] >= 1
