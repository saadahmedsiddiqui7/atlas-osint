# ATLAS OSINT

ATLAS is a local research workspace for lawful public-source searches and
organising source links as evidence. It is designed to help you keep track of
what you found and what you reviewed, not to decide what is true.

Research searches run three separate public-source connectors: the DDGS Yahoo
web index, Wikipedia, and Wikidata. Wikipedia and Wikidata use their official
public MediaWiki APIs and need no account or API key. Each source reports its
own result count and connection status. These sources cover their own indexes,
not every page or record on the internet.

Use it only for lawful public-source research and checks on accounts you own
or are authorised to investigate. The username check uses GitHub's public
profile endpoint for GitHub names and Yahoo, Bing, Brave, and Google web
indexes for possible mentions on 22 listed platforms. Search-index results
are not a complete platform scan. It does not log in, access private accounts,
check leaked passwords, or prove account ownership.

## Start ATLAS on Windows

Open PowerShell in this folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn main:app --reload --no-access-log
```

Then open `http://127.0.0.1:8000` in your browser. The API reference is at
`http://127.0.0.1:8000/docs`.

ATLAS stores records in `atlas.db` beside `database.py`. On startup, it adds
three optional review/search fields to the existing evidence table when they
are missing. This is an additive update; it preserves saved evidence.

## What the screens do

- **Research case** asks for a specific question, a defined source scope, and
  the operator's stated authority before any new source is collected or saved.
  This is a self-declaration, not a legal review or proof of permission. Closing
  a case blocks new collection; saved records remain available. Existing records
  from earlier ATLAS versions remain visible and are not automatically assigned
  to a case.
- **Search public sources** checks Yahoo, Wikipedia, and Wikidata separately,
  shows which sources returned results, and labels every result with its source.
  It saves usable links as evidence marked “not checked yet,” meaning ATLAS has
  not fact-checked the page.
- **Check a public username** directly checks for a public profile on GitHub and
  searches four web indexes for indexed pages about each selected
  platform. It reports these two checks separately so an empty index is not
  confused with a missing account. You must confirm that you own the account or
  have permission. The username is sent to GitHub and/or the search provider
  but is not saved by ATLAS. ATLAS stores only the platform,
  website domain, broad alert category, and removal-tracking status; it does not
  save the matching text or direct page link.
- **Removal tracker** links to the platform's official reporting guidance and
  lets you mark an alert as needing action, reported, removed, or a false
  positive.
- **Evidence log** filters saved records and lets you record a review status
  and a short note.
- **Add a source** saves a public URL and your notes for later review.

“Reviewed” means you opened and checked the source. “Corroborated” means you
found independent support for it. These are your assessments; ATLAS does not
automatically verify claims.

Exposure alerts are only clues from search-result snippets, not confirmation.
Search engines do not index every page, and ATLAS currently checks for email
and phone patterns only on the selected platform. A clean result does not mean
that no exposure exists.

## Safety and current limits

The API has no sign-in. Run it on your own computer and keep it on the local
address shown above; do not expose it to the public internet. Do not enter
passwords, private account details, or sensitive personal information. Public
search results can be incomplete or wrong, and a match does not establish who
owns an account.

Case authority is recorded from the operator's selection and confirmation; ATLAS
does not verify legal authority, determine whether an investigation is lawful,
or replace agency review, platform terms, or local law.
