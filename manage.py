#!/usr/bin/env python
from gevent import monkey
from buildbox.db import psyco_gevent

monkey.patch_all()
psyco_gevent.make_psycopg_green()

from logging.config import dictConfig


dictConfig({
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },

    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "rq.utils.ColorizingStreamHandler",
            "formatter": "console",
            "exclude": ["%(asctime)s"],
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "WARN",
    },
})


def run_gevent_server(app):
    def action(host=('h', '127.0.0.1'), port=('p', 5000)):
        """run application use gevent http server
        """
        from gevent import wsgi
        wsgi.WSGIServer((host, port), app).serve_forever()
    return action


def run_worker(app):
    def action(queues=('queues', 'default')):
        import gevent

        from buildbox.config import queue

        print 'New worker consuming from queues: %s' % (queues,)

        queues = [q.strip() for q in queues.split(' ') if q.strip()]

        while True:
            with app.app_context():
                try:
                    # Creates a worker that handle jobs in ``default`` queue.
                    worker = queue.get_worker(*queues)
                    worker.work()
                except Exception:
                    import traceback
                    traceback.print_exc()

            gevent.sleep(5)
    return action


from flask.ext.actions import Manager

from buildbox.config import create_app


app = create_app()

manager = Manager(app)
manager.add_action('runserver', run_gevent_server)
manager.add_action('worker', run_worker)

if __name__ == "__main__":
    manager.run()
