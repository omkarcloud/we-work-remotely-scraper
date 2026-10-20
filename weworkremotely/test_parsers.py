"""Offline parser tests on saved pages (weworkremotely/fixtures, captured
2026-10-19). Run: python -m pytest weworkremotely/test_parsers.py -q"""
import os
from datetime import date

import pytest

from weworkremotely import parsers as P
from weworkremotely import refs

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
TODAY = date(2026, 10, 19)


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def test_card_dates():
    assert P.card_date("New", TODAY) == ("2026-10-19", 0, True)
    assert P.card_date("20d", TODAY) == ("2026-09-29", 20, False)
    assert P.card_date("Aug 5", TODAY) == ("2026-08-05", 75, False)
    assert P.card_date("Nov 2", TODAY)[0] == "2025-11-02"
    assert P.card_date(None) == (None, None, False)
    assert P.ago_to_days("Posted 17 days ago") == 17 and P.ago_to_days("about 2 hours ago") == 0
    assert P.human_date("Nov 1th, 2026") == "2026-11-01" and P.human_date("Nov 18th, 2026") == "2026-11-18"
    assert P.iso_from_ld("2026-10-19 07:31:28 UTC") == "2026-10-19T07:31:28Z"
    assert P.iso_from_rfc822("Mon, 19 Oct 2026 07:31:28 +0000") == "2026-10-19T07:31:28Z"
    assert P.flag_to_code("🇺🇸") == "US"


def test_listing_dates_renewed():
    # Databricks, 2026-10-20: created 2026-08-19, renewed twice (validThrough moves, datePosted does not)
    assert P.listing_dates("2026-08-19 21:30:04 UTC", "2026-11-17 21:30:04 UTC") == \
        ("2026-10-18T21:30:04Z", "2026-08-19T21:30:04Z", "2026-11-17T21:30:04Z", True)
    assert P.listing_dates(None, None) == (None, None, None, False)


def test_search_page_sections_and_cards():
    page = P.search_page(fixture("search_page.html"), TODAY)
    assert page["total_count"] == 2 and len(page["jobs"]) == 2 and page["is_truncated"] is False
    section = page["sections"][0]
    assert section["category"]["slug"] == "customer-support" and section["latest_post_days_ago"] == 4
    job = page["jobs"][0]
    assert job["slug"] == "emerging-travel-group-senior-python-developer-crm-ai-llm"
    assert job["link"] == refs.job_link(job["slug"]) and job["title"] == "Senior Python Developer (CRM - AI/LLM)"
    assert job["job_type"] == "full-time" and job["posted_days_ago"] == 4 and job["posted_date"] == "2026-10-15"
    assert job["company"] == {"name": "Emerging Travel Group", "slug": "emerging-travel-group",
                              "link": "https://weworkremotely.com/company/emerging-travel-group", "logo_link": None,
                              "headquarters": "Kazakhstan", "is_top_100": False}
    assert job["location"]["is_anywhere"] is True and job["location"]["regions"] == ["anywhere"]
    assert job["category"]["id"] == 7 and job["flags"]["is_featured"] is False


def test_filter_options():
    options = P.filter_options(fixture("search_page.html"))
    assert len(options["skills"]) == 670 and {"id": 144, "name": "Python"} in options["skills"]
    assert len(options["countries"]) == 249 and {"code": "US", "name": "United States of America"} in options["countries"]
    assert [s["key"] for s in options["salary_ranges"]] == ["10k-25k", "25k-49k", "50k-75k", "75k-100k", "100k+"]
    assert {"label": "All Programming", "ids": [2, 17, 18]} in options["category_filters"]


def test_landing_page_cards_flags_and_pagination():
    page = P.listing_page(fixture("landing_contract.html"), TODAY)
    assert page["title"] and len(page["jobs"]) == 25 and page["page_count"] == 2
    assert all(j["job_type"] == "contract" for j in page["jobs"])
    flagged = [j for j in page["jobs"] if j["flags"]["is_boosted"]]
    assert flagged and all(j["flags"]["is_featured"] for j in flagged[:1])
    with_countries = [j for j in page["jobs"] if j["location"]["countries"]]
    assert with_countries and all(len(c["code"]) == 2 and c["name"] for j in with_countries for c in j["location"]["countries"])


def test_job_page():
    job = P.job_page(fixture("job_page.html"), "humane-world-for-animals-web-designer-ecrm-1", TODAY)
    assert job["title"] == "Web Designer, eCRM" and job["job_type"] == "full-time"
    assert job["posted_at"] == "2026-10-02T17:39:45Z" and job["expires_at"] == "2026-11-01T17:39:45Z"
    assert job["first_posted_at"] == "2026-10-02T17:39:45Z" and job["is_renewed"] is False
    assert job["location"]["is_geolocked"] is False and job["facts"] is None
    assert job["apply_before"] == "2026-11-01" and job["posted_days_ago"] == 17
    assert job["salary_range"] == {"label": "$75,000 - $99,999 USD", "key": "75k-100k", "min": 75000, "max": 99999, "currency": "USD"}
    assert job["category"]["slug"] == "front-end-programming" and job["subcategory"] is None
    assert job["location"]["is_anywhere"] is True and job["location"]["applicant_countries_count"] == 249
    assert len(job["skills"]) == 18 and job["skills"][0] == {"name": "A/B Testing", "link": "https://weworkremotely.com/remote-a-b-testing-jobs"}
    assert job["description_html"].startswith("<p><em>The general salary range") and "Responsibilities" in job["description_text"]
    assert job["apply"] == {"link": None, "requires_account": True, "is_direct_apply": False}
    company = job["company"]
    assert company["name"] == "Humane World for Animals" and company["slug"] == "humane-world-for-animals"
    assert company["website_link"] == "https://humaneworld.org" and company["jobs_posted_count"] == 2
    assert company["logo_link"] == "https://we-work-remotely.imgix.net/logos/0171/6508/logo.gif"
    assert company["description_text"].startswith("Humane World for Animals works to end animal cruelty")
    assert len(job["related_jobs"]) == 3 and job["related_jobs"][0]["flags"]["is_hot"] is True


def test_company_page():
    company = P.company_page(fixture("company_page.html"), "stripe", TODAY)
    assert company["name"] == "Stripe" and company["website_link"] == "http://stripe.com" and company["is_top_100"] is True
    assert company["location"] == "Remote US" and company["jobs_posted_count"] == 6 and company["active_jobs_count"] == 6
    assert company["latest_post_days_ago"] == 8 and company["about_text"] is None and company["culture_text"] is None
    assert [c["slug"] for c in company["categories_hiring"]] == ["sales-and-marketing", "full-stack-programming"]
    assert len(company["jobs"]) == 6 and company["jobs"][0]["company"]["is_top_100"] is True


def test_top_companies():
    rows = P.top_companies(fixture("top_companies.html"))
    assert len(rows) == 10 and rows[0]["rank"] == 1 and rows[0]["name"] == "Lumenalta" and rows[0]["jobs_posted_count"] == 573
    assert rows[1]["slug"] == "contra" and rows[1]["is_actively_hiring"] is True and rows[0]["is_actively_hiring"] is False
    assert rows[0]["logo_link"] == "https://we-work-remotely.imgix.net/logos/0170/5076/logo.gif"


def test_feed():
    jobs = P.feed(fixture("feed.rss"))
    assert len(jobs) == 5
    first = jobs[0]
    assert first["slug"] == "expel-technical-account-manager" and first["title"] == "Technical Account Manager"
    assert first["company"]["name"] == "Expel" and first["company"]["headquarters"] == "Remote"
    assert first["posted_at"] == "2026-10-19T07:31:28Z" and first["expires_at"] == "2026-11-18T07:31:28Z"
    assert first["job_type"] == "full-time" and first["category"]["slug"] == "customer-support"
    assert first["description_html"].startswith("<p>You've spent") and "Headquarters" not in first["description_text"]
    designer = jobs[2]
    assert designer["skills"] == ["Product Designer", "Product Design"] and designer["category"]["slug"] == "design"


def test_refs_resolvers():
    assert refs.resolve_job("https://weworkremotely.com/listings/foo-bar") == "foo-bar"
    assert refs.resolve_company("https://weworkremotely.com/company/Stripe?x=1") == "stripe"
    assert [c["id"] for c in refs.resolve_category("programming")] == [2, 17, 18]
    assert refs.resolve_category("UX/UI Design")[0]["id"] == 20 and refs.resolve_category("remote-design-jobs")[0]["id"] == 1
    assert refs.parse_search_link("https://weworkremotely.com/remote-jobs/search?term=python&categories%5B%5D=2&sort=Past+Week") == \
        {"query": "python", "category": ["full-stack-programming"], "posted_within": "7d"}
    assert refs.parse_search_link("https://weworkremotely.com/remote-europe-jobs") == {"region": "europe"}
    assert refs.parse_search_link("weworkremotely.com/remote-python-jobs") == {"query": "python"}
    with pytest.raises(ValueError):
        refs.resolve_job("https://remoteok.com/remote-jobs/x")
    with pytest.raises(ValueError):
        refs.parse_search_link("https://weworkremotely.com/blog/some-post")
