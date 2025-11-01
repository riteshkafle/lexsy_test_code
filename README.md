# Legal Doc Co-Pilot

A polished Flask web app that lets you upload a `.docx` legal template, detects bracket-style placeholders (e.g., `[Company Name]`), guides you through a conversational fill-in experience, and delivers a downloadable final draft.

> Built for clarity and a delightful end-to-end demo: upload → guided chat → live preview → download.


## Feature Highlights
- Upload `.docx` templates and auto-detect bracketed placeholders in document order
- Guided chat experience with progress tracking, answer history, and quick “jump to placeholder” controls
- Inline editing + clearing of any placeholder value without losing conversational context
- Live HTML preview plus a polished answer sheet for quick audits
- One-click download of the completed `.docx` with on-the-fly cleanup of temp files
- Sample YC SAFE (post-money, valuation cap) template ready to try out the full flow

## Workflow
1. **Upload** your legal template or start with the sample SAFE.
2. **Chat & fill** placeholders via the conversational assistant or jump around using the sidebar tracker.
3. **Preview & export**: review the best-effort HTML render, inspect the answer sheet, then grab the finished Word doc.


## Tech
- **Flask** (Python) + **HTMX** (no heavy front-end)
- **python-docx** for `.docx` parsing and writing
- Ready to deploy on Render / Fly / Railway / Heroku-style platforms


## Quickstart (Local)

```bash
# 1) Create & activate a venv (optional)
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt

# 3) Run
export FLASK_SECRET_KEY=$(python - <<'PY'
import secrets; print(secrets.token_hex(16))
PY
)
python app.py
# or: FLASK_SECRET_KEY=dev python app.py

# 4) Open to local host 
```


## Test Credentials
No authentication required. Everything is session-only in memory.
- Optional: set `FLASK_SECRET_KEY` in env for secure cookies.



## Sample Document
A sample YC SAFE (post-money, valuation cap only) is included at `sample_docs/sample_safe.docx`. Upload it from the home page.

Expected placeholders include:
- `[Company Name]`
- `[Investor Name]`
- `[$_____________]` (purchase amount)
- `[Date of Safe]`
- `[State of Incorporation]`
- `[Governing Law Jurisdiction]`

> Note: The app detects any bracketed token `[...]`. You can adapt your templates to that style.


## Notes & Limitations
- **Split runs in Word**: If a placeholder is split across runs, we rebuild each paragraph’s runs with a simple approach that works for most templates. If you hit an edge case, consider ensuring placeholders aren’t split stylistically across runs (bold/italic inside the brackets).
- **Preview fidelity**: The HTML preview is a convenience; the source of truth is the downloaded `.docx`.
- **Placeholder format**: The detector expects `[ ... ]`-style placeholders. You can extend `PLACEHOLDER_RE` in `utils/docx_utils.py` to support other patterns.
- **Intentional blanks**: Leaving a value empty keeps the original placeholder visible in the preview/download so you’ll never miss an unanswered token.


## Extending
- Add login (Auth0 / Clerk / Firebase) to save drafts
- Add non-bracket placeholders (e.g., `{{ like_this }}`) with Jinja-like parsing
- Add section-by-section flows and validation (dates, money, enums)
- PDF generation (e.g., `docx2pdf` or `libreoffice` in a worker)


##  Credits
- Built with python-docx
- Sample SAFE template © Y Combinator (CC BY-ND 4.0)
