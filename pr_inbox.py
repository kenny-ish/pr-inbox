#!/usr/bin/env python3
"""Show what people said on your pull requests to other projects since you last looked.

    GITHUB_TOKEN=... python pr_inbox.py --user octocat

It lists new reviews and comments from humans (bots and you are left out) on
your open PRs in repositories you do not own, and tells you when one of them
was merged or closed. What it has shown is kept in a small state file, so the
next run only shows what is new.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://api.github.com"


@dataclass
class Item:
    pr: str  # owner/repo#N
    kind: str  # approved, changes, review, comment, line, merged, closed
    who: str
    text: str
    url: str
    at: str = ""  # ISO time it was posted, for ordering

    def line(self) -> str:
        label = {"approved": "approved", "changes": "changes requested", "review": "review",
                 "comment": "comment", "line": "line comment", "merged": "merged", "closed": "closed"}[self.kind]
        first = self.text.strip().splitlines()[0][:100] if self.text.strip() else ""
        who = f" by {self.who}" if self.who else ""
        return f"{self.pr:<40} {label}{who}" + (f": {first}" if first else "")


class GitHub:
    def __init__(self, token: str | None):
        self.token = token

    def get(self, path: str):
        url = path if path.startswith("http") else API + path
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "pr-inbox"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)


def is_bot(user: dict) -> bool:
    return user.get("type") == "Bot" or user.get("login", "").endswith("[bot]")


def open_prs(gh, user: str) -> list[dict]:
    """Open PRs by user in repositories they do not own."""
    q = urllib.parse.quote(f"is:pr is:open author:{user} -user:{user}")
    found, page = [], 1
    while True:
        data = gh.get(f"/search/issues?q={q}&per_page=100&page={page}")
        found += data.get("items", [])
        if len(found) >= data.get("total_count", 0) or not data.get("items"):
            return found
        page += 1


def ref_of(issue: dict) -> str:
    repo = issue["repository_url"].split("/repos/", 1)[1]
    return f"{repo}#{issue['number']}"


def talk(gh, ref: str, me: str) -> list[tuple[str, Item]]:
    """(id, item) for every human comment, line comment and review on the PR, oldest first."""
    repo, num = ref.split("#")
    out = []
    for c in gh.get(f"/repos/{repo}/issues/{num}/comments?per_page=100"):
        out.append((f"c{c['id']}", c, Item(ref, "comment", c["user"]["login"], c.get("body") or "", c["html_url"],
                                          c.get("created_at", ""))))
    for c in gh.get(f"/repos/{repo}/pulls/{num}/comments?per_page=100"):
        out.append((f"l{c['id']}", c, Item(ref, "line", c["user"]["login"], c.get("body") or "", c["html_url"],
                                          c.get("created_at", ""))))
    for r in gh.get(f"/repos/{repo}/pulls/{num}/reviews?per_page=100"):
        if r.get("state") == "COMMENTED" and not r.get("body"):
            continue  # the empty shell GitHub makes around line comments; those are listed on their own
        kind = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes"}.get(r.get("state"), "review")
        out.append((f"r{r['id']}", r, Item(ref, kind, r["user"]["login"], r.get("body") or "", r.get("html_url", ""),
                                          r.get("submitted_at") or "")))
    keep = [(i, item) for i, raw, item in out if not is_bot(raw["user"]) and raw["user"]["login"].lower() != me.lower()]
    return sorted(keep, key=lambda pair: pair[1].at)


def check(gh, user: str, state: dict) -> list[Item]:
    """New items since the state was saved. Updates state in place."""
    seen = state.setdefault("seen", {})
    items: list[Item] = []
    current = {ref_of(i): i for i in open_prs(gh, user)}
    # PRs that were open last time and are not now: merged or closed.
    for ref in sorted(set(seen) - set(current)):
        repo, num = ref.split("#")
        pr = gh.get(f"/repos/{repo}/pulls/{num}")
        if pr.get("state") == "open":
            continue  # the search index lags; look again next run
        items.append(Item(ref, "merged" if pr.get("merged_at") else "closed", "", pr.get("title", ""), pr["html_url"]))
        del seen[ref]
    for ref in sorted(current):
        known = set(seen.get(ref, []))
        # A PR seen for the first time still shows what is already on it: a review
        # that came in before the first run is exactly the one you must not miss.
        new = [(i, item) for i, item in talk(gh, ref, user) if i not in known]
        items += [item for _, item in new]
        seen[ref] = sorted(known | {i for i, _ in new})
    return items


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--user", required=True, help="your GitHub login")
    p.add_argument("--state", type=Path, default=Path.home() / ".pr-inbox.json", help="state file (default ~/.pr-inbox.json)")
    p.add_argument("--json", action="store_true", help="print JSON lines instead of text")
    args = p.parse_args(argv)
    state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
    gh = GitHub(os.environ.get("GITHUB_TOKEN"))
    items = check(gh, args.user, state)
    for it in items:
        print(json.dumps(it.__dict__, ensure_ascii=False) if args.json else it.line())
    if not items and not args.json:
        print("nothing new")
    tmp = args.state.with_name(args.state.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(args.state)  # a crash mid-write must not lose what was already shown
    return 0


if __name__ == "__main__":
    sys.exit(main())
