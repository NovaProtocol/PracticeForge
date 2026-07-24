from __future__ import annotations

from flask import jsonify

from apps.api import blueprint
from shared.models import get_submission_status


@blueprint.route("/submission-status/<int:solution_id>")
def submission_status(solution_id: int):
    status = get_submission_status(solution_id)
    if not status:
        return jsonify({"error": "not found"}), 404
    return jsonify(status)
