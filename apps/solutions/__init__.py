from flask import Blueprint

blueprint = Blueprint(
    "solutions_blueprint",
    __name__,
    url_prefix="",
    template_folder="templates",
)
