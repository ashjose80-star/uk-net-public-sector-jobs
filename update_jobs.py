#!/usr/bin/env python3
"""
Daily UK .NET public-sector vacancy updater.

Requires:
  SERPER_API_KEY environment variable

Run:
  python update_jobs.py

The script searches several public-sector job domains using Serper's Google Search API,
keeps results that look like UK public-sector .NET/C# vacancies, and merges them into
jobs.json. Results are labelled as automated leads so they can be checked before being
treated as verified vacancies.
"""
import json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "jobs.json"
API = "https://google.serper.dev/search"

QUERIES = [
    'site:jobs.service.gov.uk ("C#" OR ".NET" OR "ASP.NET" OR "ASP.NET Core") ("Developer" OR "Engineer" OR "Software")',
    'site:jobs.ac.uk ("C#" OR ".NET" OR "ASP.NET") ("Developer" OR "Software Engineer" OR "Applications Developer") ("University" OR "College")',
    'site:findajob.dwp.gov.uk ("C#" OR ".NET" OR "ASP.NET") ("Developer" OR "Software Engineer")',
    'site:*.gov.uk/jobs ("C#" OR ".NET" OR "ASP.NET") ("Developer" OR "Software Engineer")',
    'site:*.ac.uk/jobs ("C#" OR ".NET" OR "ASP.NET") ("Developer" OR "Software Engineer")',
]

TRUSTED_HOSTS = (
    "jobs.service.gov.uk",
    "jobs.ac.uk",
    "findajob.dwp.gov.uk",
)

TECH_RE = re.compile(r'(?i)\b(?:\.net(?:\s*(?:core|framework))?|asp\.net|c#|c sharp|dotnet)\b')
ROLE_RE = re.compile(r'(?i)\b(?:developer|software engineer|programmer|applications developer|web developer|digital developer|development manager)\b')

def search(q):
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        raise SystemExit("SERPER_API_KEY is not set")
    payload = json.dumps({"q": q, "num": 20, "gl": "gb", "hl": "en"}).encode()
    req = urllib.request.Request(API, data=payload, headers={
        "X-API-KEY": key,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def infer_org(title, link, snippet):
    host = urlparse(link).netloc.lower()
    text = f"{title} {snippet}"
    # Common host-specific hints.
    if "jobs.service.gov.uk" in host:
        m = re.search(r'(?i)\b(?:Department for [A-Z][A-Za-z &-]+|[A-Z][A-Za-z &-]+ Council|NHS [A-Za-z &-]+)\b', text)
        return m.group(0).strip() if m else "UK Government"
    if "jobs.ac.uk" in host:
        m = re.search(r'(?i)\b(?:University|College) of [A-Z][A-Za-z &\'-]+', text)
        return m.group(0).strip() if m else "Higher-education provider"
    return "Public-sector employer"

def sector_for(org, link):
    host = urlparse(link).netloc.lower()
    if "jobs.ac.uk" in host or ".ac.uk" in host:
        return "University"
    if "gov.uk" in host:
        return "Government"
    if "council" in org.lower():
        return "Council"
    return "Government"

def make_item(x):
    title = clean(x.get("title"))
    link = x.get("link", "").strip()
    snippet = clean(x.get("snippet"))
    if not link or not title:
        return None
    blob = f"{title} {snippet}"
    if not TECH_RE.search(blob) or not ROLE_RE.search(title):
        return None
    host = urlparse(link).netloc.lower()
    if not (host.endswith("gov.uk") or host.endswith("ac.uk") or host == "jobs.ac.uk"):
        return None
    org = infer_org(title, link, snippet)
    return {
        "org": org,
        "sector": sector_for(org, link),
        "location": "UK",
        "title": title,
        "salary": "Not captured",
        "posted": clean(x.get("date") or ""),
        "closing": "",
        "match": "Exact .NET",
        "tech": ".NET / C# (detected in search result)",
        "url": link,
        "confidence": "Automated daily search lead; verify employer vacancy",
    }

def main():
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        data = {"active": [], "leads": [], "history": [], "coverage": []}

    existing_urls = {x.get("url") for x in data.get("active", []) if x.get("url")}
    found = {}
    for q in QUERIES:
        result = search(q)
        for item in result.get("organic", []):
            job = make_item(item)
            if job:
                found[job["url"]] = job
        time.sleep(0.5)

    # Put newly discovered jobs into active, but keep existing records first.
    new_items = [v for k, v in found.items() if k not in existing_urls]
    data["active"] = new_items + data.get("active", [])
    data["active"] = data["active"][:200]

    # Record daily discovery evidence in history without duplicating URLs.
    seen_hist = {(x.get("url"), x.get("date")) for x in data.get("history", [])}
    today = datetime.now(timezone.utc).date().isoformat()
    for job in new_items:
        key = (job["url"], today)
        if key not in seen_hist:
            data.setdefault("history", []).append({
                "org": job["org"],
                "sector": job["sector"],
                "title": job["title"],
                "date": today,
                "match": job["match"],
                "tech": job["tech"],
                "url": job["url"],
            })

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Added {len(new_items)} new automated leads; total active: {len(data['active'])}")

if __name__ == "__main__":
    main()
