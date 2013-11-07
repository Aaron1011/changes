import urlparse

from flask import render_template, current_app
from changes.api.base import MethodView


class IndexView(MethodView):
    def get(self, path=''):
        if current_app.config['SENTRY_DSN']:
            parsed = urlparse.urlparse(current_app.config['SENTRY_DSN'])
            dsn = '%s://%s@%s/%s' % (
                parsed.scheme,
                parsed.username,
                parsed.hostname + (':%s' % (parsed.port,) if parsed.port else ''),
                parsed.path,
            )
        else:
            dsn = None

        return render_template('index.html', **{
            'SENTRY_PUBLIC_DSN': dsn,
        })
