#!/usr/bin/env python3
"""Generate a self-hosted 31-day GitHub contribution graph for the profile README."""

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape


def get_daily_contributions(username: str, token: str):
    today = datetime.now(timezone.utc)
    start = (today - timedelta(days=30)).date()

    query = """
    query($username: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """

    payload = {
        "query": query,
        "variables": {
            "username": username,
            "from": start.isoformat() + "T00:00:00Z",
            "to": today.isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
    }
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-profile-activity-generator",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL: " + json.dumps(result["errors"]))
    user = (result.get("data") or {}).get("user")
    if not user:
        raise RuntimeError("GitHub GraphQL returned no user: " + username)

    days = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    counts = {
        d["date"]: d["contributionCount"]
        for week in days
        for d in week["contributionDays"]
    }
    dates = [start + timedelta(days=i) for i in range(31)]
    values = [counts.get(day.isoformat(), 0) for day in dates]
    return dates, values


def render_svg(username: str, dates, values):
    width, height = 960, 264
    left, right, top, bottom = 62, 28, 62, 42
    plot_width = width - left - right
    plot_height = height - top - bottom
    ceiling = max(4, math.ceil(max(values) / 4) * 4)
    step = plot_width / (len(values) - 1)

    def x(i):
        return left + i * step

    def y(value):
        return top + plot_height * (1 - value / ceiling)

    points = " ".join(
        "{:.1f},{:.1f}".format(x(i), y(value))
        for i, value in enumerate(values)
    )
    area = "M {:.1f},{:.1f} L {} L {:.1f},{:.1f} Z".format(
        x(0), y(0), points.replace(" ", " L "), x(30), y(0)
    )
    grid = []
    for i in range(5):
        value = ceiling * (4 - i) // 4
        yy = top + plot_height * i / 4
        grid.append(
            '<line x1="{:.1f}" x2="{}" y1="{:.1f}" y2="{:.1f}" stroke="#30363d" stroke-dasharray="4 5"/>'
            '<text x="49" y="{:.1f}" fill="#8b949e" font-size="12" text-anchor="end">{}</text>'.format(
                left, width - right, yy, yy, yy + 4, value
            )
        )
    labels = [
        '<text x="{:.1f}" y="{}" text-anchor="middle" font-size="12" fill="#8b949e">{}</text>'.format(
            x(i), height - 16, dates[i].strftime("%d %b")
        )
        for i in (0, 5, 10, 15, 20, 25, 30)
    ]
    circles = [
        '<circle cx="{:.1f}" cy="{:.1f}" r="3" fill="#39d353">'
        '<title>{}: {} contributions</title></circle>'.format(
            x(i), y(value), dates[i].isoformat(), value
        )
        for i, value in enumerate(values)
    ]
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Recent GitHub activity for {name}">
<title>Recent GitHub activity - {name}</title>
<desc>{total} contributions from {first} through {last}.</desc>
<defs><linearGradient id="activity-area" x1="0" x2="0" y1="0" y2="1">
  <stop offset="0%" stop-color="#39d353" stop-opacity=".34"/>
  <stop offset="100%" stop-color="#39d353" stop-opacity=".02"/>
</linearGradient></defs>
<rect width="100%" height="100%" rx="12" fill="#0d1117"/>
<g font-family="system-ui, -apple-system, Segoe UI, sans-serif">
<text x="{left}" y="30" font-size="17" font-weight="600" fill="#e6edf3">Recent GitHub activity</text>
<text x="{lastx}" y="30" text-anchor="end" font-size="13" fill="#8b949e">{total} contributions · last 31 days</text>
{grid}
<path d="{area}" fill="url(#activity-area)"/>
<polyline points="{points}" fill="none" stroke="#39d353" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
{circles}
{labels}
</g>
</svg>
""".format(
        width=width, height=height, name=escape(username),
        total=sum(values), first=dates[0].isoformat(), last=dates[-1].isoformat(),
        left=left, lastx=width-right, grid="\n".join(grid), area=area,
        points=points, circles="\n".join(circles), labels="\n".join(labels),
    )


if __name__ == "__main__":
    github_token = os.environ["GITHUB_TOKEN"]
    username = os.environ.get("GITHUB_USERNAME") or os.environ["GITHUB_REPOSITORY_OWNER"]
    dates, values = get_daily_contributions(username, github_token)
    output = Path("assets/recent-activity.svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(username, dates, values), encoding="utf-8")
    print("Updated {} ({} contributions in 31 days)".format(output, sum(values)))
