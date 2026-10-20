"""Cache TTL per /we-work-remotely/* endpoint (cache.py, keyed on the
validated params).

Tiers follow how fast the board moves: a few new jobs land every hour
(~440 active listings, 30-day lifetime), a job record changes only when the
employer edits it, company profiles change with each posting, the Top 100
list and the filter option lists a few times a year.
"""
from datetime import timedelta

# --- jobs --------------------------------------------------------------------
SEARCH_CACHE = timedelta(minutes=10)
LATEST_CACHE = timedelta(minutes=15)
LISTING_CACHE = timedelta(minutes=15)
JOB_CACHE = timedelta(hours=2)

# --- companies ---------------------------------------------------------------
COMPANY_CACHE = timedelta(hours=1)
TOP_COMPANIES_CACHE = timedelta(hours=12)

# --- reference ---------------------------------------------------------------
CATEGORIES_CACHE = timedelta(hours=1)
FILTERS_CACHE = timedelta(days=1)
STATISTICS_CACHE = timedelta(minutes=30)
