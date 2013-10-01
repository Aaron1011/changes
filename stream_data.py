#!/usr/bin/env python

import random
import time

from datetime import datetime

from changes import mock
from changes.api.base import as_json
from changes.config import db, pubsub, create_app
from changes.constants import Result, Status
from changes.models import Change, Build

app = create_app()
app_context = app.app_context()
app_context.push()


def create_new_change(project, **kwargs):
    return mock.change(project=project, **kwargs)


def create_new_entry(project):
    new_change = (random.randint(0, 2) == 1)
    if not new_change:
        try:
            change = Change.query.all()[0]
        except IndexError:
            new_change = True

    if new_change:
        author = mock.author()
        revision = mock.revision(project.repository, author)
        change = create_new_change(
            project=project,
            author=author,
            message=revision.message,
        )

        channel = 'changes:{0}'.format(change.id.hex)
        pubsub.publish(channel, {
            'data': as_json(change),
            'event': 'change.update',
        })

    else:
        change.date_modified = datetime.utcnow()
        db.session.add(change)
        revision = mock.revision(project.repository, change.author)

    build = mock.build(
        change=change,
        author=change.author,
        parent_revision_sha=revision.sha,
        message=change.message,
        result=Result.unknown,
        status=Status.in_progress,
        date_started=datetime.utcnow(),
    )

    return build


def update_existing_entry(project):
    try:
        build = Build.query.filter(
            Build.status == Status.in_progress,
        )[0]
    except IndexError:
        return create_new_entry(project)

    build.status = Status.finished
    build.result = Result.failed if random.randint(0, 5) == 1 else Result.passed
    build.date_finished = datetime.utcnow()
    db.session.add(build)

    for _ in xrange(50):
        if build.result == Result.failed:
            result = Result.failed if random.randint(0, 5) == 1 else Result.passed
        else:
            result = Result.passed
        mock.test_result(build, result=result)

    return build


def gen(project):
    if random.randint(0, 5) == 1:
        build = create_new_entry(project)
    else:
        build = update_existing_entry(project)

    channel = 'builds:{0}:{1}'.format(build.id.hex, build.change.id.hex)
    pubsub.publish(channel, {
        'data': as_json(build),
        'event': 'build.update',
    })

    db.session.commit()

    return build


def loop():
    repository = mock.repository()
    project = mock.project(repository)

    while True:
        build = gen(project)
        print 'Pushed build {0}', build.id
        time.sleep(5)


if __name__ == '__main__':
    loop()
