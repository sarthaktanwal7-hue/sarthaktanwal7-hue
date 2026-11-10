#!/usr/bin/env python3
"""
fetch_data.py — Fetches GitHub contribution data and writes data/contributions.json
Called by the GitHub Action before generate_cards.py
"""
import json, os, pathlib, urllib.request, urllib.error, datetime, collections

USERNAME = os.environ.get("USERNAME", "sarthaktanwal7-hue")
TOKEN    = os.environ.get("GH_TOKEN", "")
DATA_DIR = pathlib.Path("data")
DATA_DIR.mkdir(exist_ok=True)

def gh_api(url: str) -> dict | list:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def main() -> None:
    print(f"Fetching data for {USERNAME}...")

    # User profile
    user = gh_api(f"https://api.github.com/users/{USERNAME}")

    # Repos
    repos_raw = gh_api(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=pushed")
    featured = [
        {
            "name": r["name"],
            "description": r.get("description") or "",
            "language": r.get("language") or "Unknown",
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "url": r["html_url"],
        }
        for r in repos_raw
        if not r["fork"] and r["name"] != USERNAME
    ][:6]  # up to 6 featured

    # Events → contribution counts per month
    try:
        events = gh_api(f"https://api.github.com/users/{USERNAME}/events/public?per_page=100")
    except Exception:
        events = []

    monthly_counts: dict[str, int] = collections.defaultdict(int)
    day_counts: dict[str, int] = collections.defaultdict(int)
    weekday_counts: dict[int, int] = collections.defaultdict(int)
    dates_active: set[str] = set()
    streak = 0

    PUSH_TYPES = {"PushEvent", "CreateEvent", "PullRequestEvent", "IssuesEvent", "CommitCommentEvent"}
    for ev in events:
        if ev.get("type") not in PUSH_TYPES:
            continue
        created = ev.get("created_at","")[:10]  # YYYY-MM-DD
        if not created:
            continue
        try:
            dt = datetime.date.fromisoformat(created)
        except ValueError:
            continue
        month_key = dt.strftime("%b")
        monthly_counts[month_key] += 1
        dates_active.add(created)
        weekday_counts[dt.weekday()] += 1

    WEEKDAY_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    busiest_wd = max(weekday_counts, key=lambda k: weekday_counts[k]) if weekday_counts else 5
    busiest_day = WEEKDAY_NAMES[busiest_wd]

    # Simple streak: consecutive days ending today
    today = datetime.date.today()
    streak = 0
    d = today
    while d.isoformat() in dates_active:
        streak += 1
        d -= datetime.timedelta(days=1)

    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly = [{"month": m, "count": monthly_counts.get(m, 0)} for m in MONTHS]

    result = {
        "username": USERNAME,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "streak": streak,
        "active_days": len(dates_active),
        "busiest_day": busiest_day,
        "total_contributions": sum(monthly_counts.values()),
        "monthly": monthly,
        "repos": featured,
    }

    out = DATA_DIR / "contributions.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"  ✓ Wrote {out}  ({len(featured)} repos, {len(dates_active)} active days)")

if __name__ == "__main__":
    main()
