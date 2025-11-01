import os, re, secrets, uuid
from pathlib import Path
from typing import Any
from flask import Flask, render_template, request, redirect, url_for, session, send_file, abort, make_response, after_this_request
from markupsafe import escape
from werkzeug.utils import secure_filename
from utils.docx_utils import extract_placeholders, replace_placeholders, build_preview_text

APP_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = APP_DIR / "uploads"
OUTPUT_DIR = APP_DIR / "outputs"
SAMPLE_PATH = APP_DIR / "sample_docs" / "sample_safe.docx"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))

def _is_filled(value: str | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True

def _humanize_placeholder(placeholder: str | None) -> str:
    if not placeholder:
        return ""
    inner = placeholder.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    inner = inner.replace("_", " ").replace("-", " ")
    inner = re.sub(r"\s+", " ", inner).strip()
    return inner

def _reset_state() -> None:
    session.pop("doc_path", None)
    session.pop("doc_name", None)
    session.pop("placeholders", None)
    session.pop("mapping", None)
    session.pop("current_key", None)
    session["chat_history"] = []
    session["filled_count"] = 0
    session["total_placeholders"] = 0

def _initialize_workflow(doc_path: str, placeholders: list[str], doc_name: str, intro_template: str | None = None) -> None:
    _reset_state()
    session["doc_path"] = doc_path
    session["doc_name"] = doc_name
    session["placeholders"] = placeholders
    session["mapping"] = {ph: None for ph in placeholders}
    session["total_placeholders"] = len(placeholders)
    session["filled_count"] = 0

    if placeholders:
        first = placeholders[0]
        session["current_key"] = first
        plural = "" if len(placeholders) == 1 else "s"
        friendly_first = _humanize_placeholder(first)
        template = intro_template or (
            "I found {count} placeholder{plural}. Let's start with <b>{friendly_first}</b> "
            '<span class="muted">({raw_first})</span>.'
        )
        lead = template.format(
            count=len(placeholders),
            plural=plural,
            friendly_first=friendly_first,
            raw_first=first,
        )
    else:
        session["current_key"] = None
        lead = "No placeholders found. You can still preview and download the document."

    session["chat_history"] = [{"role": "bot", "text": lead}]

@app.route("/")
def index():
    if "chat_history" not in session:
        _reset_state()
    return render_template("index.html")

@app.post("/use-sample")
def use_sample():
    doc_path = str(SAMPLE_PATH)
    placeholders = extract_placeholders(doc_path)
    intro = (
        "Sample SAFE loaded! {count} placeholder{plural} ready to fill. "
        "Let's start with <b>{friendly_first}</b> <span class=\"muted\">({raw_first})</span>."
    )
    _initialize_workflow(doc_path, placeholders, "YC SAFE (sample)", intro_template=intro)
    return redirect(url_for("chat"))

@app.post("/upload")
def upload():
    if "file" not in request.files:
        abort(400)
    uploaded_file = request.files["file"]
    filename = secure_filename(uploaded_file.filename or "")
    if not filename or not filename.lower().endswith(".docx"):
        abort(400, "Please upload a .docx file")

    unique_name = f"{Path(filename).stem}_{uuid.uuid4().hex}.docx"
    save_path = UPLOAD_DIR / unique_name
    uploaded_file.save(save_path)

    placeholders = extract_placeholders(str(save_path))
    display_name = Path(uploaded_file.filename).name if uploaded_file.filename else filename
    intro = (
        "I found {count} placeholder{plural}. Let's start with <b>{friendly_first}</b> "
        '<span class="muted">({raw_first})</span>.'
    )
    _initialize_workflow(str(save_path), placeholders, display_name, intro_template=intro)
    return redirect(url_for("chat"))

def _next_key() -> str | None:
    placeholders = session.get("placeholders") or []
    mapping = session.get("mapping") or {}
    current = session.get("current_key")
    if current and current in placeholders:
        return current
    for key in placeholders:
        if not _is_filled(mapping.get(key)):
            return key
    return None

def _get_workflow_state() -> dict[str, Any]:
    placeholders = session.get("placeholders") or []
    mapping = session.get("mapping") or {}
    next_key = _next_key()
    total = len(placeholders)
    filled = sum(1 for key in placeholders if _is_filled(mapping.get(key)))
    remaining = total - filled
    progress_pct = int((filled / total) * 100) if total else 100

    placeholder_items = []
    for key in placeholders:
        value = mapping.get(key)
        placeholder_items.append({
            "raw": key,
            "label": _humanize_placeholder(key),
            "value": value,
            "is_filled": _is_filled(value),
            "is_active": key == next_key,
        })

    session["filled_count"] = filled
    session["total_placeholders"] = total
    session["current_key"] = next_key

    state = {
        "placeholder_items": placeholder_items,
        "mapping": mapping,
        "total": total,
        "filled": filled,
        "remaining": remaining,
        "progress_pct": progress_pct,
        "next_key": next_key,
        "active_label": _humanize_placeholder(next_key) if next_key else None,
        "active_raw": next_key,
        "active_value": mapping.get(next_key) if next_key else None,
        "doc_name": session.get("doc_name"),
        "has_placeholders": bool(placeholders),
        "has_remaining": remaining > 0,
        "document_ready": bool(session.get("doc_path")),
    }
    return state

def _prompt_for_state(state: dict[str, Any]) -> str | None:
    next_key = state.get("next_key")
    if not next_key:
        return None
    label = state.get("active_label") or next_key
    prompt = f"Provide a value for <b>{label}</b>"
    raw = state.get("active_raw")
    if label and raw and label != raw:
        prompt += f" <span class=\"muted\">({raw})</span>"
    prompt += "."
    return prompt

@app.get("/chat")
def chat():
    if "chat_history" not in session:
        _reset_state()

    chat_history = session.get("chat_history") or []
    state = _get_workflow_state()
    prompt_text = _prompt_for_state(state)

    return render_template(
        "chat.html",
        chat_history=chat_history,
        prompt_text=prompt_text,
        **state,
    )

@app.post("/answer")
def answer():
    key = request.form.get("key")
    msg = request.form.get("message", "").strip()
    if not key or msg == "":
        abort(400)

    placeholders = session.get("placeholders") or []
    if key not in placeholders:
        placeholders.append(key)
        session["placeholders"] = placeholders

    chat_history = session.get("chat_history") or []
    chat_history.append({"role": "you", "text": msg})

    val = msg
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1].strip()

    mapping = session.get("mapping") or {}
    mapping[key] = val
    session["mapping"] = mapping
    session["current_key"] = None

    state = _get_workflow_state()
    nxt = state["next_key"]
    label = state.get("active_label")
    raw = state.get("active_raw")
    label_html = escape(label) if label else ""
    raw_html = escape(raw) if raw else ""

    if nxt:
        bot_msg = f"Got it. Next up: <b>{label_html}</b>"
        if label and raw and label != raw:
            bot_msg += f" <span class=\"muted\">({raw_html})</span>"
    else:
        bot_msg = "All set! Head to <b>Preview</b> to review or <b>Download</b> your .docx."

    chat_history.append({"role": "bot", "text": bot_msg})
    session["chat_history"] = chat_history

    safe_msg = escape(msg)
    response_html = (
        f'<div class="bubble you">{safe_msg}</div>'
        f'<div class="bubble bot">{bot_msg}</div>'
    )
    response = make_response(response_html)
    response.headers["HX-Trigger"] = "mapping-updated"
    return response

@app.get("/chat/sidebar")
def chat_sidebar():
    state = _get_workflow_state()
    return render_template("partials/chat_sidebar.html", **state)

@app.get("/chat/input")
def chat_input():
    state = _get_workflow_state()
    prompt_text = _prompt_for_state(state)
    return render_template("partials/chat_input.html", prompt_text=prompt_text, **state)

@app.get("/fragments/progress-badge")
def progress_badge():
    state = _get_workflow_state()
    return render_template("partials/progress_badge.html", **state)

@app.post("/set-current")
def set_current():
    key = request.form.get("key")
    placeholders = session.get("placeholders") or []
    if not key or key not in placeholders:
        abort(400)

    session["current_key"] = key
    chat_history = session.get("chat_history") or []
    friendly = _humanize_placeholder(key)
    friendly_html = escape(friendly)
    raw_html = escape(key)
    mapping = session.get("mapping") or {}
    existing_value = mapping.get(key)
    details = ""
    if _is_filled(existing_value):
        details = f" Current value: <span class=\"muted\">{escape(existing_value)}</span>."
    message = (
        f"Sure - let's update <b>{friendly_html}</b> <span class=\"muted\">({raw_html})</span>."
        f"{details}"
    )
    if not chat_history or chat_history[-1].get("text") != message:
        chat_history.append({"role": "bot", "text": message})
    session["chat_history"] = chat_history
    return redirect(url_for("chat"))

@app.post("/clear-answer")
def clear_answer():
    key = request.form.get("key")
    placeholders = session.get("placeholders") or []
    if not key or key not in placeholders:
        abort(400)

    mapping = session.get("mapping") or {}
    mapping[key] = None
    session["mapping"] = mapping
    session["current_key"] = key

    chat_history = session.get("chat_history") or []
    friendly = _humanize_placeholder(key)
    friendly_html = escape(friendly)
    raw_html = escape(key)
    message = (
        f"Cleared the answer for <b>{friendly_html}</b> <span class=\"muted\">({raw_html})</span>. "
        "Let's add it again."
    )
    chat_history.append({"role": "bot", "text": message})
    session["chat_history"] = chat_history
    return redirect(url_for("chat"))

@app.get("/preview")
def preview():
    doc_path = session.get("doc_path")
    if not doc_path:
        return redirect(url_for("index"))
    state = _get_workflow_state()
    mapping = state["mapping"]
    preview_text = build_preview_text(doc_path, mapping)
    missing_items = [item for item in state["placeholder_items"] if not item["is_filled"]]
    return render_template(
        "preview.html",
        preview_text=preview_text,
        placeholder_items=state["placeholder_items"],
        missing_items=missing_items,
        doc_name=state["doc_name"],
        total=state["total"],
        filled=state["filled"],
    )

@app.get("/download")
def download_docx():
    doc_path = session.get("doc_path")
    mapping = session.get("mapping") or {}
    if not doc_path:
        abort(404)
    doc_name = session.get("doc_name") or "document"
    safe_stem = secure_filename(Path(doc_name).stem) or "document"
    download_name = f"{safe_stem}_completed.docx"
    out_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_{download_name}"

    replace_placeholders(doc_path, mapping, str(out_path))

    @after_this_request
    def _cleanup(response):
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        return response

    return send_file(
        str(out_path),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

@app.get("/reset")
def reset():
    _reset_state()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
