from flask import Blueprint

blueprint = Blueprint(
    "problems_blueprint",
    __name__,
    url_prefix="",
    template_folder="templates",
)
