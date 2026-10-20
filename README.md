# 🌍 We Work Remotely Scraper

We Work Remotely Scraper is a **free and open-source** scraper that gets you **unlimited** detailed We Work Remotely jobs data for free.

## ✨ What Can I Get?

- 🌍 **1,000+ new remote jobs every month** — search by keyword, category, country, salary, job type, region & posting date
- 📄 **Full job details** — description, salary range, skills, countries, posting & expiry dates & related jobs
- 🏢 **Top 100 remote companies & every hiring company** — website, HQ, about, culture, benefits & every open role
- 📊 **12 categories, 670 skills & 249 countries** — live job counts per category plus a whole-board statistics snapshot

## 🎥 Example: A Full We Work Remotely Job

```json
{
  "slug": "databricks-solutions-architect",
  "title": "Solutions Architect",
  "link": "https://weworkremotely.com/remote-jobs/databricks-solutions-architect",
  "job_type": "full-time",
  "posted_at": "2026-10-18T21:30:04Z",
  "first_posted_at": "2026-08-19T21:30:04Z",
  "is_renewed": true,
  "expires_at": "2026-11-17T21:30:04Z",
  "salary_range": { "label": "$100,000 or more USD", "min": 100000, "max": null, "currency": "USD" },
  "category": { "id": 4, "slug": "all-other", "name": "All Other Remote" },
  "location": { "is_anywhere": false, "is_geolocked": true, "countries": [{ "code": "US", "name": "United States of America" }] },
  "description_text": "Mission\nWe are looking for experienced pre-sales professionals who have a successful track record helping large enterprises become more data-driven...",
  "company": {
    "name": "Databricks",
    "slug": "databricks",
    "link": "https://weworkremotely.com/company/databricks",
    "website_link": "https://www.databricks.com/",
    "headquarters": "Remote",
    "jobs_posted_count": 11
  },
  "related_jobs": [
    { "slug": "testgorilla-sr-people-talent-operations-partner", "title": "Sr. People & Talent Operations Partner", "salary_range": { "label": "$50,000 - $74,999 USD" }, "flags": { "is_featured": true, "is_hot": true } }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free We Work Remotely Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/we-work-remotely-scraper
cd we-work-remotely-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=databricks-solutions-architect"
```

```json
{
  "slug": "databricks-solutions-architect",
  "title": "Solutions Architect",
  "link": "https://weworkremotely.com/remote-jobs/databricks-solutions-architect",
  "job_type": "full-time",
  "posted_at": "2026-10-18T21:30:04Z",
  "expires_at": "2026-11-17T21:30:04Z",
  "salary_range": { "label": "$100,000 or more USD", "min": 100000, "max": null, "currency": "USD" },
  "category": { "slug": "all-other", "name": "All Other Remote" },
  "location": { "is_anywhere": false, "is_geolocked": true, "countries": [{ "code": "US", "name": "United States of America" }] },
  "company": {
    "name": "Databricks",
    "slug": "databricks",
    "website_link": "https://www.databricks.com/",
    "headquarters": "Remote",
    "jobs_posted_count": 11
  }
}
```

All 16 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

16 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | Everything about one job in a single call |
| Search Jobs | `/jobs/search` | 50 jobs per page; filter by keyword, category, country, salary or date |
| Latest Jobs | `/jobs/latest` | The newest ~90 jobs with full descriptions |
| Jobs by Category / Region / Type / Keyword | `/jobs/by-category`, `/jobs/by-region`, `/jobs/by-type`, `/jobs/by-keyword` | The board's own job lists, 50 per page |
| Trending Jobs | `/jobs/trending` | The board's trending remote jobs |
| Company Details | `/companies/details` | Website, HQ, about, culture, benefits and every open job |
| Company Jobs | `/companies/jobs` | One company's open jobs, filterable by category |
| Top 100 Remote Companies | `/companies/top` | The 100 biggest remote employers, ranked by jobs posted |
| Categories | `/categories` | All 12 categories with live job counts |
| Skills / Countries | `/skills`, `/countries` | 670 skills and 249 countries, searchable by name |
| Search Filters | `/filters` | Every accepted value for the search filters |
| Board Statistics | `/statistics` | Jobs by category, type, region and salary, plus top hirers |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-we-work-remotely-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-we-work-remotely-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-we-work-remotely-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "engineer", "category": "programming"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about We Work Remotely Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20We%20Work%20Remotely%20Scraper%20API.)

[![Ask Us by Email about We Work Remotely Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20We%20Work%20Remotely%20Scraper%20API&body=I%20need%20help%20using%20the%20We%20Work%20Remotely%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Glassdoor Scraper**](https://github.com/omkarcloud/glassdoor-scraper) — Glassdoor jobs, company ratings, salaries & reviews
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/we-work-remotely-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/we-work-remotely-scraper)
