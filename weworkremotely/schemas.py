"""Marshmallow request schemas for every /we-work-remotely/* route. Generic
fields come from the shared schema_fields.py; this module adds the We Work
Remotely resolvers (refs.py). Every schema's load() output is the kwargs
dict its endpoint takes.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    job          a job slug (expel-technical-account-manager) OR a
                 weworkremotely.com job link
    company      a company slug (stripe) OR a weworkremotely.com company link
    query        free text OR (on /jobs/search) any weworkremotely.com listing
                 or search link, whose own filters are then applied
    category     our slug (full-stack-programming), the site's slug / id /
                 display name, or a group (programming, design); comma list
    region       anywhere | usa | north-america | americas | latin-america |
                 canada | europe | uk | emea | middle-east | asia | africa |
                 oceania (or the card label "Europe Only")
    country      ISO 3166-1 alpha-2 codes or country names, comma list
    salary_range 10k-25k | 25k-49k | 50k-75k | 75k-100k | 100k+ (or the
                 site's label), comma list
    skills       skill names or the site's numeric skill ids, comma list
    posted_within 24h | 7d | 14d | any
    filter       all | hot | boosted
    job_type     full-time | contract
"""
from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import (COUNTRY_CODES, BaseSchema, ChoiceField, PageField, PageSizeField, QueryField, RefField,
                           StrippedString, DateField)
from weworkremotely import refs
from weworkremotely.countries import COUNTRY_CODES as COUNTRY_BY_NAME

MAX_PAGE = 100


# ---- fields ------------------------------------------------------------------------

class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class _MappedList(StrippedString):
    """Comma list -> deduped list of canonical values through `resolve`
    (ValueError -> ValidationError), max `max_items`."""
    resolve = None
    max_items = 12

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        if not kwargs["required"]:
            kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        out = []
        for raw in value.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                items = self.resolve(raw)
            except ValueError as e:
                raise ValidationError(str(e))
            for item in (items if isinstance(items, list) else [items]):
                if item not in out:
                    out.append(item)
        if len(out) > self.max_items:
            raise ValidationError(f"At most {self.max_items} values.")
        return out or None


class CategoryListField(_MappedList):
    """-> list of our category slugs (a group expands)."""
    resolve = staticmethod(lambda raw: [c["slug"] for c in refs.resolve_category(raw)])


class CategoryField(StrippedString):
    """ONE category -> our slug (groups are not allowed here)."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            cats = refs.resolve_category(value)
        except ValueError as e:
            raise ValidationError(str(e))
        if len(cats) != 1:
            raise ValidationError("One category at a time here (a group such as 'programming' lists several).")
        return cats[0]["slug"]


def _resolve_country(raw):
    code = raw.strip().upper()
    if code == "UK":
        code = "GB"
    if len(code) == 2 and code in COUNTRY_CODES:
        return code
    name = COUNTRY_BY_NAME.get(raw.strip().lower())
    if name:
        return name
    raise ValueError(f"'{raw}' is not an ISO country code or a country name.")


class CountryListField(_MappedList):
    resolve = staticmethod(_resolve_country)
    max_items = 20


class SalaryRangeListField(_MappedList):
    resolve = staticmethod(refs.resolve_salary_range)
    max_items = 5


class SkillsField(_MappedList):
    """Skill names or ids, as given (jobs.search resolves names to the
    site's ids against the live skill list)."""
    resolve = staticmethod(lambda raw: raw)
    max_items = 10


class RegionField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        if not kwargs["required"]:
            kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            return refs.resolve_region(value)
        except ValueError as e:
            raise ValidationError(str(e))


class JobTypeField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        if not kwargs["required"]:
            kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            return refs.resolve_job_type(value)
        except ValueError as e:
            raise ValidationError(str(e))


class PostedWithinField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        if not kwargs["required"]:
            kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            return refs.resolve_posted_within(value)
        except ValueError as e:
            raise ValidationError(str(e))


# ---- jobs --------------------------------------------------------------------------------

class JobSearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None,
                           metadata={"description": "keywords matched against title / company / description, "
                                                    "or any weworkremotely.com listing or search link"})
    category = CategoryListField(metadata={"description": "comma list of categories or groups (programming, design)"})
    country = CountryListField(metadata={"description": "comma list of ISO codes or country names the job is open to"})
    salary_range = SalaryRangeListField(metadata={"description": "comma list of 10k-25k, 25k-49k, 50k-75k, 75k-100k, 100k+"})
    skills = SkillsField(metadata={"description": "comma list of skill names or ids (see /we-work-remotely/skills)"})
    posted_within = PostedWithinField(metadata={"description": "24h | 7d | 14d | any"})
    filter = ChoiceField(refs.PROMOTION_FILTERS, metadata={"description": "all | hot | boosted"})
    job_type = JobTypeField(metadata={"description": "full-time | contract"})
    region = RegionField(metadata={"description": "anywhere | usa | europe | uk | canada | asia | … (the job's region chip)"})
    page = PageField(max_page=MAX_PAGE)

    @validates_schema
    def _query(self, data, **kwargs):
        query = data.get("query")
        if not query:
            return
        if refs.is_link(query):
            try:
                refs.parse_search_link(query)
            except ValueError as e:
                raise ValidationError(str(e), "query")
        elif len(query) > 200:
            raise ValidationError("Longer than 200 characters.", "query")


class JobsLatestSchema(BaseSchema):
    category = CategoryField(required=False, load_default=None,
                             metadata={"description": "one category (its own RSS feed); default: every category"})
    since = DateField(bound="past", metadata={"description": "keep jobs posted on or after this date (YYYY-MM-DD)"})
    limit = PageSizeField(default=100, max_size=100)


class JobSchema(BaseSchema):
    job = JobField()


class JobsByCategorySchema(BaseSchema):
    category = CategoryField(required=True)
    page = PageField(max_page=MAX_PAGE)


class JobsByRegionSchema(BaseSchema):
    region = RegionField(required=True)
    page = PageField(max_page=MAX_PAGE)


class JobsByTypeSchema(BaseSchema):
    job_type = JobTypeField(required=True)
    page = PageField(max_page=MAX_PAGE)


class JobsByKeywordSchema(BaseSchema):
    keyword = QueryField(max_length=80, metadata={"description": "a skill / role keyword (python, react, qa, writer, …) "
                                                                  "or a weworkremotely.com /remote-<keyword>-jobs link"})
    page = PageField(max_page=MAX_PAGE)

    @validates_schema
    def _keyword(self, data, **kwargs):
        raw = data.get("keyword") or ""
        if refs.is_link(raw):
            try:
                parsed = refs.parse_search_link(raw)
            except ValueError as e:
                raise ValidationError(str(e), "keyword")
            if not parsed.get("query"):
                raise ValidationError("Must be a /remote-<keyword>-jobs link.", "keyword")
            data["keyword"] = parsed["query"]


class JobsTrendingSchema(BaseSchema):
    page = PageField(max_page=MAX_PAGE)


# ---- companies -------------------------------------------------------------------------

class CompanySchema(BaseSchema):
    company = CompanyField()


class CompanyJobsSchema(BaseSchema):
    company = CompanyField()
    category = CategoryField(required=False, load_default=None)
    page = PageField(max_page=MAX_PAGE)


class TopCompaniesSchema(BaseSchema):
    limit = PageSizeField(default=100, max_size=100)


# ---- reference ---------------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass


class LookupSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=80),
                           metadata={"description": "substring filter on the name"})
