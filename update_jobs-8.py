#!/usr/bin/env python3
"""
Daily UK .NET public-sector vacancy updater.

Requires:
  SERPER_API_KEY environment variable

Run:
  python update_jobs.py
"""
import json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "jobs.json"
API = "https://google.serper.dev/search"

QUERIES = [
    'site:jobs.service.gov.uk C# developer',
    'site:jobs.service.gov.uk .NET developer',
    'site:jobs.ac.uk C# developer university',
    'site:jobs.ac.uk .NET developer university',
    'site:findajob.dwp.gov.uk C# developer',
    'site:findajob.dwp.gov.uk .NET developer',
    'site:gov.uk council jobs \"digital developer\"',
    'site:gov.uk council jobs \"software developer\"',
    'site:gov.uk council jobs \"web developer\"',
    'site:gov.uk council jobs \"applications developer\"',
    'site:jobs.ac.uk university \"digital developer\"',
    'site:jobs.ac.uk university \"software developer\"',
]

TRUSTED_HOSTS = (
    "jobs.service.gov.uk",
    "jobs.ac.uk",
    "findajob.dwp.gov.uk",
)

TECH_RE = re.compile(r'(?i)\b(?:\.net(?:\s*(?:core|framework))?|asp\.net|c#|c sharp|dotnet)\b')
ROLE_RE = re.compile(r'(?i)\b(?:developer|software engineer|programmer|applications developer|application developer|web developer|digital developer|development manager|systems developer|technical developer|full[- ]stack developer|frontend developer|front[- ]end developer|backend developer|back[- ]end developer|solutions developer|integration developer|platform developer|data developer|cms developer|crm developer)\b')
RELATED_RE = re.compile(r'(?i)\b(?:digital|software|web|applications?|systems?|technical|technology|platform|integration|cms|crm|data|developer|programmer)\b')


def search(q):
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        raise SystemExit("SERPER_API_KEY is not set")
    payload = json.dumps({"q": q, "num": 10, "gl": "gb", "hl": "en"}).encode()
    req = urllib.request.Request(API, data=payload, headers={
        "X-API-KEY": key,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Serper API HTTP {e.code}: {body}")


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def infer_org(title, link, snippet):
    host = urlparse(link).netloc.lower()
    text = f"{title} {snippet}"

    if "jobs.ac.uk" in host or ".ac.uk" in host:
        m = re.search(r'(?i)\bat\s+((?:University|College) of [A-Z][A-Za-z &\'-]+)$', title)
        if m:
            return clean(m.group(1))
        m = re.search(r'(?i)\b((?:University|College) of [A-Z][A-Za-z &\'-]+)', text)
        if m:
            return clean(m.group(1))
        return "Higher-education provider"

    if "jobs.service.gov.uk" in host:
        m = re.search(r'(?i)\b(?:Department for [A-Z][A-Za-z &-]+|[A-Z][A-Za-z &-]+ Council|NHS [A-Za-z &-]+)\b', text)
        return clean(m.group(0)) if m else "UK Government"

    m = re.search(r'(?i)\b([A-Z][A-Za-z &-]+ Council)\b', text)
    if m:
        return clean(m.group(1))
    return "Public-sector employer"


def sector_for(org, link):
    host = urlparse(link).netloc.lower()
    if "council" in org.lower():
        return "Council"
    if "jobs.ac.uk" in host or ".ac.uk" in host:
        return "University"
    if "gov.uk" in host:
        return "Government"
    return "Government"


def parse_closing_date(value):
    value = clean(value)
    if not value:
        return None
    formats = (
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def is_expired(job):
    closing = parse_closing_date(job.get("closing", ""))
    return bool(closing and closing < datetime.now(timezone.utc).date())


def clean_existing_job(job):
    job = dict(job)
    title = clean(job.get("title", ""))
    link = clean(job.get("url", ""))
    snippet = clean(job.get("snippet", ""))
    org = clean(job.get("org", ""))

    if "jobs.ac.uk" in urlparse(link).netloc.lower():
        m = re.search(r'(?i)\bat\s+((?:University|College) of [A-Z][A-Za-z &\'-]+)$', title)
        if m:
            org = clean(m.group(1))
        elif "University of Oxford" in org:
            org = "University of Oxford"

    if not org or " Strong hands-on " in org:
        org = infer_org(title, link, snippet)

    job["org"] = org
    job["sector"] = sector_for(org, link)
    return job


def make_item(x):
    title = clean(x.get("title"))
    link = x.get("link", "").strip()
    snippet = clean(x.get("snippet"))
    if not link or not title:
        return None
    blob = f"{title} {snippet}"
    if not ROLE_RE.search(title):
        return None
    host = urlparse(link).netloc.lower()
    if not (host.endswith("gov.uk") or host.endswith("ac.uk") or host == "jobs.ac.uk"):
        return None

    exact = bool(TECH_RE.search(blob))
    related = bool(RELATED_RE.search(blob))
    if not exact and not related:
        return None

    org = infer_org(title, link, snippet)
    if exact:
        match = "Exact .NET"
        tech = ".NET / C# (detected in search result)"
        confidence = "Automated daily search lead; .NET/C# evidence detected"
    else:
        match = "Related"
        tech = "Digital/software role; .NET not explicit in search result"
        confidence = "Automated daily search lead; check vacancy for .NET/C#"

    return {
        "org": org,
        "sector": sector_for(org, link),
        "location": "UK",
        "title": title,
        "salary": "Not captured",
        "posted": clean(x.get("date") or ""),
        "closing": "",
        "match": match,
        "tech": tech,
        "url": link,
        "confidence": confidence,
    }


def main():
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        data = {"active": [], "leads": [], "history": [], "coverage": []}

    found = {}
    for q in QUERIES:
        result = search(q)
        for item in result.get("organic", []):
            job = make_item(item)
            if job:
                found[job["url"]] = job
        time.sleep(0.5)

    cleaned_existing = []
    expired_count = 0
    for existing in data.get("active", []):
        job = clean_existing_job(existing)
        if is_expired(job):
            expired_count += 1
            continue
        cleaned_existing.append(job)

    existing_urls = {x.get("url") for x in cleaned_existing if x.get("url")}
    new_items = [v for k, v in found.items() if k not in existing_urls]
    data["active"] = new_items + cleaned_existing
    data["active"] = data["active"][:200]

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
    print(f"Added {len(new_items)} new automated leads; removed {expired_count} expired vacancies; total active: {len(data['active'])}")


if __name__ == "__main__":
    main()
