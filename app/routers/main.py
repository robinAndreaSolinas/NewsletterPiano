from flask import Blueprint, render_template, redirect

router = Blueprint("base", __name__, url_prefix="/")

@router.route("/ciao-mondo")
def get_users():
    return "Ciao Mondo"