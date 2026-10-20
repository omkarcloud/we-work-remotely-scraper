"""/we-work-remotely/categories, /skills, /countries, /filters,
/statistics — the site's reference lists and a snapshot of the whole board.

categories  the 12 categories with their site ids, groups, links, RSS feed
            links, the exact number of active jobs (the complete category
            pages, fetched in parallel) and when each was last posted to
skills      the 670 skills of the search form (id + name), optional filter
countries   the 249 countries of the search form (code + name)
filters     every accepted value of the search params
statistics  one pass over every active job (the 12 category pages): totals
            by category, job type, region, salary bucket, promotion flags,
            the companies with the most open roles, posting recency
"""
from collections import Counter

from weworkremotely.shared import memoized
from weworkremotely import parsers as P
from weworkremotely import refs
from weworkremotely.fetch import get_page, run_parallel
from weworkremotely.jobs import category_jobs, search_form

ALL_JOBS_TTL = 600


def all_jobs():
    """Every active job card of the board, by category (memoised 10 min)."""
    def load():
        slugs = [c["slug"] for c in refs.CATEGORIES if c["slug"] not in ("product-design", "ux-ui-design")]
        lists = run_parallel([lambda s=s: category_jobs(s) for s in slugs])
        return dict(zip(slugs, lists))
    return memoized("weworkremotely:all-jobs", load, ttl=ALL_JOBS_TTL)


def categories():
    body, _ = get_page("/", label="homepage")
    home = P.search_page(body)
    by_slug = {s["category"]["slug"]: s for s in home["sections"] if s["category"]}
    counts = all_jobs()
    items = []
    for cat in refs.CATEGORIES:
        sec = by_slug.get(cat["slug"]) or {}
        parent = cat["slug"] if cat["slug"] in counts else None
        items.append({
            "slug": cat["slug"], "id": cat["id"], "name": cat["name"], "group": cat["group"],
            "parent": "design" if cat["id"] in refs.SUBCATEGORY_PARENT else None,
            "link": refs.category_link(cat), "feed_link": refs.category_feed_link(cat),
            "active_jobs_count": len(counts[parent]) if parent else None,
            "latest_post_days_ago": sec.get("latest_post_days_ago"),
            "latest_post_label": sec.get("latest_post_label"),
        })
    return {"categories": items, "count": len(items), "total_active_jobs": home["total_count"]}


def _filtered(items, query, key):
    if not query:
        return items
    low = query.lower()
    return [i for i in items if low in (i.get(key) or "").lower()]


def skills(query=None):
    items = _filtered(search_form()["skills"], query, "name")
    return {"skills": items, "count": len(items), "applied": {"query": query}}


def countries(query=None):
    items = _filtered(search_form()["countries"], query, "name")
    return {"countries": items, "count": len(items), "applied": {"query": query}}


def filters():
    form = search_form()
    return {
        "categories": [{"slug": c["slug"], "id": c["id"], "name": c["name"], "group": c["group"]} for c in refs.CATEGORIES],
        "category_groups": refs.CATEGORY_GROUPS,
        "regions": [{"slug": k, "name": v[1], "label": v[2], "link": refs.SITE + v[0]} for k, v in refs.REGIONS.items()],
        "job_types": [{"slug": k, "name": v[1], "link": refs.SITE + v[0]} for k, v in refs.JOB_TYPES.items()],
        "salary_ranges": [{"key": k, "label": v[0], "min": v[1], "max": v[2], "currency": "USD"} for k, v in refs.SALARY_RANGES.items()],
        "posted_within": [{"key": k, "label": v} for k, v in refs.POSTED_WITHIN.items()],
        "filter": refs.PROMOTION_FILTERS,
        "skills_count": len(form["skills"]),
        "countries_count": len(form["countries"]),
        "notes": {
            "category": "comma list; a group (programming, design) expands to its members",
            "country": "comma list of ISO 3166-1 alpha-2 codes or country names; matches jobs open to that country",
            "salary_range": "comma list of the keys above (the site's five USD buckets)",
            "skills": "comma list of names or ids from /we-work-remotely/skills — the site's own skills filter is very "
                      "strict (0 results even for Python on 2026-10-19); prefer `query`",
            "region": "the region chip of a card (one value)",
            "query": "keywords, or any weworkremotely.com listing / search link",
        },
    }


def statistics():
    by_cat = all_jobs()
    jobs = {}
    for cards in by_cat.values():
        for job in cards:
            jobs.setdefault(job["slug"], job)
    jobs = list(jobs.values())
    regions, countries_c, companies = Counter(), Counter(), Counter()
    for job in jobs:
        for r in job["location"]["regions"]:
            regions[r] += 1
        for c in job["location"]["countries"]:
            countries_c[c["code"]] += 1
        if job["company"]["slug"]:
            companies[job["company"]["slug"]] += 1
    names = {j["company"]["slug"]: j["company"]["name"] for j in jobs if j["company"]["slug"]}
    recency = Counter()
    for job in jobs:
        d = job.get("posted_days_ago")
        bucket = "unknown" if d is None else "today" if d == 0 else "past_7_days" if d <= 7 else "past_14_days" if d <= 14 else "past_30_days" if d <= 30 else "older"
        recency[bucket] += 1
    return {
        "total_active_jobs": len(jobs),
        "by_category": {slug: len(cards) for slug, cards in by_cat.items()},
        "by_job_type": dict(Counter(j["job_type"] or "unknown" for j in jobs)),
        "by_region": dict(regions.most_common()),
        "by_country": [{"code": code, "name": next((c["name"] for j in jobs for c in j["location"]["countries"] if c["code"] == code), None), "count": n}
                       for code, n in countries_c.most_common(25)],
        "by_salary_range": dict(Counter((j["salary_range"] or {}).get("key") or "not_given" for j in jobs)),
        "by_recency": dict(recency),
        "flags": {"hot": sum(j["flags"]["is_hot"] for j in jobs), "boosted": sum(j["flags"]["is_boosted"] for j in jobs),
                  "featured": sum(j["flags"]["is_featured"] for j in jobs), "new_today": sum(j["flags"]["is_new"] for j in jobs),
                  "top_100_company": sum(j["company"]["is_top_100"] for j in jobs)},
        "top_hiring_companies": [{"slug": s, "name": names.get(s), "link": refs.company_link(s), "active_jobs_count": n}
                                 for s, n in companies.most_common(20)],
    }
