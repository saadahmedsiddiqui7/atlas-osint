# ATLAS OSINT

ATLAS is a local research workspace for lawful public-source searches and organising source links as evidence. It helps you track what you found and reviewed; it does not decide what is true.

## Quick start

You need Python 3.10 or newer and an internet connection for public searches. Download or clone this repository, open a terminal in the `atlas-osint` folder, and run the start script for your computer:

| Computer | Start command |
| --- | --- |
| Windows | Double-click `start_atlas.bat`, or run `.\start_atlas.bat` in PowerShell |
| macOS / Linux | Run `chmod +x start_atlas.sh` once, then `./start_atlas.sh` |

The first start creates a private Python environment in `.venv` and installs the required packages. Later starts reuse that environment. When startup finishes, open [http://127.0.0.1:8000](http://127.0.0.1:8000). The API reference is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Keep the terminal window open while using ATLAS. To stop it, press **Ctrl+C** in that window.

### Manual setup

If you prefer to run each setup step yourself, use the commands for your computer.

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log
```

**macOS / Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log
```

If your computer does not recognise `py` or `python3`, install Python 3.10 or newer from [python.org](https://www.python.org/downloads/) and try again. If a package install fails, check your internet connection and try the install command again.

## What ATLAS searches

Public research searches query three separate sources: the Yahoo web index through DDGS, Wikipedia, and Wikidata. Wikipedia and Wikidata use their official public APIs and do not need an account or API key. These services cover their own indexes, not every page on the internet.

The username check uses GitHub's public profile service for GitHub usernames and web indexes for possible mentions on the selected services. Search results are not a complete scan of a platform. ATLAS does not log in to accounts, access private pages, check leaked passwords, or prove who owns an account.

## Using the screens

- **Research case** asks for a question, source scope, and your stated authority before new sources are collected or saved. This self-declaration is not proof of permission or a legal review. Closing a case stops new collection; it does not delete saved records.
- **Search public sources** checks Yahoo, Wikipedia, and Wikidata separately, shows which ones responded, and labels results with their source. Saved links are marked “not checked yet” until you review them.
- **Check a public username** checks GitHub's public profile service when GitHub is selected, and searches web indexes for indexed pages about the selected service. The username is sent to those providers and is not saved by ATLAS. ATLAS stores only the platform, website domain, broad alert category, and removal status; it does not save matching text or direct page links.
- **Removal tracker** links to the service's reporting guidance and tracks whether an alert needs action, was reported, was removed, or was a false positive.
- **Evidence log** filters saved records and lets you record a review status and a short note.
- **Add a source** saves a public URL and your notes for later review.

“Reviewed” means you opened and checked the source. “Corroborated” means you found independent support. These are your assessments; ATLAS does not automatically verify claims.

Exposure alerts are clues from search-result snippets, not confirmation. Search engines do not index every page. ATLAS checks for email and phone patterns only in snippets returned for the selected service. No alert does not prove there is no exposure.

## Your saved information

ATLAS creates `atlas.db` in the project folder when it starts. It stores case, evidence, and alert records on your computer. Back up this file if you need to preserve your research. The start scripts do not delete it. The database is excluded from Git so it is not included when sharing the source code.

When ATLAS starts with an older database, it adds missing optional fields without deleting saved evidence.

## Safety and privacy

The API has no sign-in. Run ATLAS on your own computer and keep it at the local address (`127.0.0.1`) shown in the start instructions. Do not expose it to the public internet. Do not enter passwords, private account details, or sensitive personal information.

Use ATLAS only for lawful public-source research and checks on accounts you own or are authorised to investigate. A result can be incomplete or wrong, and a name match does not establish identity. ATLAS does not verify your legal authority or replace platform terms, agency review, or local law.

## For developers

Install the packages from `requirements.txt` in a Python 3.10+ environment, then run `python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log` from the project folder. Set `ATLAS_SEARCH_BACKEND` to a supported DDGS backend name to change the primary public web index; it defaults to `yahoo`.
