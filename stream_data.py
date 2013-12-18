#!/usr/bin/env python

import random
import time

from datetime import datetime

from changes import mock
from changes.config import db, create_app
from changes.constants import Result, Status
from changes.models import Change, Build, LogSource, TestResultManager

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
    else:
        change.date_modified = datetime.utcnow()
        db.session.add(change)
        revision = mock.revision(project.repository, change.author)

    build = mock.build(
        change=change,
        author=change.author,
        revision_sha=revision.sha,
        message=change.message,
        result=Result.unknown,
        status=Status.in_progress,
        date_started=datetime.utcnow(),
    )

    logsource = LogSource(
        build=build,
        project=build.project,
        name='console',
    )
    db.session.add(logsource)
    db.session.commit()

    offset = 0
    for x in xrange(30):
        lc = mock.logchunk(source=logsource, offset=offset)
        db.session.commit()
        offset += lc.size
        time.sleep(1)

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

    test_results = []
    for _ in xrange(50):
        if build.result == Result.failed:
            result = Result.failed if random.randint(0, 5) == 1 else Result.passed
        else:
            result = Result.passed
        test_results.append(mock.test_result(build, result=result))
    TestResultManager(build).save(test_results)

    return build


def gen(project):
    if random.randint(0, 3) == 1:
        build = create_new_entry(project)
    else:
        build = update_existing_entry(project)

    db.session.commit()

    return build


def loop():
    repository = mock.repository()

    while True:
        project = mock.project(repository)

        build = gen(project)
        print 'Pushed build {0}', build.id
        time.sleep(1)


if __name__ == '__main__':
    loop()
