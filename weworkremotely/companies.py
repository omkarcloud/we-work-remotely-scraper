"""/we-work-remotely/companies/* — one company's profile with every active
job, its jobs alone (category filter, paged) and the Top 100 remote
companies list.

A company page renders its whole active job list for an anonymous visitor
(no AJAX), so details is one page load. An unknown slug redirects to the
homepage, which fetch.py turns into a 404.
"""
from weworkremotely import parsers as P
from weworkremotely import refs
from weworkremotely.fetch import WeworkremotelyNotFound, get_page
from weworkremotely.jobs import PAGE_SIZE, _pagination, _slice


def _page(company):
    body, _ = get_page(f"/company/{company}", label=f"company {company}")
    profile = P.company_page(body, company)
    if not profile.get("name"):
        raise WeworkremotelyNotFound(f"company {company} not found")
    return profile


def details(company):
    return _page(company)


def jobs(company, category=None, page=1):
    page = int(page or 1)
    profile = _page(company)
    items = profile["jobs"]
    if category:
        wanted = refs.CATEGORY_BY_SLUG[category]["id"]
        ids = {i for i in (wanted, refs.SUBCATEGORY_PARENT.get(wanted)) if i is not None}
        items = [j for j in items if (j.get("category") or {}).get("id") in ids]
    return {"jobs": _slice(items, page),
            "company": {k: profile[k] for k in ("name", "slug", "link", "logo_link", "website_link", "location", "is_top_100",
                                                  "jobs_posted_count", "active_jobs_count")},
            "applied": {"category": category}, "pagination": _pagination(page, len(items))}


def top(limit=100):
    body, _ = get_page("/top-remote-companies", label="top companies")
    companies = P.top_companies(body)
    if limit:
        companies = companies[:int(limit)]
    return {"companies": companies, "count": len(companies), "link": refs.SITE + "/top-remote-companies"}
