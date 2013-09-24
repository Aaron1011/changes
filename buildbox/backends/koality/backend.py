from __future__ import absolute_import, division

import requests
import sys

from collections import defaultdict
from datetime import datetime

from buildbox.constants import Result, Status
from buildbox.backends.base import BaseBackend
from buildbox.db.utils import create_or_update, update
from buildbox.models import (
    Revision, Author, Phase, Step, RemoteEntity, EntityType, Node,
    Build
)

# TODO: this should be stored in the db
# TODO: we could use entities to take out ID claims

PROJECT_MAP = {
    26: 'server',
}


def find_entity(session, type, remote_id, provider='koality'):
    try:
        entity = session.query(RemoteEntity).filter_by(
            type=type,
            remote_id=remote_id,
            provider=provider,
        )[0]
    except IndexError:
        return None, None

    instance = session.query(entity.type.model).get(entity.internal_id)
    return entity, instance


def get_entity(session, instance, provider='koality'):
    try:
        return session.query(RemoteEntity).filter_by(
            type=getattr(EntityType, instance.__tablename__),
            internal_id=instance.id,
            provider=provider,
        )[0]
    except IndexError:
        return None


class KoalityBackend(BaseBackend):
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self._node_cache = {}
        super(KoalityBackend, self).__init__()

    def _get_end_time(self, stage_list):
        end_time = 0
        for stage in stage_list:
            if not stage.get('endTime'):
                continue
            end_time = max((stage['endTime'], end_time))

        if end_time != 0:
            return datetime.utcfromtimestamp(end_time / 1000)
        return

    def _get_start_time(self, stage_list):
        start_time = sys.maxint
        for stage in stage_list:
            if not stage.get('startTime'):
                continue
            start_time = min((stage['startTime'], start_time))

        if start_time != 0:
            return datetime.utcfromtimestamp(start_time / 1000)
        return

        datetime.utcfromtimestamp(
            min(s['startTime'] for s in stage_list if s['startTime']) / 1000,
        )

    def _get_response(self, method, url, **kwargs):
        kwargs.setdefault('params', {})
        kwargs['params'].setdefault('key', self.api_key)
        return getattr(requests, method.lower())(url, **kwargs).json()

    def _get_node(self, node_id):
        node = self._node_cache.get(node_id)
        if node is not None:
            return node

        with self.get_session() as session:
            _, node = find_entity(
                session, EntityType.node, str(node_id))
            if node is None:
                node = Node()
                entity = RemoteEntity(
                    provider='koality', remote_id=str(node_id),
                    internal_id=node.id, type=EntityType.node,
                )
                session.add(node)
                session.add(entity)

        self._node_cache[node_id] = node

        return node

    def _sync_author(self, user):
        with self.get_session() as session:
            author = create_or_update(session, Author, values={
                'email': user['email'],
            }, where={
                'name': user['name'],
            })
        return author

    def _sync_revision(self, repository, author, commit):
        with self.get_session() as session:
            revision = create_or_update(session, Revision, values={
                'message': commit['message'],
                'author_id': author.id,
            }, where={
                'repository_id': repository.id,
                'sha': commit['sha'],
            })
        return revision

    def _sync_phase(self, build, stage_type, stage_list):
        values = {
            'build_id': build.id,
            'repository_id': build.repository_id,
            'project_id': build.project_id,
            'label': stage_type.title(),
        }

        if all((s['startTime'] and s['endTime']) for s in stage_list):
            if all(s['status'] == 'passed' for s in stage_list):
                values['result'] = Result.passed
            else:
                values['result'] = Result.failed
            values['status'] = Status.finished
        elif any(s['startTime'] for s in stage_list):
            if any(s['status'] == 'failed' for s in stage_list):
                values['result'] = Result.failed
            values['status'] = Status.in_progress
        else:
            values['status'] = Status.queued

        values['date_started'] = self._get_start_time(stage_list)
        values['date_finished'] = self._get_end_time(stage_list)

        with self.get_session() as session:
            _, phase = find_entity(
                session, EntityType.phase, stage_type)
            if phase is None:
                phase = Phase(**values)
                session.add(phase)
                entity = RemoteEntity(
                    provider='koality', remote_id=stage_type,
                    internal_id=phase.id, type=EntityType.phase,
                )
                session.add(entity)
            else:
                update(session, phase, values)

        return phase

    def _sync_step(self, build, phase, stage):
        node = self._get_node(stage['buildNode'])

        values = {
            'build_id': build.id,
            'repository_id': build.repository_id,
            'project_id': build.project_id,
            'phase_id': phase.id,
            'node_id': node.id,
            'label': stage['name'],
            'date_started': self._get_start_time([stage]),
            'date_finished': self._get_end_time([stage]),
        }

        if values['date_started'] and values['date_finished']:
            if stage['status'] == 'passed':
                values['result'] = Result.passed
            else:
                values['result'] = Result.failed
            values['status'] = Status.finished
        elif values['date_started']:
            if stage['status'] == 'failed':
                values['result'] = Result.failed
            values['status'] = Status.in_progress
        else:
            values['status'] = Status.queued

        with self.get_session() as session:
            _, step = find_entity(
                session, EntityType.step, str(stage['id']))
            if step is None:
                step = Step(**values)
                session.add(step)
                entity = RemoteEntity(
                    provider='koality', remote_id=str(stage['id']),
                    internal_id=step.id, type=EntityType.step,
                )
                session.add(entity)
            else:
                update(session, step, values)

        return step

    def _sync_build(self, project, change, stage_list=None, build=None):
        values = {
            'parent_revision_sha': change['headCommit']['sha'],
            'label': change['headCommit']['sha'],
        }

        if stage_list:
            values.update({
                'date_started': self._get_start_time(stage_list),
                'date_finished': self._get_end_time(stage_list),
            })

            # for stage in (s for s in stages if s['status'] == 'failed'):
            if values['date_started'] and values['date_finished']:
                if all(s['status'] == 'passed' for s in stage_list):
                    values['result'] = Result.passed
                else:
                    values['result'] = Result.failed
                values['status'] = Status.finished
            elif values['date_started']:
                if any(s['status'] == 'failed' for s in stage_list):
                    values['result'] = Result.failed
                values['status'] = Status.in_progress
            else:
                values['status'] = Status.queued

        author = self._sync_author(change['headCommit']['user'])
        self._sync_revision(
            project.repository, author, change['headCommit'])

        with self.get_session() as session:
            if build is None:
                _, build = find_entity(
                    session, EntityType.build, str(change['id']))
            if build is None:
                build = Build(
                    project=project,
                    repository=project.repository,
                    author=author,
                    **values
                )
                entity = RemoteEntity(
                    provider='koality',
                    type=EntityType.build,
                    remote_id=str(change['id']),
                    internal_id=build.id,
                )
                session.add(entity)
                session.add(build)
            else:
                update(session, build, values)

        return build

    def sync_build_list(self, project):
        with self.get_session() as session:
            remote_entity = get_entity(session, project)

        assert remote_entity

        project_id = remote_entity.remote_id

        change_list = self._get_response('GET', '{base_uri}/api/v/0/repositories/{project_id}/changes'.format(
            base_uri=self.base_url, project_id=project_id
        ))

        build_list = []
        for change in change_list:
            build = self._sync_build(project, change)
            build_list.append(build)

        return build_list

    def sync_build_details(self, build):
        with self.get_session() as session:
            build_entity = get_entity(session, build)
            project_entity = get_entity(session, build.project)

        assert build_entity
        assert project_entity

        remote_id = build_entity.remote_id
        project_id = project_entity.remote_id

        # {u'branch': u'verify only (api)', u'number': 760, u'createTime': 1379712159000, u'headCommit': {u'sha': u'257e20ba86c5fe1ff1e1f44613a2590bb56d7285', u'message': u'Change format of mobile gandalf info\n\nSummary: Made it more prettier\n\nTest Plan: tried it with my emulator, it works\n\nReviewers: fta\n\nReviewed By: fta\n\nCC: Reviews-Aloha, Server-Reviews\n\nDifferential Revision: https://tails.corp.dropbox.com/D23207'}, u'user': {u'lastName': u'Verifier', u'id': 3, u'firstName': u'Koality', u'email': u'verify-koala@koalitycode.com'}, u'startTime': 1379712161000, u'mergeStatus': None, u'endTime': 1379712870000, u'id': 814}
        change = self._get_response('GET', '{base_uri}/api/v/0/repositories/{project_id}/changes/{build_id}'.format(
            base_uri=self.base_url, project_id=project_id, build_id=remote_id
        ))

        # [{u'status': u'passed', u'type': u'compile', u'id': 18421, u'name': u'sudo -H -u lt3 ci/compile'}, {u'status': u'passed', u'type': u'compile', u'id': 18427, u'name': u'sudo ln -svf /usr/local/encap/python-2.7.4.1/bin/tox /usr/local/bin/tox'}, {u'status': u'passed', u'type': u'compile', u'id': 18426, u'name': u'sudo pip install tox'}, {u'status': u'passed', u'type': u'setup', u'id': 18408, u'name': u'hg'}, {u'status': u'passed', u'type': u'setup', u'id': 18409, u'name': u'provision'}, {u'status': u'passed', u'type': u'test', u'id': 18428, u'name': u'blockserver'}, {u'status': u'passed', u'type': u'test', u'id': 18429, u'name': u'dropbox'}, {u'status': u'passed', u'type': u'compile', u'id': 18422, u'name': u'sudo -H -u lt3 ci/compile'}, {u'status': u'passed', u'type': u'compile', u'id': 18431, u'name': u'sudo ln -svf /usr/local/encap/python-2.7.4.1/bin/tox /usr/local/bin/tox'}, {u'status': u'passed', u'type': u'compile', u'id': 18430, u'name': u'sudo pip install tox'}, {u'status': u'passed', u'type': u'setup', u'id': 18406, u'name': u'hg'}, {u'status': u'passed', u'type': u'setup', u'id': 18412, u'name': u'provision'}, {u'status': u'passed', u'type': u'test', u'id': 18432, u'name': u'magicpocket'}, {u'status': u'passed', u'type': u'compile', u'id': 18433, u'name': u'sudo -H -u lt3 ci/compile'}, {u'status': u'passed', u'type': u'compile', u'id': 18441, u'name': u'sudo ln -svf /usr/local/encap/python-2.7.4.1/bin/tox /usr/local/bin/tox'}, {u'status': u'passed', u'type': u'compile', u'id': 18437, u'name': u'sudo pip install tox'}, {u'status': u'passed', u'type': u'setup', u'id': 18407, u'name': u'hg'}, {u'status': u'passed', u'type': u'setup', u'id': 18411, u'name': u'provision'}, {u'status': u'passed', u'type': u'compile', u'id': 18420, u'name': u'sudo -H -u lt3 ci/compile'}, {u'status': u'passed', u'type': u'compile', u'id': 18424, u'name': u'sudo ln -svf /usr/local/encap/python-2.7.4.1/bin/tox /usr/local/bin/tox'}, {u'status': u'passed', u'type': u'compile', u'id': 18423, u'name': u'sudo pip install tox'}, {u'status': u'passed', u'type': u'setup', u'id': 18405, u'name': u'hg'}, {u'status': u'passed', u'type': u'setup', u'id': 18410, u'name': u'provision'}, {u'status': u'passed', u'type': u'test', u'id': 18425, u'name': u'metaserver'}]
        stage_list = self._get_response('GET', '{base_uri}/api/v/0/repositories/{project_id}/changes/{build_id}/stages'.format(
            base_uri=self.base_url, project_id=project_id, build_id=remote_id
        ))

        build = self._sync_build(build.project, change, stage_list, build=build)

        grouped_stages = defaultdict(list)
        for stage in stage_list:
            grouped_stages[stage['type']].append(stage)

        for stage_type, stage_list in grouped_stages.iteritems():
            stage_list.sort(key=lambda x: x['status'] == 'passed')

            phase = self._sync_phase(build, stage_type, stage_list)

            for stage in stage_list:
                self._sync_step(build, phase, stage)

        return build

    def create_build(self):
        pass
