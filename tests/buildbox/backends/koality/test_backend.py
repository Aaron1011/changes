from __future__ import absolute_import

import json
import mock
import os

from datetime import datetime

from buildbox.backends.koality.backend import KoalityBackend
from buildbox.config import db
from buildbox.constants import Result, Status
from buildbox.models import (
    Repository, Project, Build, EntityType, Revision, Author,
    Phase, Step
)
from buildbox.testutils import BackendTestCase


class MockedResponse(object):
    fixture_root = os.path.join(os.path.dirname(__file__), 'fixtures')

    # used to mock out KoalityBackend._get_response
    def __init__(self, base_url):
        self.base_url = base_url

    def __call__(self, method, url, **kwargs):
        fixture = self.load_fixture(method, url, **kwargs)
        if fixture is None:
            # TODO:
            raise Exception

        fixture = os.path.join(self.fixture_root, fixture)

        with open(fixture) as fp:
            return json.load(fp)

    def load_fixture(self, method, url, **kwargs):
        if method == 'GET':
            return self.url_to_filename(url)

    def url_to_filename(self, url):
        assert url.startswith(self.base_url)
        return url[len(self.base_url) + 1:].strip('/').replace('/', '__') + '.json'


class KoalityBackendTestCase(BackendTestCase):
    backend_cls = KoalityBackend
    backend_options = {
        'base_url': 'https://koality.example.com',
        'api_key': 'a' * 12,
    }
    provider = 'koality'

    def setUp(self):
        self.patcher = mock.patch.object(
            KoalityBackend,
            '_get_response',
            MockedResponse(self.backend_options['base_url']),
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.repo = Repository(url='https://github.com/dropbox/buildbox.git')
        self.project = Project(repository=self.repo, name='test', slug='test')

        db.session.add(self.repo)
        db.session.add(self.project)


class SyncBuildListTest(KoalityBackendTestCase):
    def test_simple(self):
        backend = self.get_backend()

        project_entity = self.make_entity(EntityType.project, self.project.id, 1)

        results = backend.sync_build_list(
            project=self.project,
            project_entity=project_entity,
        )
        assert len(results) == 2


class SyncBuildDetailsTest(KoalityBackendTestCase):
    # TODO(dcramer): we should break this up into testing individual methods
    # so edge cases can be more isolated
    def test_simple(self):
        backend = self.get_backend()
        build = Build(
            repository=self.repo, project=self.project, label='pending',
        )
        db.session.add(build)

        project_entity = self.make_entity(EntityType.project, self.project.id, 1)
        build_entity = self.make_entity(EntityType.build, build.id, 1)

        backend.sync_build_details(
            build=build,
            project=self.project,
            build_entity=build_entity,
            project_entity=project_entity,
        )

        assert build.label == 'Fixing visual regression with visuals.'
        assert build.parent_revision_sha == '7ebd1f2d750064652ef5bbff72452cc19e1731e0'
        assert build.status == Status.finished
        assert build.result == Result.failed
        assert build.date_started == datetime(2013, 9, 19, 22, 15, 22)
        assert build.date_finished == datetime(2013, 9, 19, 22, 15, 36)

        revision = Revision.query.filter_by(
            sha=build.parent_revision_sha,
            repository=build.repository,
        )[0]
        author = Author.query.get(revision.author_id)
        build = Build.query.get(build.id)

        assert revision.message == 'Fixing visual regression with visuals.'

        assert author.email == 'john@example.com'
        assert author.name == 'John Developer'

        phase_list = list(Phase.query.filter_by(
            build=build,
        ))

        phase_list.sort(key=lambda x: x.date_started)

        assert len(phase_list) == 3

        assert phase_list[0].project_id == build.project_id
        assert phase_list[0].repository_id == build.repository_id
        assert phase_list[0].label == 'Setup'
        assert phase_list[0].status == Status.finished
        assert phase_list[0].result == Result.passed
        assert phase_list[0].date_started == datetime(2013, 9, 19, 22, 15, 22)
        assert phase_list[0].date_finished == datetime(2013, 9, 19, 22, 15, 33)

        assert phase_list[1].project_id == build.project_id
        assert phase_list[1].repository_id == build.repository_id
        assert phase_list[1].label == 'Compile'
        assert phase_list[1].status == Status.finished
        assert phase_list[1].result == Result.passed
        assert phase_list[1].date_started == datetime(2013, 9, 19, 22, 15, 22, 500000)
        assert phase_list[1].date_finished == datetime(2013, 9, 19, 22, 15, 34)

        assert phase_list[2].project_id == build.project_id
        assert phase_list[2].repository_id == build.repository_id
        assert phase_list[2].label == 'Test'
        assert phase_list[2].status == Status.finished
        assert phase_list[2].result == Result.failed
        assert phase_list[2].date_started == datetime(2013, 9, 19, 22, 15, 25)
        assert phase_list[2].date_finished == datetime(2013, 9, 19, 22, 15, 36)

        step_list = list(Step.query.filter_by(
            build=build,
        ))

        step_list.sort(key=lambda x: (x.date_started, x.date_created))

        assert len(step_list) == 6

        assert step_list[0].project_id == build.project_id
        assert step_list[0].repository_id == build.repository_id
        assert step_list[0].phase_id == phase_list[0].id
        assert step_list[0].label == 'ci/setup'
        assert step_list[0].status == Status.finished
        assert step_list[0].result == Result.passed
        assert step_list[0].date_started == datetime(2013, 9, 19, 22, 15, 22)
        assert step_list[0].date_finished == datetime(2013, 9, 19, 22, 15, 33)

        assert step_list[1].project_id == build.project_id
        assert step_list[1].repository_id == build.repository_id
        assert step_list[1].phase_id == phase_list[0].id
        assert step_list[1].label == 'ci/setup'
        assert step_list[1].status == Status.finished
        assert step_list[1].result == Result.passed
        assert step_list[1].date_started == datetime(2013, 9, 19, 22, 15, 22)
        assert step_list[1].date_finished == datetime(2013, 9, 19, 22, 15, 33)

        assert step_list[2].project_id == build.project_id
        assert step_list[2].repository_id == build.repository_id
        assert step_list[2].phase_id == phase_list[1].id
        assert step_list[2].label == 'ci/compile'
        assert step_list[2].status == Status.finished
        assert step_list[2].result == Result.passed
        assert step_list[2].date_started == datetime(2013, 9, 19, 22, 15, 22, 500000)
        assert step_list[2].date_finished == datetime(2013, 9, 19, 22, 15, 33, 500000)

        assert step_list[3].project_id == build.project_id
        assert step_list[3].repository_id == build.repository_id
        assert step_list[3].phase_id == phase_list[1].id
        assert step_list[3].label == 'ci/compile'
        assert step_list[3].status == Status.finished
        assert step_list[3].result == Result.passed
        assert step_list[3].date_started == datetime(2013, 9, 19, 22, 15, 23)
        assert step_list[3].date_finished == datetime(2013, 9, 19, 22, 15, 34)

        assert step_list[4].project_id == build.project_id
        assert step_list[4].repository_id == build.repository_id
        assert step_list[4].phase_id == phase_list[2].id
        assert step_list[4].label == 'ci/test'
        assert step_list[4].status == Status.finished
        assert step_list[4].result == Result.passed
        assert step_list[4].date_started == datetime(2013, 9, 19, 22, 15, 25)
        assert step_list[4].date_finished == datetime(2013, 9, 19, 22, 15, 35)

        assert step_list[5].project_id == build.project_id
        assert step_list[5].repository_id == build.repository_id
        assert step_list[5].phase_id == phase_list[2].id
        assert step_list[5].label == 'ci/test'
        assert step_list[5].status == Status.finished
        assert step_list[5].result == Result.failed
        assert step_list[5].date_started == datetime(2013, 9, 19, 22, 15, 26)
        assert step_list[5].date_finished == datetime(2013, 9, 19, 22, 15, 36)
