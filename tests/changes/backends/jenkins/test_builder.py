from __future__ import absolute_import

import mock
import os.path
import responses

from flask import current_app
from uuid import UUID

from changes.config import db
from changes.constants import Status, Result
from changes.models import (
    Repository, Project, RemoteEntity, TestCase, Patch, LogSource, LogChunk
)
from changes.backends.jenkins.builder import JenkinsBuilder, chunked
from changes.testutils import BackendTestCase, SAMPLE_DIFF


class BaseTestCase(BackendTestCase):
    provider = 'jenkins'
    builder_cls = JenkinsBuilder
    builder_options = {
        'base_url': 'http://jenkins.example.com',
        'job_name': 'server',
    }

    def setUp(self):
        self.repo = Repository(url='https://github.com/dropbox/changes.git')
        self.project = Project(repository=self.repo, name='test', slug='test')

        db.session.add(self.repo)
        db.session.add(self.project)

    def get_builder(self, **options):
        base_options = self.builder_options.copy()
        base_options.update(options)
        return self.builder_cls(app=current_app, **base_options)

    def load_fixture(self, filename):
        filepath = os.path.join(
            os.path.dirname(__file__),
            filename,
        )
        with open(filepath, 'rb') as fp:
            return fp.read()


# TODO(dcramer): these tests need to ensure we're passing the right parameters
# to jenkins
class CreateBuildTest(BaseTestCase):
    @responses.activate
    def test_queued_creation(self):
        responses.add(
            responses.POST, 'http://jenkins.example.com/job/server/build/api/json/',
            body='',
            status=201)

        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/api/json/',
            body=self.load_fixture('fixtures/GET/queue_list.json'))

        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/api/json/',
            body=self.load_fixture('fixtures/GET/job_list.json'))

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'))

        builder = self.get_builder()
        builder.create_job(job)

        assert job.data == {
            'build_no': None,
            'item_id': 13,
            'job_name': 'server',
            'queued': True,
        }

    @responses.activate
    def test_active_creation(self):
        responses.add(
            responses.POST, 'http://jenkins.example.com/job/server/build/api/json/',
            body='',
            status=201)

        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/api/json/',
            body=self.load_fixture('fixtures/GET/queue_list.json'))

        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/api/json/',
            body=self.load_fixture('fixtures/GET/job_list.json'))

        job = self.create_job(
            self.project,
            id=UUID('f9481a17aac446718d7893b6e1c6288b'))

        builder = self.get_builder()
        builder.create_job(job)

        assert job.data == {
            'build_no': 1,
            'item_id': None,
            'job_name': 'server',
            'queued': False,
        }

    @responses.activate
    def test_patch(self):
        responses.add(
            responses.POST, 'http://jenkins.example.com/job/server/build/api/json/',
            body='',
            status=201)

        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/api/json/',
            body=self.load_fixture('fixtures/GET/queue_list.json'))

        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/api/json/',
            body=self.load_fixture('fixtures/GET/job_list.json'))

        patch = Patch(
            repository=self.repo,
            project=self.project,
            parent_revision_sha='7ebd1f2d750064652ef5bbff72452cc19e1731e0',
            label='D1345',
            diff=SAMPLE_DIFF,
        )
        db.session.add(patch)

        job = self.create_job(
            self.project,
            patch=patch,
            revision_sha=patch.parent_revision_sha,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8')
        )

        builder = self.get_builder()
        builder.create_job(job)

    @responses.activate
    def test_with_entity(self):
        project_entity = RemoteEntity(
            provider=self.provider,
            internal_id=self.project.id,
            remote_id='server-foo',
            type='build',
        )
        db.session.add(project_entity)

        responses.add(
            responses.POST, 'http://jenkins.example.com/job/server-foo/build/api/json/',
            body='',
            status=201)

        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/api/json/',
            body=self.load_fixture('fixtures/GET/queue_list.json'))

        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server-foo/api/json/',
            body=self.load_fixture('fixtures/GET/job_list.json'))

        job = self.create_job(
            self.project,
            id=UUID('f9481a17aac446718d7893b6e1c6288b'))

        builder = self.get_builder(job_name=None)
        builder.create_job(job)

        assert job.data == {
            'build_no': 1,
            'item_id': None,
            'job_name': 'server-foo',
            'queued': False,
        }


class SyncBuildTest(BaseTestCase):
    @responses.activate
    def test_waiting_in_queue(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/item/13/api/json/',
            body=self.load_fixture('fixtures/GET/queue_details_pending.json'))

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': None,
                'item_id': 13,
                'job_name': 'server',
                'queued': True,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        assert job.status == Status.queued

    @responses.activate
    def test_cancelled_in_queue(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/item/13/api/json/',
            body=self.load_fixture('fixtures/GET/queue_details_cancelled.json'))

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': None,
                'item_id': 13,
                'job_name': 'server',
                'queued': True,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        assert job.status == Status.finished
        assert job.result == Result.aborted

    @responses.activate
    def test_queued_to_active(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/queue/item/13/api/json/',
            body=self.load_fixture('fixtures/GET/queue_details_building.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/api/json/',
            body=self.load_fixture('fixtures/GET/job_details_building.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/logText/progressiveHtml/?start=0',
            match_querystring=True,
            adding_headers={'X-Text-Size': '0'},
            body='')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': None,
                'item_id': 13,
                'job_name': 'server',
                'queued': True,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        assert job.data['build_no'] == 2
        assert job.status == Status.in_progress
        assert job.date_started is not None

    @responses.activate
    def test_success_result(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/api/json/',
            body=self.load_fixture('fixtures/GET/job_details_success.json'))

        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/logText/progressiveHtml/?start=0',
            match_querystring=True,
            adding_headers={'X-Text-Size': '0'},
            body='')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': 2,
                'item_id': 13,
                'job_name': 'server',
                'queued': False,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        assert job.data['build_no'] == 2
        assert job.status == Status.finished
        assert job.result == Result.passed
        assert job.duration == 8875
        assert job.date_finished is not None

    @responses.activate
    def test_failed_result(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/api/json/',
            body=self.load_fixture('fixtures/GET/job_details_failed.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/logText/progressiveHtml/?start=0',
            match_querystring=True,
            adding_headers={'X-Text-Size': '0'},
            body='')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': 2,
                'item_id': 13,
                'job_name': 'server',
                'queued': False,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        assert job.data['build_no'] == 2
        assert job.status == Status.finished
        assert job.result == Result.failed
        assert job.duration == 8875
        assert job.date_finished is not None

    @responses.activate
    def test_does_sync_test_report(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/api/json/',
            body=self.load_fixture('fixtures/GET/job_details_with_test_report.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/testReport/api/json/',
            body=self.load_fixture('fixtures/GET/job_test_report.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/logText/progressiveHtml/?start=0',
            match_querystring=True,
            adding_headers={'X-Text-Size': '0'},
            body='')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': 2,
                'item_id': 13,
                'job_name': 'server',
                'queued': False,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        test_list = sorted(TestCase.query.filter_by(job=job), key=lambda x: x.duration)

        assert len(test_list) == 2
        assert test_list[0].name == 'Test'
        assert test_list[0].package == 'tests.changes.handlers.test_xunit'
        assert test_list[0].result == Result.skipped
        assert test_list[0].message == 'collection skipped'
        assert test_list[0].duration == 0

        assert test_list[1].name == 'test_simple'
        assert test_list[1].package == 'tests.changes.api.test_build_details.BuildDetailsTest'
        assert test_list[1].result == Result.passed
        assert test_list[1].message == ''
        assert test_list[1].duration == 155

    @responses.activate
    def test_does_sync_log(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/api/json/',
            body=self.load_fixture('fixtures/GET/job_details_failed.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/logText/progressiveHtml/?start=0',
            match_querystring=True,
            adding_headers={'X-Text-Size': '7'},
            body='Foo bar')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': 2,
                'item_id': 13,
                'job_name': 'server',
                'queued': False,
            },
        )

        builder = self.get_builder()
        builder.sync_job(job)

        source = LogSource.query.filter_by(job=job).first()
        assert source.name == 'console'
        assert source.project == self.project
        assert source.date_created == job.date_started

        chunks = list(LogChunk.query.filter_by(
            source=source,
        ).order_by(LogChunk.date_created.asc()))
        assert len(chunks) == 1
        assert chunks[0].job_id == job.id
        assert chunks[0].project_id == self.project.id
        assert chunks[0].offset == 0
        assert chunks[0].size == 7
        assert chunks[0].text == 'Foo bar'

        assert job.data.get('log_offset') == 7

    @responses.activate
    @mock.patch('changes.backends.jenkins.builder.queue')
    def test_does_fire_sync_artifacts(self, queue):
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/api/json/',
            body=self.load_fixture('fixtures/GET/job_details_with_artifacts.json'))
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/logText/progressiveHtml/?start=0',
            match_querystring=True,
            adding_headers={'X-Text-Size': '0'},
            body='')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': 2,
                'item_id': 13,
                'job_name': 'server',
                'queued': False,
            },
        )
        builder = self.get_builder()
        builder.sync_job(job)

        assert len(queue.mock_calls) == 2

        queue.delay.assert_any_call('sync_artifact', kwargs={
            'job_id': job.id.hex,
            'artifact': {
                "displayPath": "foobar.log",
                "fileName": "foobar.log",
                "relativePath": "artifacts/foobar.log"
            },
        })

        queue.delay.assert_any_call('sync_artifact', kwargs={
            'job_id': job.id.hex,
            'artifact': {
                "displayPath": "tests.xml",
                "fileName": "tests.xml",
                "relativePath": "artifacts/tests.xml"
            },
        })

    @responses.activate
    def test_sync_artifact(self):
        responses.add(
            responses.GET, 'http://jenkins.example.com/job/server/2/artifact/artifacts/foobar.log',
            body='hello world')

        job = self.create_job(
            self.project,
            id=UUID('81d1596fd4d642f4a6bdf86c45e014e8'),
            data={
                'build_no': 2,
                'item_id': 13,
                'job_name': 'server',
                'queued': False,
            },
        )

        builder = self.get_builder()
        builder.sync_artifact(job, {
            "displayPath": "foobar.log",
            "fileName": "foobar.log",
            "relativePath": "artifacts/foobar.log"
        })

        source = LogSource.query.filter(
            LogSource.job_id == job.id,
            LogSource.name == 'foobar.log',
        ).first()
        assert source is not None
        assert source.project == self.project

        chunks = list(LogChunk.query.filter_by(
            source=source,
        ).order_by(LogChunk.date_created.asc()))
        assert len(chunks) == 1
        assert chunks[0].job_id == job.id
        assert chunks[0].project_id == self.project.id
        assert chunks[0].offset == 0
        assert chunks[0].size == 11
        assert chunks[0].text == 'hello world'


class ChunkedTest(TestCase):
    def test_simple(self):
        foo = 'aaa\naaa\naaa\n'

        result = list(chunked(foo, 5))
        assert len(result) == 2
        assert result[0] == 'aaa\naaa\n'
        assert result[1] == 'aaa\n'

        result = list(chunked(foo, 8))

        assert len(result) == 1
        assert result[0] == 'aaa\naaa\naaa\n'

        result = list(chunked(foo, 4))

        assert len(result) == 3
        assert result[0] == 'aaa\n'
        assert result[1] == 'aaa\n'
        assert result[2] == 'aaa\n'

        foo = 'a' * 10

        result = list(chunked(foo, 2))
        assert len(result) == 5
        assert all(r == 'aa' for r in result)

        foo = 'aaaa\naaaa'

        result = list(chunked(foo, 3))
        assert len(result) == 3
