"""/we-work-remotely/jobs/* — job search with every filter the site has (and
any weworkremotely.com listing / search link accepted as the query), the
newest jobs from the RSS feeds, one job in full, and the site's own lists:
a category (complete), a region, a job type, a keyword page, trending.

How a search works (verified 2026-10-19): /remote-jobs/search answers every
match on ONE page grouped by category, but caps each category section at
~25 cards while `data-job-filter-count` carries the true total; `page=` is
ignored upstream. So:

  * the site is asked with the filters it understands (term, category ids,
    country codes, salary buckets, skill ids, time window, hot / boosted);
  * when a section is truncated AND the only filters set are ones we can
    apply ourselves (category, posted_within, filter, job_type, region) the
    complete category pages are fetched in parallel and filtered here, so
    the result set is whole;
  * `job_type` and `region` are always applied here (the site has no such
    search filter; they are chips on every card);
  * results are paged here, 50 a page, newest first; `is_truncated` says
    when the site held back matches we could not recover (a keyword / country
    / salary / skill search with more than ~25 hits in one category).

Skill names are resolved to the site's ids against the live option list
(memoised a day); an unknown name is a 400.
"""
from datetime import datetime, timezone

from weworkremotely.shared import memoized
from weworkremotely import parsers as P
from weworkremotely import refs
from weworkremotely.fetch import WeworkremotelyBadRequest, WeworkremotelyNotFound, gather, get_feed, get_page, run_parallel

PAGE_SIZE = 50
REGION_COUNTRY = {"usa": "US", "uk": "GB", "canada": "CA"}      # single-country regions show as a flag chip on cards
SKILLS_NOTE = ("the site's own skills filter is very strict: on 2026-10-19 it answered 0 jobs even for Python; "
               "search by keyword instead, or read skills from /jobs/details and /jobs/latest")
UPSTREAM_ONLY = ("query", "country", "salary_range", "skills")      # filters only the site can apply
FILTER_KEYS = ("query", "category", "country", "salary_range", "skills", "posted_within", "filter", "job_type", "region")


# ---- helpers ------------------------------------------------------------------------

def _pagination(page, total, per_page=PAGE_SIZE):
    pages = max(1, -(-total // per_page)) if total else 1
    return {"page": page, "items_per_page": per_page, "total_pages": pages, "total_count": total}


def _slice(items, page, per_page=PAGE_SIZE):
    start = (page - 1) * per_page
    return items[start:start + per_page]


def _newest_first(jobs):
    return sorted(jobs, key=lambda j: (j.get("posted_days_ago") is None, j.get("posted_days_ago") or 0))


def _applied(kw):
    return {key: kw.get(key) if kw.get(key) not in ("", []) else None for key in FILTER_KEYS}


def search_form():
    """The search form's option lists (skills, countries, salary buckets),
    memoised for a day."""
    def load():
        body, _ = get_page("/remote-jobs/search", {"term": "zzqxv-no-such-term"}, label="search form")
        return P.filter_options(body)
    return memoized("weworkremotely:search-form", load, ttl=86400)


def resolve_skill_ids(values):
    """Names or ids -> the site's skill ids. Unknown names are a 400."""
    if not values:
        return None
    options = None
    out, unknown = [], []
    for raw in values:
        raw = str(raw).strip()
        if raw.isdigit():
            out.append(int(raw))
            continue
        options = options or search_form()["skills"]
        hit = next((s for s in options if s["name"].lower() == raw.lower()), None)
        if hit is None:
            hit = next((s for s in options if refs.slugify(s["name"]) == refs.slugify(raw)), None)
        if hit is None:
            unknown.append(raw)
        else:
            out.append(hit["id"])
    if unknown:
        raise WeworkremotelyBadRequest("unknown skills: " + ", ".join(unknown) + " (see /we-work-remotely/skills)")
    return list(dict.fromkeys(out)) or None


def _category_ids(slugs):
    """Our slugs -> the site's checkbox ids. "All Design" (1) is exclusive
    with its subcategories upstream, so design drops product-design and
    ux-ui-design from the request (1 already covers them)."""
    slugs = list(slugs or [])
    if "design" in slugs:
        slugs = [s for s in slugs if s not in ("product-design", "ux-ui-design")]
    return [refs.CATEGORY_BY_SLUG[s]["id"] for s in slugs if s in refs.CATEGORY_BY_SLUG] or None


def upstream_params(kw):
    return {
        "term": kw.get("query"),
        "categories": _category_ids(kw.get("category")),
        "country": kw.get("country"),
        "salary_range": [refs.SALARY_RANGES[k][0] for k in (kw.get("salary_range") or [])] or None,
        "skills": kw.get("skill_ids"),
        "sort": refs.POSTED_WITHIN.get(kw.get("posted_within")) if kw.get("posted_within") not in (None, "any") else None,
        "job_filter": kw.get("filter") if kw.get("filter") in ("hot", "boosted") else None,
    }


def _passes(job, kw):
    """The client-side filters: job_type, region, posted_within, filter,
    category."""
    # card chips fold like the param does (part-time / freelance -> contract)
    if kw.get("job_type") and refs.JOB_TYPE_BY_LABEL.get(job.get("job_type"), job.get("job_type")) != kw["job_type"]:
        return False
    if kw.get("region"):
        loc = job.get("location") or {}
        codes = {c.get("code") for c in loc.get("countries", [])}
        wanted_code = REGION_COUNTRY.get(kw["region"])
        if kw["region"] not in loc.get("regions", []) and not (wanted_code and wanted_code in codes):
            return False
    days = refs.POSTED_WITHIN_DAYS.get(kw.get("posted_within"))
    if days is not None and ((job.get("posted_days_ago") is None) or job["posted_days_ago"] > days):
        return False
    if kw.get("filter") == "hot" and not job["flags"]["is_hot"]:
        return False
    if kw.get("filter") == "boosted" and not job["flags"]["is_boosted"]:
        return False
    if kw.get("category"):
        cat = job.get("category") or {}
        wanted = set(kw["category"])
        if cat.get("slug") not in wanted:
            # subcategories (product-design, ux-ui-design) roll up to design on cards
            if not (cat.get("slug") == "design" and wanted & {"product-design", "ux-ui-design"}):
                return False
    return True


def _merge_link(link, kw):
    """A parsed listing link's own filters fill the gaps of the explicit
    params (explicit values win)."""
    out = dict(kw)
    for key in FILTER_KEYS + ("page",):
        if out.get(key) in (None, [], "") and link.get(key) not in (None, [], ""):
            out[key] = link[key]
    return out


def category_jobs(slug):
    """The complete card list of one category page."""
    cat = refs.CATEGORY_BY_SLUG[slug]
    body, _ = get_page(f"/categories/{cat['site_slug']}", label=f"category {slug}")
    return P.listing_page(body)["jobs"]


def search(query=None, category=None, country=None, salary_range=None, skills=None, posted_within=None,
           filter=None, job_type=None, region=None, page=1):
    kw = {"query": query, "category": category, "country": country, "salary_range": salary_range, "skills": skills,
          "posted_within": posted_within, "filter": filter, "job_type": job_type, "region": region}
    if query and refs.is_link(query):
        kw["query"] = None
        kw = _merge_link(refs.parse_search_link(query), kw)
        # our own `page` drives paging (the site ignores a search link's page=);
        # honouring the link's page would pin every next / previous link to it
        kw.pop("page", None)
    page = int(page or 1)
    kw["skill_ids"] = resolve_skill_ids(kw.get("skills"))

    body, _ = get_page("/remote-jobs/search", upstream_params(kw), label="jobs search")
    result = P.search_page(body)
    jobs = result["jobs"]
    site_total = result["total_count"]
    recovered = False

    truncated_sections = [s for s in result["sections"] if s["is_truncated"] and s["category"]]
    if truncated_sections and not any(kw.get(k) for k in UPSTREAM_ONLY):
        # the complete category pages instead of the capped sections
        slugs = [s["category"]["slug"] for s in truncated_sections]
        full = run_parallel([lambda s=s: category_jobs(s) for s in slugs])
        replaced = {s for s in slugs}
        kept = [j for j in jobs if not (j.get("category") or {}).get("slug") in replaced]
        seen = {j["slug"] for j in kept}
        for cards in full:
            for job in cards:
                if job["slug"] not in seen:
                    seen.add(job["slug"])
                    kept.append(job)
        jobs = kept
        recovered = True

    jobs = _newest_first([j for j in jobs if _passes(j, kw)])
    total = len(jobs)
    is_truncated = bool(result["is_truncated"] and not recovered)
    kw.pop("skill_ids", None)
    applied = _applied(kw)
    if kw.get("skills") and not jobs:
        applied["note"] = SKILLS_NOTE
    return {
        "jobs": _slice(jobs, page),
        "applied": applied,
        "site_total_count": site_total,
        "is_truncated": is_truncated,
        "pagination": _pagination(page, total),
    }


def latest(category=None, since=None, limit=100):
    """The RSS feed (all jobs, or one category's feed): newest ~90 jobs with
    the full description, region / country, skills and expiry."""
    if category:
        cat = refs.CATEGORY_BY_SLUG[category]
        xml = get_feed(f"/categories/{cat['site_slug']}.rss", label=f"{category} feed")
    else:
        xml = get_feed("/remote-jobs.rss", label="feed")
    jobs = P.feed(xml)
    if since:
        jobs = [j for j in jobs if (j.get("posted_at") or "")[:10] >= since]
    if limit:
        jobs = jobs[:int(limit)]
    return {"jobs": jobs, "count": len(jobs), "applied": {"category": category, "since": since}}


def details(job):
    body, _ = get_page(f"/remote-jobs/{job}", label=f"job {job}")
    item = P.job_page(body, job)
    if not item.get("title"):
        raise WeworkremotelyNotFound(f"job {job} not found")
    item["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return item


# ---- the site's own lists ----------------------------------------------------------------------

def by_category(category, page=1):
    """One category, complete (the site renders every job of a category on
    one page), paged here."""
    page = int(page or 1)
    cat = refs.CATEGORY_BY_SLUG[category]
    body, _ = get_page(f"/categories/{cat['site_slug']}", label=f"category {category}")
    listing = P.listing_page(body)
    jobs = listing["jobs"]
    return {"jobs": _slice(jobs, page), "category": P.category_from_id(cat["id"]),
            "feed_link": refs.category_feed_link(cat), "latest_post_days_ago": listing["latest_post_days_ago"],
            "pagination": _pagination(page, len(jobs))}


def _landing(path, page, label):
    """A landing page with the site's own ?page=N (50 a page)."""
    body, _ = get_page(path, {"page": page} if page > 1 else None, label=label)
    listing = P.listing_page(body)
    jobs = listing["jobs"]
    page_count = listing["page_count"] or page
    if not jobs and page > 1:
        page_count = page - 1
    total = None if page_count > 1 or len(jobs) >= PAGE_SIZE else len(jobs)
    return listing, {"page": page, "items_per_page": PAGE_SIZE, "total_pages": max(page_count, page if jobs else 1), "total_count": total}


def by_region(region, page=1):
    page = int(page or 1)
    path, name, label = refs.REGIONS[region]
    listing, pagination = _landing(path, page, f"region {region}")
    return {"jobs": listing["jobs"], "region": {"slug": region, "name": name, "label": label, "link": refs.region_link(region)},
            "latest_post_days_ago": listing["latest_post_days_ago"], "pagination": pagination}


def by_type(job_type, page=1):
    page = int(page or 1)
    path, name = refs.JOB_TYPES[job_type]
    listing, pagination = _landing(path, page, f"{job_type} jobs")
    return {"jobs": listing["jobs"], "job_type": {"slug": job_type, "name": name, "link": refs.SITE + path},
            "latest_post_days_ago": listing["latest_post_days_ago"], "pagination": pagination}


def by_keyword(keyword, page=1):
    """The site's /remote-<keyword>-jobs pages (python, react, qa, writer, …)."""
    page = int(page or 1)
    slug = refs.slugify(keyword)
    if not slug:
        raise WeworkremotelyBadRequest("keyword is empty")
    listing, pagination = _landing(f"/remote-{slug}-jobs", page, f"keyword {slug}")
    return {"jobs": listing["jobs"], "keyword": {"slug": slug, "name": keyword, "title": listing["title"], "link": refs.keyword_link(keyword)},
            "latest_post_days_ago": listing["latest_post_days_ago"], "pagination": pagination}


def trending(page=1):
    page = int(page or 1)
    listing, pagination = _landing("/top-trending-remote-jobs", page, "trending jobs")
    return {"jobs": listing["jobs"], "pagination": pagination}
