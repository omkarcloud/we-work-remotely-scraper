"""The 16 We Work Remotely endpoints. Every path is served with and without
the `/we-work-remotely` prefix, so code generated against the hosted API on
RapidAPI (paths like /jobs/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in weworkremotely/schemas.py
(the same ones the hosted API uses): ONE param per input — `job` takes a
slug or a weworkremotely.com job link, `company` a slug or a company link,
and `query` on /jobs/search takes text or a full weworkremotely.com listing
or search link whose own filters are then applied. Unknown params are
rejected with a 400 so typos surface.

Lists page with `page` (count / total_pages / next / previous in the
response)."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from weworkremotely import companies, jobs, reference
from weworkremotely import schemas as S


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Zürich" would arrive as "ZÃ¼rich")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema, fn, paginated=False):
    """Validate the query, run the scraper, map errors: bad params -> 400,
    missing entity -> 404, transport/blocks -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:                # bad slug / params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # the site cannot serve these params
        return json_response({"error": f"we-work-remotely rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"we-work-remotely {label} failed: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


def mount(path, schema, fn, paginated=False):
    """Serve an endpoint at /path and /we-work-remotely/path."""
    def handler():
        return call(path.strip("/"), schema, fn, paginated)
    handler.__name__ = "we_work_remotely_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/we-work-remotely" + path, method="GET")(handler)


P = True   # paginated (page)
ENDPOINTS = [
    ("/jobs/details", S.JobSchema, jobs.details, False),
    ("/jobs/search", S.JobSearchSchema, jobs.search, P),
    ("/jobs/latest", S.JobsLatestSchema, jobs.latest, False),
    ("/jobs/by-category", S.JobsByCategorySchema, jobs.by_category, P),
    ("/jobs/by-region", S.JobsByRegionSchema, jobs.by_region, P),
    ("/jobs/by-type", S.JobsByTypeSchema, jobs.by_type, P),
    ("/jobs/by-keyword", S.JobsByKeywordSchema, jobs.by_keyword, P),
    ("/jobs/trending", S.JobsTrendingSchema, jobs.trending, P),
    ("/companies/details", S.CompanySchema, companies.details, False),
    ("/companies/jobs", S.CompanyJobsSchema, companies.jobs, P),
    ("/companies/top", S.TopCompaniesSchema, companies.top, False),
    ("/categories", S.EmptySchema, reference.categories, False),
    ("/skills", S.LookupSchema, reference.skills, False),
    ("/countries", S.LookupSchema, reference.countries, False),
    ("/filters", S.EmptySchema, reference.filters, False),
    ("/statistics", S.EmptySchema, reference.statistics, False),
]

for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
