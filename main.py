"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The functions live in weworkremotely/ (jobs, companies,
reference). Their params take the validated values the API builds (lists for
`category`, our slugs for `job` / `company`), so call them as below or go
through weworkremotely.schemas first.
"""
import json
import os

from weworkremotely import companies, jobs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # search: every programming job mentioning "engineer" posted in the last 2 weeks
    found = jobs.search(query="engineer", category=["full-stack-programming", "front-end-programming",
                                                    "back-end-programming"], posted_within="14d")
    save("search_engineer_programming.json", found)

    # one job in full — a job slug (or use any weworkremotely.com job link through the API)
    if found["jobs"]:
        save("job_details.json", jobs.details(found["jobs"][0]["slug"]))

    # a company profile with every active job
    save("company_vercel.json", companies.details("vercel"))
