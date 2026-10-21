"""We Work Remotely normalizers: the site's job cards, search / category /
landing pages, job pages (JSON-LD + sidebar), company pages, the Top 100
list, the search form's option lists and the RSS feeds -> the shapes the
/we-work-remotely/* routes return.

Conventions: snake_case keys, `link` not `url`, booleans as questions
(`is_hot`), null for missing, amounts as numbers + `currency`, identity
fields first, nested objects after the main content, metadata last.

A job CARD (search rows, category / landing / company lists, related jobs):

    {slug, title, link, job_type, posted_date, posted_days_ago,
     salary_range: {label, min, max, currency} | null,
     location: {is_anywhere, regions: [slug], region_labels: [..],
                countries: [{code, name}], places: [..]},
     company: {name, slug, link, logo_link, headquarters, is_top_100},
     category: {id, slug, name, link},
     flags: {is_featured, is_boosted, is_hot, is_pinned, is_new}}

A JOB PAGE adds posted_at (the current 30-day posting) / first_posted_at
(the listing's original creation) / is_renewed / expires_at / apply_before,
subcategory, skills, description_html / description_text,
apply (the site gates the employer's apply link behind a free account —
apply.requires_account tells so), the company panel and related_jobs.

Intentionally skipped from the raw data (and why):
  * JSON-LD `@context` / `@type` / `jobLocationType` (TELECOMMUTE) / `url`
    (always the homepage) / `hiringOrganization.sameAs` when it is the
    homepage placeholder: constants.
  * JSON-LD `applicantLocationRequirements` as a 249-country list: emitted as
    `is_anywhere` + the explicit list only when it is a real restriction.
  * JSON-LD `baseSalary`: 0/0 when no salary was given, and otherwise the
    chosen bucket's FLOOR copied into both minValue and maxValue (a
    "$75,000 - $99,999" job carries 75000/75000) — not a published amount,
    so only the sidebar bucket is emitted (`salary_range`).
  * JSON-LD `description`: an HTML-escaped copy of the page description.
  * JSON-LD `identifier`: the slug again.
  * the "AI Auto-Apply" / "Save job" buttons, the job-copilot upsell, the
    promoted ad cards (`promoted-listing`, listing-ad asides), share widgets,
    email-protection links, RSS icons, the "View Company Profile" tooltips.
  * `data-promoted-listing-id`, `data-listing-ad-*`, tracking query strings.
  * the site's "AI Auto-Apply" and account-register links.
"""
import html as html_lib
import json
import re
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from weworkremotely.shared import strip_html, text, to_int
from weworkremotely import refs
from weworkremotely.countries import COUNTRY_NAMES

_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_BG_RE = re.compile(r"url\((['\"]?)(.*?)\1\)", re.S)
_DAYS_RE = re.compile(r"^(\d+)\s*d$", re.I)
_MONTH_DAY_RE = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})$")
_AGO_RE = re.compile(r"(?:about\s+|over\s+|almost\s+|less than\s+)?(an?|\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", re.I)
_NUMBER_RE = re.compile(r"\d[\d,]*")
_FLAG_RE = re.compile(r"^((?:[\U0001F1E6-\U0001F1FF]){2})\s*(.*)$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_ABOUT = "we're sure there's lots more to know"
_PLACEHOLDER_PANELS = ("no culture details", "no benefits listed", "no hiring process details", "nothing shared yet")
_CATEGORY_HREF_RE = re.compile(r"^/categories/([a-z0-9-]+)")
_FEED_HQ_RE = re.compile(r"^\s*<p>\s*<strong>\s*Headquarters:\s*</strong>(.*?)</p>", re.S | re.I)

LISTING_DAYS = 30      # "We Work Remotely job postings last 30 days and automatically renew" (FAQ)

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


# ---- small helpers ------------------------------------------------------------------

def soup(markup):
    return BeautifulSoup(markup or "", "lxml")


def node_text(node):
    if node is None:
        return None
    return text(node.get_text(" ", strip=True))


def _own_text(node):
    """A node's direct text (children's text excluded)."""
    if node is None:
        return None
    return text(" ".join(s for s in node.find_all(string=True, recursive=False)))


def _bg_image(node):
    style = (node.get("style") if node is not None else None) or ""
    match = _BG_RE.search(style)
    return html_lib.unescape(match.group(2)) if match else None


def logo_link(value):
    """The imgix thumbnail link -> the stored original (no resize params)."""
    if not value:
        return None
    return value.split("?")[0] if "imgix.net" in value else value


def _first_number(value):
    match = _NUMBER_RE.search(value or "")
    return to_int(match.group(0)) if match else None


def _slug_from_href(href, marker):
    if not href or marker not in href:
        return None
    tail = href.split(marker, 1)[1]
    return tail.split("?")[0].split("#")[0].strip("/").lower() or None


def flag_to_code(flag):
    """🇺🇸 -> US."""
    try:
        return "".join(chr(ord(ch) - 0x1F1E6 + ord("A")) for ch in flag)
    except (TypeError, ValueError):
        return None


def iso_from_ld(value):
    """'2026-10-19 07:31:28 UTC' -> '2026-10-19T07:31:28Z'."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_from_rfc822(value):
    """'Mon, 19 Oct 2026 07:31:28 +0000' -> '2026-10-19T07:31:28Z'."""
    if not isinstance(value, str) or not value.strip():
        return None
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def listing_dates(date_posted, valid_through):
    """JSON-LD datePosted / validThrough -> (posted_at, first_posted_at,
    expires_at, is_renewed). A listing runs 30 days and auto-renews; the
    JSON-LD keeps the ORIGINAL creation date while validThrough moves with
    every renewal, so the current posting is validThrough - 30 days."""
    first = iso_from_ld(date_posted)
    expires = iso_from_ld(valid_through)
    posted = first
    if expires:
        current = (datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ") - timedelta(days=LISTING_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not first or current > first:
            posted = current
    is_renewed = bool(first and posted and posted[:10] > first[:10])
    return posted, first, expires, is_renewed


def human_date(value, today=None):
    """'Nov 1th, 2026' / 'Nov 18th, 2026' -> '2026-11-01'."""
    if not value:
        return None
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value.strip())
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def card_date(label, today=None):
    """The card's date chip -> (posted_date, posted_days_ago, is_new).
    'New' = today, '20d' = 20 days ago, 'Aug 5' = that day (this year, or
    last year when that would be in the future)."""
    today = today or date.today()
    raw = text(label or "")
    if not raw:
        return None, None, False
    if raw.lower() == "new":
        return today.isoformat(), 0, True
    match = _DAYS_RE.match(raw)
    if match:
        days = int(match.group(1))
        return (today - timedelta(days=days)).isoformat(), days, False
    match = _MONTH_DAY_RE.match(raw)
    if match and match.group(1) in MONTHS:
        month, day = MONTHS[match.group(1)], int(match.group(2))
        try:
            when = date(today.year, month, day)
            if when > today:
                when = date(today.year - 1, month, day)
        except ValueError:
            return None, None, False
        return when.isoformat(), (today - when).days, False
    return None, None, False


def ago_to_days(value):
    """'Posted 17 days ago' / 'about 2 hours ago' / 'Latest post 8 days ago'
    -> days (0 for hours / minutes)."""
    match = _AGO_RE.search(value or "")
    if not match:
        return None
    count = 1 if match.group(1).lower() in ("a", "an") else int(match.group(1))
    unit = match.group(2).lower()
    return {"minute": 0, "hour": 0, "day": count, "week": count * 7, "month": count * 30, "year": count * 365}[unit]


# ---- categories ---------------------------------------------------------------------------

def category_from_id(value):
    cat = refs.CATEGORY_BY_ID.get(to_int(value))
    if cat is None:
        return None
    return {"id": cat["id"], "slug": cat["slug"], "name": cat["name"], "link": refs.category_link(cat)}


def category_from_href(href):
    match = _CATEGORY_HREF_RE.match(href or "")
    if not match:
        return None
    cat = refs.CATEGORY_BY_SITE_SLUG.get(match.group(1).removesuffix(".rss"))
    return category_from_id(cat["id"]) if cat else None


def category_from_name(name):
    try:
        return category_from_id(refs.resolve_category(name)[0]["id"])
    except ValueError:
        return None


# ---- job cards --------------------------------------------------------------------------------

def job_type_slug(label):
    """'Full-Time' / 'Contract' / 'Part-Time' -> 'full-time' / 'contract' / 'part-time'."""
    if not label:
        return None
    return refs.slugify(label) or None


def _salary_from_label(label):
    key = refs.SALARY_BY_LABEL.get((label or "").lower().replace(" ", ""))
    if not key:
        return None
    site_label, low, high = refs.SALARY_RANGES[key]
    return {"label": site_label, "key": key, "min": low, "max": high, "currency": "USD"}


def _location_from_tags(tags):
    regions, labels, countries, places = [], [], [], []
    for tag in tags:
        flag = _FLAG_RE.match(tag)
        if flag:
            code = flag_to_code(flag.group(1))
            name = text(flag.group(2)) or COUNTRY_NAMES.get(code)
            countries.append({"code": code, "name": name})
            continue
        slug = refs.REGION_BY_LABEL.get(tag.lower())
        if slug:
            regions.append(slug)
            labels.append(tag)
        else:
            places.append(tag)
    return {"is_anywhere": "anywhere" in regions, "regions": regions, "region_labels": labels,
            "countries": countries, "places": places}


def job_card(li, today=None):
    """One `li.new-listing-container` -> job card dict (None for the
    promoted ad cards)."""
    classes = li.get("class") or []
    if "promoted-listing" in classes:
        return None
    link_node = li.select_one("a.listing-link--unlocked, a.listing-link--locked, a[href^='/remote-jobs/']")
    href = link_node.get("href") if link_node else None
    slug = _slug_from_href(href, "/remote-jobs/")
    if not slug:
        return None
    title = node_text(li.select_one(".new-listing__header__title__text")) or node_text(li.select_one(".new-listing__header__title"))
    company_a = li.select_one(".tooltip--flag-logo a[href^='/company/']") or li.select_one("a[href^='/company/']")
    company_slug = _slug_from_href(company_a.get("href") if company_a else None, "/company/")
    logo = _bg_image(li.select_one(".tooltip--flag-logo__flag-logo, .flag-logo"))
    company_name = _own_text(li.select_one(".new-listing__company-name")) or node_text(li.select_one(".new-listing__company-name"))
    hq = _own_text(li.select_one(".new-listing__company-headquarters"))
    date_label = node_text(li.select_one(".new-listing__header__icons__date"))
    posted_date, days_ago, is_new = card_date(date_label, today)

    job_type = salary = None
    plain_tags, is_top_100, is_featured_tag, is_boosted_tag = [], False, False, False
    for p in li.select(".new-listing__categories__category"):
        label = node_text(p)
        pcls = " ".join(p.get("class") or [])
        if not label:
            continue
        if "--top-company" in pcls or label.lower() == "top 100":
            is_top_100 = True
        elif "--featured" in pcls or label.lower() == "featured":
            is_featured_tag = True
        elif "--boosted" in pcls or label.lower() == "boosted":
            is_boosted_tag = True
        elif label.lower() in refs.JOB_TYPE_LABELS:
            job_type = job_type_slug(label)
        elif _salary_from_label(label):
            salary = _salary_from_label(label)
        else:
            plain_tags.append(label)
    if li.select_one(".highlight-bar--top-company"):
        is_top_100 = True
    category = category_from_id(li.get("data-category"))
    return {
        "slug": slug,
        "title": title,
        "link": refs.job_link(slug),
        "job_type": job_type,
        "posted_date": posted_date,
        "posted_days_ago": days_ago,
        "salary_range": salary,
        "location": _location_from_tags(plain_tags),
        "company": {"name": company_name, "slug": company_slug,
                    "link": refs.company_link(company_slug) if company_slug else None,
                    "logo_link": logo_link(logo), "headquarters": hq, "is_top_100": is_top_100},
        "category": category,
        "flags": {"is_featured": "feature" in classes or is_featured_tag,
                  "is_boosted": "boosted" in classes or is_boosted_tag or li.select_one(".new-listing__header__icons__boostedIcon") is not None,
                  "is_hot": li.select_one(".new-listing__header__title__hot-icon") is not None,
                  "is_pinned": li.select_one(".new-listing__header__icons__pinnedIcon") is not None,
                  "is_new": is_new},
    }


def job_cards(container, today=None):
    out, seen = [], set()
    if container is None:
        return out
    for li in container.select("li.new-listing-container"):
        card = job_card(li, today)
        if card and card["slug"] not in seen:
            seen.add(card["slug"])
            out.append(card)
    return out


# ---- listing pages (search / homepage / category / landing) ---------------------------------------

def _section(sec, today=None):
    h2 = sec.select_one("article > h2") or sec.select_one("h2")
    cat_link = h2.select_one("a[href^='/categories/']") if h2 else None
    category = category_from_href(cat_link.get("href")) if cat_link else None
    if category is None and sec.get("id", "").startswith("category-"):
        category = category_from_id(sec["id"].split("-", 1)[1])
    title = node_text(cat_link) if cat_link else (_own_text(h2) if h2 else None)
    latest = node_text(sec.select_one(".latest_post"))
    view_all = sec.select_one("a.view-all, a[href^='/categories/']:-soup-contains('View all')")
    if view_all is None:
        for a in sec.select("a[href^='/categories/']"):
            if "view all" in (node_text(a) or "").lower():
                view_all = a
                break
    return {
        "category": category,
        "title": title,
        "latest_post_label": latest.replace("Latest post", "").strip() if latest else None,
        "latest_post_days_ago": ago_to_days(latest),
        "is_truncated": view_all is not None,
        "view_all_link": refs.absolute(view_all.get("href")) if view_all else None,
        "jobs": job_cards(sec, today),
    }


def search_page(markup, today=None):
    """/remote-jobs/search or the homepage -> {total_count, sections,
    jobs (flat, promoted ads dropped), skills/countries/salary option lists}."""
    doc = soup(markup)
    counts = [to_int(n.get_text()) for n in doc.select("[data-job-filter-count]") if to_int(n.get_text()) is not None]
    total = counts[0] if counts else None
    root = doc.select_one("#search-results") or doc
    sections = [_section(sec, today) for sec in root.select("section.jobs")]
    sections = [s for s in sections if s["category"] or s["jobs"]]     # drops the "Free jobs by Toptal" promo section
    flat, seen = [], set()
    for sec in sections:
        for job in sec["jobs"]:
            if job["slug"] not in seen:
                seen.add(job["slug"])
                flat.append(job)
    return {"total_count": total, "sections": sections, "jobs": flat,
            "is_truncated": any(s["is_truncated"] for s in sections) or (total is not None and len(flat) < total)}


def listing_page(markup, today=None):
    """A category / region / job-type / keyword / trending page -> {title,
    jobs, latest_post_days_ago, page_count (from the pagination links)}."""
    doc = soup(markup)
    h1 = doc.select_one("h1")
    heading = node_text(h1)
    latest = node_text(doc.select_one(".latest_post"))
    pages = [to_int(m.group(1)) for a in doc.select("a[href*='page=']")
             for m in [re.search(r"[?&]page=(\d+)", a.get("href") or "")] if m]
    current = doc.select_one(".pagination .current, .pagination .active, nav.pagination em")
    container = doc.select_one(".jobs-container") or doc.select_one("#job_list") or doc
    return {"title": heading, "latest_post_label": latest.replace("Latest post", "").strip() if latest else None,
            "latest_post_days_ago": ago_to_days(latest), "jobs": job_cards(container, today),
            "page_count": max(pages) if pages else None, "current_page_label": node_text(current)}


def filter_options(markup):
    """The search form's option lists -> {skills: [{id, name}], countries:
    [{code, name}], salary_ranges: [{label, key, min, max}], categories}."""
    doc = soup(markup)
    skills = []
    seen = set()
    for opt in doc.select("select[name='skills[]'] option"):
        sid, name = to_int(opt.get("value")), node_text(opt)
        if sid is not None and name and sid not in seen:
            seen.add(sid)
            skills.append({"id": sid, "name": name})
    skills.sort(key=lambda s: s["name"].lower())
    countries = []
    for opt in doc.select("select[name='country[]'] option"):
        code, label = (opt.get("value") or "").strip().upper(), node_text(opt)
        if len(code) == 2 and label:
            flag = _FLAG_RE.match(label)
            countries.append({"code": code, "name": text(flag.group(2)) if flag else label})
    salaries = []
    for opt in doc.select("select[name='salary_range[]'] option"):
        sal = _salary_from_label(opt.get("value") or node_text(opt))
        if sal:
            salaries.append(sal)
    categories = []
    for node in doc.select("[data-category-ids][data-category-label]"):
        ids = [to_int(x) for x in (node.get("data-category-ids") or "").split(",") if to_int(x) is not None]
        categories.append({"label": node.get("data-category-label"), "ids": ids})
    return {"skills": skills, "countries": countries, "salary_ranges": salaries, "category_filters": categories}


# ---- job page -----------------------------------------------------------------------------------

def _load_ld(markup):
    for raw in _LD_RE.findall(markup or ""):
        try:
            data = json.loads(raw, strict=False)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return {}


def _salary_from_ld(ld):
    base = (ld or {}).get("baseSalary") or {}
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return None
    low, high = to_int(value.get("minValue")), to_int(value.get("maxValue"))
    if not low and not high:
        return None
    unit = (value.get("unitText") or "").upper()
    return {"min": low or None, "max": high or None, "currency": base.get("currency") or "USD",
            "period": {"YEAR": "year", "MONTH": "month", "HOUR": "hour", "WEEK": "week", "DAY": "day"}.get(unit, unit.lower() or None)}


def _sidebar_facts(doc):
    """The 'About the job' list -> {label_key: {"text": .., "values": [..],
    "links": [..]}}."""
    facts = {}
    for li in doc.select(".lis-container__job__sidebar__job-about__list__item"):
        label = _own_text(li)
        if not label:
            continue
        key = refs.slugify(label).replace("-", "_")
        values = [node_text(b) for b in li.select(".box, span") if node_text(b)]
        values = [v for v in values if v]
        if not values:
            values = [node_text(li).replace(label, "", 1).strip()] if node_text(li) else []
        links = [refs.absolute(a.get("href")) for a in li.select("a[href]") if a.get("href")]
        facts[key] = {"label": label, "values": list(dict.fromkeys(v for v in values if v)), "links": links}
    return facts


def job_page(markup, slug, today=None):
    doc = soup(markup)
    ld = _load_ld(markup)
    facts = _sidebar_facts(doc)

    def fact(key):
        return (facts.get(key) or {}).get("values") or []

    hero = doc.select_one(".lis-container__header__hero")
    title = node_text(doc.select_one("h1.lis-container__header__hero__company-info__title")) or text(ld.get("title")) or node_text(doc.select_one("h1"))
    nav_cat = doc.select_one(".lis-container__header__navigation__tab--category")
    category = category_from_href(nav_cat.get("href") if nav_cat else None) or category_from_name((fact("category") or [None])[0])
    subcategory = (fact("subcategory") or [None])[0]

    # company panel
    panel = doc.select_one(".lis-container__job__sidebar__companyDetails")
    company_a = (panel.select_one("a[href^='/company/']") if panel else None) or (hero.select_one("a[href^='/company/']") if hero else None)
    company_slug = _slug_from_href(company_a.get("href") if company_a else None, "/company/")
    org = ld.get("hiringOrganization") if isinstance(ld.get("hiringOrganization"), dict) else {}
    company_name = node_text(panel.select_one(".lis-container__job__sidebar__companyDetails__info__title h3")) if panel else None
    company_name = company_name or text(org.get("name"))
    logo = _bg_image(panel.select_one(".lis-container__header__hero__company-logo") if panel else None) or \
        _bg_image(hero.select_one(".lis-container__header__hero__company-logo") if hero else None) or org.get("logo")
    website = org.get("sameAs")
    if website and "weworkremotely.com" in website:
        website = None
    hq = text(org.get("address"))
    if hq and company_name and hq.lower() == company_name.lower():
        hq = None
    blurb = hero.select_one(".lis-container__header__hero__company-info__description") if hero else None
    jobs_posted = _first_number(node_text(panel.select_one(".lis-container__job__sidebar__companyDetails__info__jobs-posted")) if panel else None)

    # description
    desc_node = doc.select_one(".lis-container__job__content__description")
    description_html = None
    if desc_node is not None:
        for hr in desc_node.select("hr.lis-container__job__content__description__hr"):
            hr.decompose()
        description_html = desc_node.decode_contents().strip() or None
    description_text = strip_html(description_html) if description_html else strip_html(html_lib.unescape(ld.get("description") or ""))

    # apply
    apply_a = doc.select_one("a.apply-btn, a#job-cta-alt, a#job-cta")
    apply_href = apply_a.get("href") if apply_a else None
    requires_account = bool(apply_href and ("/job-seekers/account" in apply_href or "apply-btn--locked" in " ".join(apply_a.get("class") or [])))
    apply_link = None if (requires_account or not apply_href) else refs.absolute(apply_href)

    # location
    countries = [c.get("name") for c in (ld.get("applicantLocationRequirements") or []) if isinstance(c, dict) and c.get("name")]
    region_tags = fact("region")
    location = _location_from_tags(region_tags)
    is_anywhere = location["is_anywhere"] or len(countries) >= 240
    location["is_anywhere"] = is_anywhere
    location["countries"] = location["countries"] or ([] if is_anywhere else [{"code": c, "name": COUNTRY_NAMES.get(c)} for c in countries])
    location["applicant_countries_count"] = len(countries) or None
    country_fact = fact("country")
    location["is_geolocked"] = any("geolocked" in (v or "").lower() for v in country_fact)
    if not location["countries"]:
        flagged = _location_from_tags([v for v in country_fact if _FLAG_RE.match(v or "")])["countries"]
        location["countries"] = flagged

    # skills (links to /remote-jobs-<slug>, which the site 301s to /remote-<slug>-jobs)
    skills = []
    skills_li = next((li for li in doc.select(".lis-container__job__sidebar__job-about__list__item") if (_own_text(li) or "").lower() == "skills"), None)
    if skills_li is not None:
        for a in skills_li.select("a[href]"):
            name = node_text(a)
            if name:
                skills.append({"name": name, "link": refs.keyword_link(name)})
    if not skills and fact("skills"):
        skills = [{"name": v, "link": None} for v in fact("skills")]

    posted_label = (fact("posted_on") or [None])[0] or node_text(hero.select_one(".lis-container__header__hero__company-info__icons__item") if hero else None)
    posted_at, first_posted_at, expires_at, is_renewed = listing_dates(ld.get("datePosted"), ld.get("validThrough"))
    apply_before = human_date((fact("apply_before") or [None])[0]) or (expires_at[:10] if expires_at else None)
    job_type_label = (fact("job_type") or [None])[0] or text(ld.get("employmentType"))
    salary_label = (fact("salary") or [None])[0]
    related = doc.select_one("#job_list")

    return {
        "slug": slug,
        "title": title,
        "link": refs.job_link(slug),
        "job_type": job_type_slug(job_type_label),
        "posted_at": posted_at,
        "posted_days_ago": ago_to_days(posted_label) if posted_label else None,
        "first_posted_at": first_posted_at,
        "is_renewed": is_renewed,
        "expires_at": expires_at,
        "apply_before": apply_before,
        "salary_range": _salary_from_label(salary_label),
        "category": category,
        "subcategory": subcategory,
        "location": location,
        "skills": skills,
        "description_html": description_html,
        "description_text": description_text,
        "apply": {"link": apply_link, "requires_account": requires_account,
                  "is_direct_apply": str(ld.get("directApply", "")).lower() == "true"},
        "company": {"name": company_name, "slug": company_slug,
                    "link": refs.company_link(company_slug) if company_slug else None,
                    "website_link": website, "logo_link": logo_link(logo), "headquarters": hq,
                    "description_html": (blurb.decode_contents().strip() or None) if blurb else None,
                    "description_text": strip_html(blurb.decode_contents()) if blurb else None,
                    "jobs_posted_count": jobs_posted},
        "related_jobs": job_cards(related, today),
        "facts": {k: v["values"] for k, v in facts.items() if k not in ("posted_on", "apply_before", "job_type", "salary", "category", "subcategory", "region", "country", "skills")} or None,
    }


# ---- company page -------------------------------------------------------------------------------

def _panel_text(node, placeholders=(), heading=None):
    """A profile panel -> (html, text); None/None for the site's "nothing
    shared yet" placeholders and for a panel that holds only its own heading
    and empty bullets ("Benefits\n-")."""
    if node is None:
        return None, None
    inner = node.decode_contents().strip()
    plain = strip_html(inner)
    if not plain:
        return None, None
    low = plain.lower()
    if any(p in low for p in placeholders):
        return None, None
    lines = [ln.strip() for ln in plain.splitlines()]
    lines = [ln for ln in lines if ln and ln not in ("-", "•")]
    if lines and heading and lines[0].lower() == heading.lower():
        lines = lines[1:]          # the panel repeats its own heading ("Benefits") as its first line
    if not lines:
        return None, None
    return inner, "\n".join(lines)


def company_page(markup, slug, today=None):
    doc = soup(markup)
    card = doc.select_one(".company-show-card")
    name = node_text(card.select_one(".company-show-card__name") if card else None) or node_text(doc.select_one("h1"))
    logo = card.select_one("img.company-show-card__logo") if card else None
    site_a = card.select_one("a.company-show-card__url") if card else None
    about_html, about_text = _panel_text(card.select_one(".company-show-card__about p") if card else None, (_PLACEHOLDER_ABOUT,))
    panels = {}
    for sec in doc.select(".company-modal__panel"):
        key = sec.get("data-panel") or refs.slugify(node_text(sec.select_one(".company-modal__panel-title")))
        body = sec.select_one(".company-modal__body-text") or sec
        panels[key] = _panel_text(body, _PLACEHOLDER_PANELS + (_PLACEHOLDER_ABOUT,), heading=key)
    if "about" in panels and panels["about"][0] and not about_html:
        about_html, about_text = panels["about"]

    jobs_sec = doc.select_one(".company-jobs")
    active = _first_number(node_text(jobs_sec.select_one(".company-jobs__count")) if jobs_sec else None)
    latest = node_text(jobs_sec.select_one(".company-jobs__latest")) if jobs_sec else None
    hiring_in = []
    for b in (jobs_sec.select(".company-jobs__filter[data-filter]") if jobs_sec else []):
        cat = category_from_id(b.get("data-filter"))
        if cat:
            hiring_in.append(cat)
    jobs = job_cards(jobs_sec or doc, today)
    return {
        "name": name,
        "slug": slug,
        "link": refs.company_link(slug),
        "website_link": site_a.get("href") if site_a else None,
        "logo_link": logo_link(logo.get("src")) if logo else None,
        "location": node_text(card.select_one(".company-show-card__location") if card else None),
        "is_top_100": bool(card and card.select_one(".company-show-card__top100-badge")),
        "jobs_posted_count": _first_number(node_text(card.select_one(".company-show-card__jobs-count") if card else None)),
        "active_jobs_count": active if active is not None else len(jobs),
        "latest_post_label": latest.replace("Latest post", "").strip() if latest else None,
        "latest_post_days_ago": ago_to_days(latest),
        "about_html": about_html,
        "about_text": about_text,
        "culture_text": (panels.get("culture") or (None, None))[1],
        "benefits_text": (panels.get("benefits") or (None, None))[1],
        "hiring_process_text": (panels.get("hiring") or (None, None))[1],
        "categories_hiring": hiring_in,
        "jobs": jobs,
    }


# ---- top 100 ---------------------------------------------------------------------------------------

def top_companies(markup):
    doc = soup(markup)
    out, seen = [], set()
    for li in doc.select(".jobs-container li"):
        a = li.select_one("a[href^='/company/'] .rank")
        if a is None:
            continue
        row = a.find_parent("a")
        slug = _slug_from_href(row.get("href"), "/company/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append({
            "rank": to_int(node_text(a)),
            "name": node_text(row.select_one(".company")),
            "slug": slug,
            "link": refs.company_link(slug),
            "logo_link": logo_link(_bg_image(li.select_one(".flag-logo"))),
            "description": node_text(row.select_one(".company-title")),
            "jobs_posted_count": _first_number(node_text(row.select_one(".job-count"))),
            "is_actively_hiring": li.select_one(".listing-pill") is not None,
        })
    return out


# ---- RSS -------------------------------------------------------------------------------------------

def _xml_text(item, tag):
    node = item.find(tag)
    return text(node.text) if node is not None and node.text else None


def feed(xml_text, today=None):
    """An RSS feed -> [{slug, title, link, job_type, posted_at, expires_at,
    region/country/state, skills, category, company {name, logo_link},
    description_html, description_text}]."""
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ElementTree.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        raw_title = _xml_text(item, "title") or ""
        company, _, title = raw_title.partition(": ")
        if not title:
            company, title = None, raw_title
        link = _xml_text(item, "link") or _xml_text(item, "guid")
        slug = _slug_from_href(link, "/remote-jobs/")
        region = _xml_text(item, "region")
        country, state = _xml_text(item, "country"), _xml_text(item, "state")
        tags = [t for t in (region, country) if t]
        location = _location_from_tags(tags)
        if state:
            location["places"].append(state)
        desc = item.find("description")
        desc_html = (desc.text or "").strip() if desc is not None else ""
        hq = None
        hq_match = _FEED_HQ_RE.match(desc_html)
        if hq_match:
            hq = text(_HTML_TAG_RE.sub(" ", hq_match.group(1)))
            desc_html = desc_html[hq_match.end():].strip()
        media = item.find("{http://search.yahoo.com/mrss}content")
        skills_raw = _xml_text(item, "skills")
        skills = [s.strip() for s in re.split(r",| and ", skills_raw) if s.strip()] if skills_raw else []
        cat_name = _xml_text(item, "category")
        out.append({
            "slug": slug,
            "title": text(title),
            "link": link,
            "job_type": job_type_slug(_xml_text(item, "type")),
            "posted_at": iso_from_rfc822(_xml_text(item, "pubDate")),
            "expires_at": iso_from_rfc822(_xml_text(item, "expires_at")),
            "location": location,
            "skills": skills,
            "description_html": desc_html or None,
            "description_text": strip_html(desc_html) if desc_html else None,
            "company": {"name": text(company), "headquarters": hq,
                        "logo_link": logo_link(media.get("url")) if media is not None else None},
            "category": category_from_name(cat_name) or ({"id": None, "slug": None, "name": cat_name, "link": None} if cat_name else None),
        })
    return out
