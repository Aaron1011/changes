from changes.models import Build
from changes.signals import SIGNAL_MAP


def notify_listeners(build_id, signal_name):
    build = Build.query.get(build_id)
    if build is None:
        return

    signal = SIGNAL_MAP[signal_name]
    signal.send(build)
