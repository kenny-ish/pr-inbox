import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pr_inbox as pi

ME = "me"


def user(login, bot=False):
    return {"login": login, "type": "Bot" if bot else "User"}


class FakeGitHub:
    """Answers the paths pr_inbox asks for from a dict; unknown paths fail loudly."""

    def __init__(self):
        self.prs = {}  # ref -> {"state", "merged_at", "comments", "lines", "reviews"}

    def add(self, ref, comments=(), lines=(), reviews=(), state="open", merged=False):
        self.prs[ref] = {"state": state, "merged_at": "2026-10-01T00:00:00Z" if merged else None,
                         "comments": list(comments), "lines": list(lines), "reviews": list(reviews)}

    def get(self, path):
        if path.startswith("/search/issues"):
            items = [{"repository_url": f"https://api.github.com/repos/{r.split('#')[0]}", "number": int(r.split("#")[1])}
                     for r, p in self.prs.items() if p["state"] == "open"]
            return {"total_count": len(items), "items": items}
        repo_num = path.split("/repos/")[1].split("?")[0]
        parts = repo_num.split("/")
        ref = f"{parts[0]}/{parts[1]}#{parts[3]}"
        pr = self.prs[ref]
        if parts[2] == "issues" and parts[4] == "comments":
            return pr["comments"]
        if parts[2] == "pulls" and len(parts) == 4:
            return {"state": pr["state"], "merged_at": pr["merged_at"], "title": "t", "html_url": "u"}
        if parts[4] == "comments":
            return pr["lines"]
        if parts[4] == "reviews":
            return pr["reviews"]
        raise AssertionError(path)


def comment(i, who, body="hi", bot=False):
    return {"id": i, "user": user(who, bot), "body": body, "html_url": f"c{i}"}


def review(i, who, state, body=""):
    return {"id": i, "user": user(who), "state": state, "body": body, "html_url": f"r{i}"}


class PrInboxTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()

    def run_check(self, state):
        return [(it.pr, it.kind, it.who) for it in pi.check(self.gh, ME, state)]

    def test_first_run_shows_what_is_already_there(self):
        # The review came in before the first run; it must not be marked read silently.
        self.gh.add("org/lib#5", reviews=[review(1, "maint", "CHANGES_REQUESTED", "please fix")])
        self.assertEqual(self.run_check({}), [("org/lib#5", "changes", "maint")])

    def test_second_run_shows_only_new(self):
        state = {}
        self.gh.add("org/lib#5", comments=[comment(1, "maint")])
        self.run_check(state)
        self.assertEqual(self.run_check(state), [])
        self.gh.prs["org/lib#5"]["reviews"].append(review(2, "maint", "APPROVED", "LGTM"))
        self.assertEqual(self.run_check(state), [("org/lib#5", "approved", "maint")])

    def test_bots_and_me_are_left_out(self):
        self.gh.add("org/lib#5", comments=[comment(1, "codecov[bot]"), comment(2, "ci", bot=True),
                                           comment(3, ME), comment(4, "Me"), comment(5, "person")])
        self.assertEqual(self.run_check({}), [("org/lib#5", "comment", "person")])

    def test_empty_review_shell_is_skipped_but_line_comment_kept(self):
        self.gh.add("org/lib#5", lines=[comment(7, "maint", "nit: rename")],
                    reviews=[review(8, "maint", "COMMENTED", "")])
        self.assertEqual(self.run_check({}), [("org/lib#5", "line", "maint")])

    def test_merged_and_closed(self):
        state = {}
        self.gh.add("org/a#1")
        self.gh.add("org/b#2")
        self.run_check(state)
        self.gh.prs["org/a#1"].update(state="closed", merged_at="2026-10-02T00:00:00Z")
        self.gh.prs["org/b#2"].update(state="closed")
        self.assertEqual(self.run_check(state), [("org/a#1", "merged", ""), ("org/b#2", "closed", "")])
        self.assertEqual(state["seen"], {})

    def test_items_are_in_time_order(self):
        early = dict(review(1, "maint", "CHANGES_REQUESTED", "fix"), submitted_at="2026-10-01T10:00:00Z")
        late = dict(comment(2, "maint", "thanks"), created_at="2026-10-02T10:00:00Z")
        self.gh.add("org/lib#5", comments=[late], reviews=[early])
        self.assertEqual([k for _, k, _ in self.run_check({})], ["changes", "comment"])

    def test_line_format(self):
        it = pi.Item("org/lib#5", "changes", "maint", "please fix\nmore", "u")
        self.assertEqual(it.line(), f"{'org/lib#5':<40} changes requested by maint: please fix")

    def test_main_keeps_state_between_runs(self):
        self.gh.add("org/lib#5", comments=[comment(1, "maint", "looks good")])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            for expected in ("comment by maint: looks good", "nothing new"):
                out = io.StringIO()
                with mock.patch.object(pi, "GitHub", return_value=self.gh), contextlib.redirect_stdout(out):
                    self.assertEqual(pi.main(["--user", ME, "--state", str(path)]), 0)
                self.assertIn(expected, out.getvalue())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["seen"], {"org/lib#5": ["c1"]})


if __name__ == "__main__":
    unittest.main()
