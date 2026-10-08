"""Editable internal role references, never employer requirements or live job data."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

REFERENCE_PATH = Path(__file__).resolve().parents[3] / "data/knowledge/career-roles.json"
STAGES = ("resume", "role", "report")


def role_catalog():
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def list_roles():
    return [
        {key: item[key] for key in ("id", "label", "description")}
        for item in role_catalog()["items"]
    ]


def resolve_role(role_id):
    if not isinstance(role_id, str):
        raise ValueError("희망 직무를 선택해 주세요.")
    role = next((item for item in role_catalog()["items"] if item["id"] == role_id), None)
    if role is None:
        raise ValueError("목록에서 희망 직무를 선택하거나 직접 입력을 선택해 주세요.")
    return role


def reference_for(target):
    reference = deepcopy(resolve_role(target["role_id"]))
    reference.update(
        label=target["label"], source="internal_role_reference", version=role_catalog()["version"]
    )
    if target.get("focus"):
        reference["focus"] = target["focus"]
    return reference


def reference_text(reference):
    # Reuse the evidence comparison engine with explicit internal criteria.
    # The user's optional focus remains context, not an invented requirement.
    return "\n".join(reference["criteria"])


def fingerprint(draft):
    encoded = json.dumps(
        {
            "resume_text": draft["resume_text"],
            "target": draft.get("career_target"),
            "reference": role_catalog(),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def preparation_for(draft):
    if draft.get("analysis_mode") != "desired_role" or not draft.get("career_target"):
        return None
    current = fingerprint(draft)
    saved = draft.get("preparation")
    if isinstance(saved, dict) and saved.get("fingerprint") == current:
        return deepcopy(saved)
    return {
        "fingerprint": current,
        "complete": False,
        "stages": [{"id": stage, "status": "pending", "detail": "분석 대기"} for stage in STAGES],
    }
