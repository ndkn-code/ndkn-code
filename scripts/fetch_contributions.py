"""Fetch the last year of GitHub contributions into data/contributions.json.

Needs a token in GITHUB_TOKEN (the Actions token works for public counts; a
personal token with read:user also counts private contributions if the
profile setting "Include private contributions" is on).
"""

import json
import os
import urllib.request
from pathlib import Path

LOGIN = os.environ.get("GH_LOGIN", "ndkn-code")
QUERY = """query($login:String!){user(login:$login){contributionsCollection{
  contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""

req = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
    headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as res:
    cal = json.load(res)["data"]["user"]["contributionsCollection"]["contributionCalendar"]

days = [d for w in cal["weeks"] for d in w["contributionDays"]]
out = Path(__file__).resolve().parent.parent / "data" / "contributions.json"
out.write_text(json.dumps({"login": LOGIN, "total": cal["totalContributions"], "days": days}, indent=1) + "\n")
print(f"{cal['totalContributions']} contributions, {days[0]['date']} to {days[-1]['date']}")
