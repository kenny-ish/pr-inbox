# pr-inbox

When you have pull requests open in several other people's projects, the review you are waiting for is easy to miss: GitHub's notifications mix it in with bot comments, CI messages and your own replies. pr-inbox answers one question: what did a person say on my PRs since I last looked?

It finds your open PRs in repositories you do not own, collects comments, line comments and reviews, drops anything written by a bot or by you, and prints what is new, oldest first. It also tells you when one of those PRs was merged or closed. What it has shown is kept in a state file, so the next run only shows new things.

Python 3.10+, standard library only.

## Usage

```
export GITHUB_TOKEN=...   # any token that can read the repositories; public ones need no scopes
python pr_inbox.py --user kenny-ish
```

The first lines of a real run on 2026-10-07:

```
gastownhall/beads#7229                   changes requested by bee-ghosttrack: Reviewed at 7577bb252e. The diagnosis and the tri-state shape are right, and the tests pin what they
gastownhall/beads#7229                   approved by bee-ghosttrack: Re-reviewed at f52664f796 (interdiff from 7577bb252e: the `stopLocked` guard, its test, one comment
gastownhall/beads#7229                   approved by bee-ghosttrack: Approved at 23dce441a3 (r3). The r2 note is closed: `stopLocked` now takes the known-not-dolt arm th
vyperlang/vyper#5291                     approved by Sporarum: LGTM !
vyperlang/vyper#5291                     line comment by pcaversaccio: open q: should we add a link here to the note below?
```

Run it again right away:

```
nothing new
```

Options:

- `--state PATH` keeps the state somewhere else (default `~/.pr-inbox.json`). One file per GitHub user.
- `--json` prints one JSON object per item (`pr`, `kind`, `who`, `text`, `url`, `at`) for piping into something else.

`kind` is one of `approved`, `changes`, `review`, `comment`, `line`, `merged`, `closed`.

## Details that matter

- A PR seen for the first time still shows everything already on it. Marking existing comments as read on first sight is the obvious way to build this, and it hides exactly the review that came in between opening the PR and the first check.
- Bots are recognized by GitHub's user type and by a `[bot]` suffix, so codecov, CI summaries and AI review bots stay out. Your own comments are left out too, case-insensitively.
- When you leave line comments, GitHub also creates an empty "commented" review around them. Those shells are skipped; the line comments themselves are listed.
- A PR that drops out of the open list is looked up once more. If it is still open (the search index can lag), it is checked again next run instead of being reported as closed.
- The state file is replaced in one step, so an interrupted run never loses what was already shown.

Repositories you own are not included (`-user:<you>` in the search), since those already notify you directly.

## Tests

```
python -m unittest -v test_pr_inbox
```

The tests run against a fake GitHub, no network.
