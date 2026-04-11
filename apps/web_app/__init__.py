# Muscle Tracker Web App - py4web Clinical Backend v2.0
from . import controllers
from . import cinematic_controller
from . import scan_upload_controller
from . import dashboard_controller
from . import mesh_controller
from . import texture_controller
from . import profile_controller
from . import body_model_controller
from . import studio_controller
from . import body_scan_controller
from . import lhm_controller

from py4web import action
@action('ping')
def ping(): return "pong"
