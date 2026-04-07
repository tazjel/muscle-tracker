# Muscle Tracker Web App - py4web Clinical Backend v2.0
from . import controllers
from . import cinematic_controller

from py4web import action
@action('ping')
def ping(): return "pong"
