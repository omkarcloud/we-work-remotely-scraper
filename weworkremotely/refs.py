"""We Work Remotely reference tables + resolvers: ONE param per input that
auto-detects its forms (tripadvisor QueryOrIdField convention — never a
sibling `url`/`id` pair).

  job        expel-technical-account-manager
             | https://weworkremotely.com/remote-jobs/expel-technical-account-manager
             | https://weworkremotely.com/listings/expel-technical-account-manager   -> slug
  company    stripe | https://weworkremotely.com/company/stripe                  -> slug
  query      free text | a weworkremotely.com listing / search link whose own
             filters are then applied (parse_search_link)
  category   our slug (full-stack-programming), the site's slug
             (remote-full-stack-programming-jobs), the site's numeric id (2),
             the display name ("Full-Stack Programming") or a group
             ("programming" = full-stack + front-end + back-end)
  region     our slug (europe) or the site's landing slug (remote-europe-jobs)
             or the card label ("Europe Only", "Anywhere in the World")

The site's own tokens (verified 2026-10-19 from the search form and the
sitemap): category checkbox ids, the 13 region landing pages, the two
job-type pages, five salary buckets, four time windows, three promotion
filters.
"""
import re
from urllib.parse import parse_qsl, unquote, urlparse

SITE = "https://weworkremotely.com"

# ---- categories --------------------------------------------------------------------
# (our slug, site id, display name, site landing slug, group)
CATEGORIES = [
    {"slug": "full-stack-programming", "id": 2, "name": "Full-Stack Programming",
     "site_slug": "remote-full-stack-programming-jobs", "group": "programming"},
    {"slug": "front-end-programming", "id": 17, "name": "Front-End Programming",
     "site_slug": "remote-front-end-programming-jobs", "group": "programming"},
    {"slug": "back-end-programming", "id": 18, "name": "Back-End Programming",
     "site_slug": "remote-back-end-programming-jobs", "group": "programming"},
    {"slug": "design", "id": 1, "name": "Design", "site_slug": "remote-design-jobs", "group": "design"},
    {"slug": "product-design", "id": 19, "name": "Product Design",
     "site_slug": "remote-product-design-jobs", "group": "design"},
    {"slug": "ux-ui-design", "id": 20, "name": "UX/UI Design",
     "site_slug": "remote-ux-ui-design-jobs", "group": "design"},
    {"slug": "customer-support", "id": 7, "name": "Customer Support",
     "site_slug": "remote-customer-support-jobs", "group": None},
    {"slug": "devops-sysadmin", "id": 6, "name": "DevOps and Sysadmin",
     "site_slug": "remote-devops-sysadmin-jobs", "group": None},
    {"slug": "sales-and-marketing", "id": 9, "name": "Sales and Marketing",
     "site_slug": "remote-sales-and-marketing-jobs", "group": None},
    {"slug": "management-and-finance", "id": 3, "name": "Management and Finance",
     "site_slug": "remote-management-and-finance-jobs", "group": None},
    {"slug": "product", "id": 11, "name": "Product", "site_slug": "remote-product-jobs", "group": None},
    {"slug": "all-other", "id": 4, "name": "All Other Remote", "site_slug": "all-other-remote-jobs", "group": None},
]
CATEGORY_GROUPS = {"programming": ["full-stack-programming", "front-end-programming", "back-end-programming"],
                   "design": ["design", "product-design", "ux-ui-design"]}
CATEGORY_BY_SLUG = {c["slug"]: c for c in CATEGORIES}
CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}
CATEGORY_BY_SITE_SLUG = {c["site_slug"]: c for c in CATEGORIES}


def _norm(value):
    """'Full-Stack Programming' / 'UX/UI Design' / 'sales & marketing' ->
    'full stack programming' / 'ux ui design' / 'sales and marketing'."""
    low = str(value or "").strip().lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[-_/]+", " ", low)).strip()


CATEGORY_BY_NAME = {_norm(c["name"]): c for c in CATEGORIES}
CATEGORY_BY_NAME.update({"all other": CATEGORY_BY_SLUG["all-other"], "all other remote jobs": CATEGORY_BY_SLUG["all-other"],
                         "other": CATEGORY_BY_SLUG["all-other"], "devops": CATEGORY_BY_SLUG["devops-sysadmin"],
                         "devops sysadmin": CATEGORY_BY_SLUG["devops-sysadmin"], "ux ui": CATEGORY_BY_SLUG["ux-ui-design"],
                         "full stack": CATEGORY_BY_SLUG["full-stack-programming"], "front end": CATEGORY_BY_SLUG["front-end-programming"],
                         "back end": CATEGORY_BY_SLUG["back-end-programming"], "sales": CATEGORY_BY_SLUG["sales-and-marketing"],
                         "marketing": CATEGORY_BY_SLUG["sales-and-marketing"], "management": CATEGORY_BY_SLUG["management-and-finance"],
                         "finance": CATEGORY_BY_SLUG["management-and-finance"], "support": CATEGORY_BY_SLUG["customer-support"]})
# the site's category subcategory ids (19, 20) roll up under 1 on cards (data-category)
SUBCATEGORY_PARENT = {19: 1, 20: 1}

# ---- regions ------------------------------------------------------------------------
# our slug -> (site landing path, display name, card label)
REGIONS = {
    "anywhere": ("/100-percent-remote-jobs", "Anywhere in the World", "Anywhere in the World"),
    "usa": ("/remote-usa-jobs", "USA", "USA Only"),
    "north-america": ("/remote-north-america-jobs", "North America", "North America Only"),
    "americas": ("/remote-americas-jobs", "Americas", "Americas Only"),
    "latin-america": ("/remote-latin-america-jobs", "Latin America", "Latin America Only"),
    "canada": ("/remote-canada-jobs", "Canada", "Canada Only"),
    "europe": ("/remote-europe-jobs", "Europe", "Europe Only"),
    "uk": ("/remote-uk-jobs", "UK", "UK Only"),
    "emea": ("/remote-emea-jobs", "EMEA", "EMEA Only"),
    "middle-east": ("/remote-middle-east-jobs", "Middle East", "Middle East Only"),
    "asia": ("/remote-asia-jobs", "Asia", "Asia Only"),
    "africa": ("/remote-africa-jobs", "Africa", "Africa Only"),
    "oceania": ("/remote-oceania-jobs", "Oceania", "Oceania Only"),
}
REGION_BY_LABEL = {v[2].lower(): k for k, v in REGIONS.items()}
REGION_BY_LABEL.update({v[1].lower(): k for k, v in REGIONS.items()})
REGION_BY_LABEL.update({"anywhere in the world": "anywhere", "worldwide": "anywhere", "100 percent remote": "anywhere",
                        "united states": "usa", "us": "usa", "united kingdom": "uk", "gb": "uk"})
REGION_BY_PATH = {v[0].strip("/"): k for k, v in REGIONS.items()}

# ---- job types / salary / time windows / promotion filters ------------------------------
JOB_TYPES = {"full-time": ("/remote-full-time-jobs", "Full-Time"), "contract": ("/remote-contract-jobs", "Contract")}
JOB_TYPE_BY_LABEL = {"full-time": "full-time", "full time": "full-time", "fulltime": "full-time", "contract": "contract",
                     "part-time": "contract", "part time": "contract", "freelance": "contract"}
# every job-type chip the cards show (the site's contract page also lists part-time)
JOB_TYPE_LABELS = {"full-time", "contract", "part-time", "freelance", "internship", "temporary"}

# our value -> (site label, min, max)
SALARY_RANGES = {
    "10k-25k": ("$10,000 - $25,000 USD", 10000, 25000),
    "25k-49k": ("$25,000 - $48,999 USD", 25000, 48999),
    "50k-75k": ("$50,000 - $74,999 USD", 50000, 74999),
    "75k-100k": ("$75,000 - $99,999 USD", 75000, 99999),
    "100k+": ("$100,000 or more USD", 100000, None),
}
SALARY_BY_LABEL = {v[0].lower().replace(" ", ""): k for k, v in SALARY_RANGES.items()}
SALARY_ALIASES = {"10k-25k": "10k-25k", "25k-49k": "25k-49k", "25k-48k": "25k-49k", "50k-75k": "50k-75k",
                  "50k-74k": "50k-75k", "75k-100k": "75k-100k", "75k-99k": "75k-100k", "100k+": "100k+",
                  "100k": "100k+", "100k-plus": "100k+", "100k-or-more": "100k+"}

POSTED_WITHIN = {"24h": "Past 24 Hours", "7d": "Past Week", "14d": "Past 2 Weeks", "any": "Any Time"}
POSTED_WITHIN_DAYS = {"24h": 1, "7d": 7, "14d": 14, "any": None}
POSTED_WITHIN_BY_LABEL = {v.lower(): k for k, v in POSTED_WITHIN.items()}
PROMOTION_FILTERS = ["all", "hot", "boosted"]

# ---- links out -----------------------------------------------------------------------------

def absolute(path):
    if not path or not isinstance(path, str):
        return None
    path = path.strip()
    if path.startswith("http"):
        return path
    if path.startswith("//"):
        return "https:" + path
    if not path.startswith("/"):
        path = "/" + path
    return SITE + path


def job_link(slug):
    return f"{SITE}/remote-jobs/{slug}"


def company_link(slug):
    return f"{SITE}/company/{slug}"


def category_link(category):
    return f"{SITE}/categories/{category['site_slug']}"


def category_feed_link(category):
    return category_link(category) + ".rss"


def region_link(slug):
    return SITE + REGIONS[slug][0]


def keyword_link(keyword):
    return f"{SITE}/remote-{slugify(keyword)}-jobs"


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


# ---- resolvers -------------------------------------------------------------------------------

_HOST_RE = re.compile(r"^(?:www\.)?weworkremotely\.com(?=/|$)", re.I)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,200}$", re.I)
_KEYWORD_PAGE_RE = re.compile(r"^remote-(.+)-jobs$", re.I)


def is_link(value):
    value = str(value or "").strip()
    return value.startswith(("http://", "https://", "//")) or bool(_HOST_RE.match(value))


def _parse(value):
    """A weworkremotely.com link -> (path segments, query pairs). ValueError
    for another site."""
    url = value.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host == "weworkremotely.com" or host.endswith(".weworkremotely.com")):
        raise ValueError("not a weworkremotely.com link")
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    return segments, parse_qsl(parsed.query, keep_blank_values=False)


def _clean_slug(raw):
    return raw.split("?")[0].split("#")[0].strip().lower()


def resolve_job(value):
    """slug | /remote-jobs/<slug> link | /listings/<slug> link -> slug."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Must not be empty.")
    if is_link(raw):
        try:
            segments, _ = _parse(raw)
        except ValueError:
            raise ValueError("Must be a weworkremotely.com job link (/remote-jobs/<slug>) or a job slug.")
        if len(segments) >= 2 and segments[0] in ("remote-jobs", "listings") and segments[1] not in ("search", "salary"):
            raw = segments[1]
        else:
            raise ValueError("Must be a weworkremotely.com job link (/remote-jobs/<slug>) or a job slug.")
    raw = _clean_slug(raw.removesuffix(".rss"))
    if not _SLUG_RE.match(raw):
        raise ValueError("Must be a job slug (letters, digits, dashes) or a weworkremotely.com job link.")
    return raw


def resolve_company(value):
    """slug | /company/<slug> link -> slug."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Must not be empty.")
    if is_link(raw):
        try:
            segments, _ = _parse(raw)
        except ValueError:
            raise ValueError("Must be a weworkremotely.com company link (/company/<slug>) or a company slug.")
        if len(segments) >= 2 and segments[0] == "company":
            raw = segments[1]
        else:
            raise ValueError("Must be a weworkremotely.com company link (/company/<slug>) or a company slug.")
    raw = _clean_slug(raw)
    if not _SLUG_RE.match(raw):
        raise ValueError("Must be a company slug (letters, digits, dashes) or a weworkremotely.com company link.")
    return raw


def resolve_category(value):
    """our slug | site slug | site id | name | group -> [category dict, ...]
    (a group expands to its members)."""
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("Must not be empty.")
    if raw.isdigit():
        cat = CATEGORY_BY_ID.get(int(raw))
        if cat:
            return [cat]
    raw = raw.replace("_", "-")
    if raw in CATEGORY_GROUPS:
        return [CATEGORY_BY_SLUG[s] for s in CATEGORY_GROUPS[raw]]
    if raw in CATEGORY_BY_SLUG:
        return [CATEGORY_BY_SLUG[raw]]
    if raw in CATEGORY_BY_SITE_SLUG:
        return [CATEGORY_BY_SITE_SLUG[raw]]
    if raw.startswith("categories/"):
        return resolve_category(raw.split("/", 1)[1])
    spaced = _norm(raw)
    if spaced in CATEGORY_BY_NAME:
        return [CATEGORY_BY_NAME[spaced]]
    if spaced.endswith(" jobs") and spaced[:-5] in CATEGORY_BY_NAME:
        return [CATEGORY_BY_NAME[spaced[:-5]]]
    raise ValueError("Unknown category. Use one of: " + ", ".join(list(CATEGORY_GROUPS) + [c["slug"] for c in CATEGORIES]) + ".")


def resolve_region(value):
    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw:
        raise ValueError("Must not be empty.")
    if raw in REGIONS:
        return raw
    if raw in REGION_BY_PATH:
        return REGION_BY_PATH[raw]
    spaced = re.sub(r"\s+", " ", raw.replace("-", " ")).strip()
    if spaced in REGION_BY_LABEL:
        return REGION_BY_LABEL[spaced]
    if spaced.endswith(" only") and spaced[:-5] in REGION_BY_LABEL:
        return REGION_BY_LABEL[spaced[:-5]]
    raise ValueError("Unknown region. Use one of: " + ", ".join(REGIONS) + ".")


def resolve_job_type(value):
    raw = re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", "-"))
    if raw in JOB_TYPES:
        return raw
    if raw in JOB_TYPE_BY_LABEL:
        return JOB_TYPE_BY_LABEL[raw]
    if raw.replace(" ", "-") in JOB_TYPES:
        return raw.replace(" ", "-")
    raise ValueError("Must be full-time or contract.")


def resolve_salary_range(value):
    raw = str(value or "").strip().lower().replace(" ", "")
    if raw in SALARY_BY_LABEL:
        return SALARY_BY_LABEL[raw]
    raw = raw.replace("_", "-").replace("$", "").replace(",", "")
    if raw in SALARY_ALIASES:
        return SALARY_ALIASES[raw]
    raise ValueError("Must be one of: " + ", ".join(SALARY_RANGES) + ".")


def resolve_posted_within(value):
    raw = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if raw in POSTED_WITHIN:
        return raw
    if raw in POSTED_WITHIN_BY_LABEL:
        return POSTED_WITHIN_BY_LABEL[raw]
    aliases = {"1d": "24h", "day": "24h", "today": "24h", "week": "7d", "1w": "7d", "2w": "14d", "2 weeks": "14d",
               "all": "any", "anytime": "any"}
    if raw in aliases:
        return aliases[raw]
    raise ValueError("Must be one of: 24h, 7d, 14d, any.")


def parse_search_link(value):
    """A weworkremotely.com listing / search link -> the search kwargs it
    encodes (only the keys present). ValueError for another site or a page
    that is not a listing."""
    segments, query = _parse(value)
    out = {}
    path = "/".join(segments)
    if segments:
        if segments[0] == "categories" and len(segments) == 2:
            out["category"] = [c["slug"] for c in resolve_category(segments[1].removesuffix(".rss"))]
        elif segments == ["remote-jobs", "search"] or segments == ["jobs", "search"]:
            pass
        elif segments in (["remote-jobs"], ["remote-jobs.rss"]):
            pass
        elif path in REGION_BY_PATH:
            out["region"] = REGION_BY_PATH[path]
        elif path == "remote-full-time-jobs":
            out["job_type"] = "full-time"
        elif path == "remote-contract-jobs":
            out["job_type"] = "contract"
        elif len(segments) == 3 and segments[:2] == ["remote-jobs", "salary"]:
            out["salary_range"] = [resolve_salary_range(segments[2])]
        elif len(segments) == 1 and _KEYWORD_PAGE_RE.match(segments[0]):
            out["query"] = _KEYWORD_PAGE_RE.match(segments[0]).group(1).replace("-", " ")
        elif len(segments) == 1 and segments[0].startswith("remote-jobs-"):
            out["query"] = segments[0][len("remote-jobs-"):].replace("-", " ")
        else:
            raise ValueError("Not a weworkremotely.com listing or search link.")
    for key, raw in query:
        key = key.lower().removesuffix("[]")
        raw = raw.strip()
        if not raw:
            continue
        if key == "term":
            out["query"] = raw
        elif key == "categories":
            out.setdefault("category", [])
            for part in raw.split(","):
                try:
                    out["category"] += [c["slug"] for c in resolve_category(part)]
                except ValueError:
                    pass
        elif key == "country":
            out.setdefault("country", []).append(raw.upper())
        elif key == "salary_range":
            try:
                out.setdefault("salary_range", []).append(resolve_salary_range(raw))
            except ValueError:
                pass
        elif key == "skills":
            out.setdefault("skills", []).append(raw)
        elif key == "sort":
            try:
                out["posted_within"] = resolve_posted_within(raw)
            except ValueError:
                pass
        elif key == "job_filter" and raw.lower() in PROMOTION_FILTERS:
            out["filter"] = raw.lower()
        elif key == "page" and raw.isdigit():
            out["page"] = int(raw)
    for key in ("category", "country", "salary_range", "skills"):
        if key in out:
            seen = []
            for item in out[key]:
                if item not in seen:
                    seen.append(item)
            out[key] = seen
    return out
