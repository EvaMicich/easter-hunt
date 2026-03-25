from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, Response, request, render_template, redirect
from twilio.twiml.messaging_response import MessagingResponse


load_dotenv()

app = Flask(__name__)

STATE_FILE = Path("state.json")
EXPERIENCES_FILE = Path("experiences.json")


# ----------------------------
# File loading / saving
# ----------------------------

def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_all_experiences() -> Dict[str, Dict[str, Any]]:
    registry = load_json(EXPERIENCES_FILE)
    result: Dict[str, Dict[str, Any]] = {}

    for entry in registry["experiences"]:
        key = entry["key"]
        config_file = Path(entry["config_file"])
        result[key] = load_json(config_file)

    return result


# ----------------------------
# Normalisation / matching
# ----------------------------

def normalize_free_text(text: str) -> str:
    """
    Forgiving matching for human-entered trigger phrases and commands.
    Ignores punctuation, case, and repeated spaces.
    """
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_structured_text(text: str) -> str:
    """
    For structured messages like FOUND <code>.
    Preserves hyphens in checkpoint codes.
    """
    return " ".join((text or "").strip().lower().split())


def extract_found_code(message: str) -> Optional[str]:
    message = message.strip().lower()

    if message.startswith("found-"):
        return message.replace("found-", "").strip()

    if message.startswith("found "):
        return message.replace("found ", "").strip()

    return None


def matches_command(incoming_text: str, aliases: list[str]) -> bool:
    normalized_incoming = normalize_free_text(incoming_text)
    normalized_aliases = {normalize_free_text(alias) for alias in aliases}
    return normalized_incoming in normalized_aliases


def find_experience_by_trigger(
    incoming_text: str,
    experiences: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    normalized_incoming = normalize_free_text(incoming_text)

    for experience in experiences.values():
        trigger = experience.get("start_trigger", "")
        if normalize_free_text(trigger) == normalized_incoming:
            return experience

    return None


# ----------------------------
# State helpers
# ----------------------------

def get_user_record(state: Dict[str, Any], phone: str) -> Dict[str, Any]:
    return state.get(
        phone,
        {
            "started": False,
            "finished": False,
            "step_index": 0,
            "experience_key": None,
            "started_at": None,
            "finished_at": None,
        },
    )


def get_current_experience(
    user: Dict[str, Any],
    experiences: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    key = user.get("experience_key")
    if not key:
        return None
    return experiences.get(key)


def current_checkpoint(experience: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    return experience["checkpoints"][int(user["step_index"])]


def current_objective_text(experience: Dict[str, Any], user: Dict[str, Any]) -> str:
    checkpoint = current_checkpoint(experience, user)
    return checkpoint["clue"]["text"]


def generic_not_started_message(experiences: Dict[str, Dict[str, Any]]) -> str:
    triggers = [exp.get("start_trigger", "") for exp in experiences.values() if exp.get("start_trigger")]
    if not triggers:
        return "No active experience detected."
    joined = "\n".join(f"- {t}" for t in triggers)
    return f"No active experience detected.\n\nSend one of these to begin:\n{joined}"


# ----------------------------
# Content composition
# ----------------------------

def media_tuple(media: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not media:
        return "", ""
    return (
        (media.get("url") or "").strip(),
        (media.get("type") or "").strip().lower(),
    )


def build_start_block(experience: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start response is a single combined block:
    start intro_text + clue 1 text + clue 1 media
    """
    first_checkpoint = experience["checkpoints"][0]
    clue = first_checkpoint["clue"]

    intro_text = (experience["start"].get("intro_text") or "").strip()
    clue_text = (clue.get("text") or "").strip()
    clue_media_url, clue_media_type = media_tuple(clue.get("media"))

    text_parts = []
    if intro_text:
        text_parts.append(intro_text)
    if clue_text:
        text_parts.append(clue_text)

    return {
        "text": "\n\n".join(text_parts),
        "media": {
            "url": clue_media_url,
            "type": clue_media_type,
        },
    }


def build_status_block(experience: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    checkpoint = current_checkpoint(experience, user)
    clue = checkpoint["clue"]
    clue_media_url, clue_media_type = media_tuple(clue.get("media"))

    return {
        "text": (clue.get("text") or "").strip(),
        "media": {
            "url": clue_media_url,
            "type": clue_media_type,
        },
    }


def build_finish_block(experience: Dict[str, Any]) -> Dict[str, Any]:
    finish = experience["finish"]
    finish_media_url, finish_media_type = media_tuple(finish.get("media"))

    return {
        "text": (finish.get("text") or "").strip(),
        "media": {
            "url": finish_media_url,
            "type": finish_media_type,
        },
    }


def build_progression_block(
    experience: Dict[str, Any],
    current_index: int,
) -> Dict[str, Any]:
    """
    After a successful checkpoint, build one combined block:
    current checkpoint success_text + next checkpoint clue text + next checkpoint clue media
    """
    current_cp = experience["checkpoints"][current_index]
    next_cp = experience["checkpoints"][current_index + 1]

    success_text = (current_cp.get("success_text") or "").strip()
    next_clue = next_cp["clue"]
    next_clue_text = (next_clue.get("text") or "").strip()
    next_media_url, next_media_type = media_tuple(next_clue.get("media"))

    text_parts = []
    if success_text:
        text_parts.append(success_text)
    if next_clue_text:
        text_parts.append(next_clue_text)

    return {
        "text": "\n\n".join(text_parts),
        "media": {
            "url": next_media_url,
            "type": next_media_type,
        },
    }


# ----------------------------
# TwiML rendering
# ----------------------------

def add_block_to_response(response: MessagingResponse, block: Dict[str, Any]) -> None:
    """
    Render a single outgoing block to one or two TwiML messages.

    Rules:
    - image media: text + image in one message
    - video media: video in one message, text in a second message
    - no media: text only
    """
    text = (block.get("text") or "").strip()
    media_url, media_type = media_tuple(block.get("media"))

    if media_url and media_type == "image":
        msg = response.message()
        if text:
            msg.body(text)
        msg.media(media_url)
        return

    if media_url and media_type == "video":
        video_msg = response.message()
        video_msg.media(media_url)

        if text:
            text_msg = response.message()
            text_msg.body(text)
        return

    text_msg = response.message()
    text_msg.body(text)


def twiml_text(body: str) -> Response:
    resp = MessagingResponse()
    resp.message(body)
    return Response(str(resp), mimetype="application/xml")


def twiml_block(block: Dict[str, Any]) -> Response:
    resp = MessagingResponse()
    add_block_to_response(resp, block)
    return Response(str(resp), mimetype="application/xml")


# ----------------------------
# Main webhook
# ----------------------------

@app.post("/webhook")
def webhook() -> Response:
    incoming_body = request.form.get("Body") or ""
    from_number = (request.form.get("From") or "").strip()

    if not from_number:
        return twiml_text("Missing sender number.")

    experiences = load_all_experiences()
    state = load_state()
    user = get_user_record(state, from_number)

    structured_message = normalize_structured_text(incoming_body)
    active_experience = get_current_experience(user, experiences)

    # ----------------------------
    # No active experience yet
    # ----------------------------
    if not user.get("started", False):
        matched_experience = find_experience_by_trigger(incoming_body, experiences)
        if matched_experience is not None:
            user["started"] = True
            user["finished"] = False
            user["step_index"] = 0
            user["experience_key"] = matched_experience["experience_key"]
            user["started_at"] = now_iso()
            user["finished_at"] = None

            state[from_number] = user
            save_state(state)

            return twiml_block(build_start_block(matched_experience))

    # ----------------------------
    # Active experience missing
    # ----------------------------
    if active_experience is None:
        return twiml_text("Configuration error: active experience not found.")

    commands = active_experience.get("commands", {})
    game = active_experience["game"]

    # ----------------------------
    # HELP
    # ----------------------------
    if matches_command(incoming_body, commands.get("help", ["help"])):
        return twiml_text(game["help_text"])

    # ----------------------------
    # RESET
    # ----------------------------
    if matches_command(incoming_body, commands.get("reset", ["reset"])):
        user["started"] = False
        user["finished"] = False
        user["step_index"] = 0
        user["experience_key"] = None
        user["started_at"] = None
        user["finished_at"] = None
        state[from_number] = user
        save_state(state)

        return twiml_text("Progress reset.\n\nYou can now begin a different experience.")

    # ----------------------------
    # STATUS
    # ----------------------------
    if matches_command(incoming_body, commands.get("status", ["status"])):
        if user.get("finished", False):
            return twiml_block(build_finish_block(active_experience))
        return twiml_block(build_status_block(active_experience, user))

    # ----------------------------
    # Already finished
    # ----------------------------
    if user.get("finished", False):
        return twiml_block(build_finish_block(active_experience))

    # ----------------------------
    # FOUND <code>
    # ----------------------------
    found_code = extract_found_code(structured_message)
    if found_code is not None:
        checkpoint = current_checkpoint(active_experience, user)
        expected_code = checkpoint["code"].strip().lower()

        if found_code != expected_code:
            wrong_sequence = game["wrong_sequence_text"].replace(
                "{current_objective}",
                current_objective_text(active_experience, user),
            )
            return twiml_text(wrong_sequence)

        current_index = int(user["step_index"])
        next_index = current_index + 1
        checkpoints = active_experience["checkpoints"]

        # Final checkpoint accepted
        if next_index >= len(checkpoints):
            user["finished"] = True
            user["finished_at"] = now_iso()
            state[from_number] = user
            save_state(state)
            return twiml_block(build_finish_block(active_experience))

        # Advance and send combined response
        user["step_index"] = next_index
        state[from_number] = user
        save_state(state)

        progression_block = build_progression_block(active_experience, current_index)
        return twiml_block(progression_block)

    # ----------------------------
    # Fallback
    # ----------------------------
    fallback = game["unknown_input_text"].replace(
        "{current_objective}",
        current_objective_text(active_experience, user),
    )
    return twiml_text(fallback)

# ----------------------------
# Dashboard helpers
# ----------------------------

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_iso(ts: str | None):
    return datetime.fromisoformat(ts) if ts else None


def format_duration_seconds(total_seconds: int) -> str:
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


@app.get("/admin")
def admin_dashboard():
    state = load_state()
    experiences = load_all_experiences()

    rows = []

    for phone, user in state.items():
        exp_key = user.get("experience_key")
        exp = experiences.get(exp_key) if exp_key else None

        checkpoint_label = None
        if exp and not user.get("finished"):
            idx = int(user.get("step_index", 0))
            if idx < len(exp["checkpoints"]):
                checkpoint_label = exp["checkpoints"][idx]["label"]

        started_at = user.get("started_at")
        finished_at = user.get("finished_at")

        total_time = None
        elapsed_time = None

        start_dt = parse_iso(started_at)
        finish_dt = parse_iso(finished_at)

        if start_dt and finish_dt:
            total_seconds = int((finish_dt - start_dt).total_seconds())
            total_time = format_duration_seconds(total_seconds)
        elif start_dt and not finish_dt:
            elapsed_seconds = int((datetime.now() - start_dt).total_seconds())
            elapsed_time = format_duration_seconds(elapsed_seconds)

        rows.append({
            "phone": phone,
            "experience": exp_key,
            "step_index": user.get("step_index"),
            "checkpoint": checkpoint_label,
            "finished": user.get("finished"),
            "started_at": started_at,
            "finished_at": finished_at,
            "total_time": total_time,
            "elapsed_time": elapsed_time,
        })

    return render_template("admin.html", rows=rows)

@app.post("/admin/reset/<phone>")
def reset_user(phone):
    state = load_state()

    if phone in state:
        del state[phone]
        save_state(state)

    return redirect("/admin")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)