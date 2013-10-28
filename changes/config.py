import flask
import os
import os.path

from datetime import timedelta
from flask.ext.sqlalchemy import SQLAlchemy
from raven.contrib.flask import Sentry

from changes.ext.celery import Celery
from changes.ext.pubsub import PubSub

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

db = SQLAlchemy(session_options={
    'autoflush': True,
})
pubsub = PubSub()
queue = Celery()
sentry = Sentry(logging=True)


def create_app(**config):
    app = flask.Flask(__name__,
                      static_folder=None,
                      template_folder=os.path.join(PROJECT_ROOT, 'templates'))

    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql:///changes'
    app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    app.config['REDIS_URL'] = 'redis://localhost/0'
    app.config['RQ_DEFAULT_RESULT_TTL'] = 0
    app.config['DEBUG'] = True
    app.config['HTTP_PORT'] = 5000
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    app.config['CELERY_ACKS_LATE'] = True
    app.config['CELERY_BROKER_URL'] = 'redis://localhost/0'

    app.config['EVENT_LISTENERS'] = (
        # ('import.path', 'build.finished'),
    )

    # celerybeat must be running for our cleanup tasks to execute
    # e.g. celery worker -B
    app.config['CELERYBEAT_SCHEDULE'] = {
        'cleanup-builds': {
            'task': 'cleanup_builds',
            'schedule': timedelta(minutes=1),
        },
    }
    app.config['CELERY_TIMEZONE'] = 'UTC'

    app.config['SENTRY_DSN'] = None

    app.config['JENKINS_URL'] = None
    app.config['JENKINS_TOKEN'] = None

    app.config['KOALITY_URL'] = None
    app.config['KOALITY_API_KEY'] = None

    # CHANGES_CONF=/etc/changes.conf.py
    app.config.from_envvar('CHANGES_CONF', silent=True)

    app.config.update(config)

    db.init_app(app)
    pubsub.init_app(app)
    queue.init_app(app)
    sentry.init_app(app)

    from raven.contrib.celery import register_signal
    register_signal(sentry)

    # TODO: these can be moved to wsgi app entrypoints
    configure_api_routes(app)
    configure_web_routes(app)

    configure_database_listeners(app)
    configure_event_listeners(app)
    configure_jobs(app)

    return app


def configure_api_routes(app):
    from changes.api.build_details import BuildDetailsAPIView
    from changes.api.build_index import BuildIndexAPIView
    from changes.api.build_retry import BuildRetryAPIView
    from changes.api.change_details import ChangeDetailsAPIView
    from changes.api.change_index import ChangeIndexAPIView
    from changes.api.project_details import ProjectDetailsAPIView
    from changes.api.test_details import TestDetailsAPIView

    app.add_url_rule(
        '/api/0/builds/', view_func=BuildIndexAPIView.as_view('api-build-list'))
    app.add_url_rule(
        '/api/0/builds/<build_id>/', view_func=BuildDetailsAPIView.as_view('api-build-details'))
    app.add_url_rule(
        '/api/0/builds/<build_id>/retry/', view_func=BuildRetryAPIView.as_view('api-build-retry'))
    app.add_url_rule(
        '/api/0/changes/', view_func=ChangeIndexAPIView.as_view('api-change-list'))
    app.add_url_rule(
        '/api/0/changes/<change_id>/', view_func=ChangeDetailsAPIView.as_view('api-change-details'))
    app.add_url_rule(
        '/api/0/changes/<change_id>/builds/', view_func=BuildIndexAPIView.as_view('api-change-build-list'))
    app.add_url_rule(
        '/api/0/projects/<project_id>/', view_func=ProjectDetailsAPIView.as_view('api-project-details'))
    app.add_url_rule(
        '/api/0/tests/<test_id>/', view_func=TestDetailsAPIView.as_view('api-change-test-details'))


def configure_web_routes(app):
    from changes.web.index import IndexView
    from changes.web.static import StaticView

    app.add_url_rule(
        '/static/<path:filename>',
        view_func=StaticView.as_view('static', root=os.path.join(PROJECT_ROOT, 'static')))
    app.add_url_rule(
        '/partials/<path:filename>',
        view_func=StaticView.as_view('partials', root=os.path.join(PROJECT_ROOT, 'partials')))
    app.add_url_rule(
        '/<path:path>', view_func=IndexView.as_view('index-path'))
    app.add_url_rule(
        '/', view_func=IndexView.as_view('index'))


def configure_jobs(app):
    from changes.jobs.cleanup_builds import cleanup_builds
    from changes.jobs.sync_build import sync_build

    queue.register('cleanup_builds', cleanup_builds)
    queue.register('sync_build', sync_build)


def configure_database_listeners(app):
    from sqlalchemy import event
    from changes import events
    from changes.models import Build, Change, Phase, Test

    event.listen(Build, 'after_insert', events.publish_build_update)
    event.listen(Change, 'after_insert', events.publish_change_update)
    event.listen(Phase, 'after_insert', events.publish_phase_update)
    event.listen(Test, 'after_insert', events.publish_test_update)

    event.listen(Build, 'after_update', events.publish_build_update)
    event.listen(Change, 'after_update', events.publish_change_update)
    event.listen(Phase, 'after_update', events.publish_phase_update)
    event.listen(Test, 'after_update', events.publish_test_update)


def configure_event_listeners(app):
    from changes.signals import register_listener
    from changes.utils.imports import import_string

    for func_path, signal_name in app.config['EVENT_LISTENERS']:
        func = import_string(func_path)
        register_listener(func, signal_name)
