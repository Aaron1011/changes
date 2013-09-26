from __future__ import absolute_import, division

import requests
import sys

from collections import defaultdict
from datetime import datetime
from sqlalchemy.orm import joinedload

from buildbox.backends.base import BaseBackend
from buildbox.config import db
from buildbox.constants import Result, Status
from buildbox.db.utils import create_or_update
from buildbox.models import (
    Revision, Author, Phase, Step, RemoteEntity, EntityType, Node,
    Build, Project
)

# TODO: this should be stored in the db
# TODO: we could use entities to take out ID claims

PROJECT_MAP = {
    26: 'server',
}


def find_entity(type, remote_id, provider='koality'):
    try:
        entity = RemoteEntity.query.filter_by(
            type=type,
            remote_id=remote_id,
            provider=provider,
        )[0]
    except IndexError:
        return None, None

    instance = db.session.query(entity.type.model).get(entity.internal_id)
    return entity, instance


def get_entity(instance, provider='koality'):
    try:
        return db.session.query(RemoteEntity).filter_by(
            type=getattr(EntityType, instance.__tablename__),
            internal_id=instance.id,
            provider=provider,
        )[0]
    except IndexError:
        return None


class KoalityBackend(BaseBackend):
    def __init__(self, base_url, api_key, *args, **kwargs):
        self.base_url = base_url
        self.api_key = api_key
        self._node_cache = {}
        super(KoalityBackend, self).__init__(*args, **kwargs)

    def _get_end_time(self, stage_list):
        end_time = 0
        for stage in stage_list:
            if not stage.get('endTime'):
                return
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

        _, node = find_entity(
            EntityType.node, str(node_id))
        if node is None:
            node = Node()
            entity = RemoteEntity(
                provider='koality', remote_id=str(node_id),
                internal_id=node.id, type=EntityType.node,
            )
            db.session.add(node)
            db.session.add(entity)

        self._node_cache[node_id] = node

        return node

    def _sync_author(self, user):
        author = create_or_update(db.session, Author, values={
            'email': user['email'],
        }, where={
            'name': user['name'],
        })
        return author

    def _sync_revision(self, repository, author, commit):
        revision = create_or_update(db.session, Revision, values={
            'message': commit['message'],
            'author': author,
        }, where={
            'repository': repository,
            'sha': commit['sha'],
        })

        return revision

    def _sync_phase(self, build, stage_type, stage_list, phase=None):
        remote_id = '%s:%s' % (build.id.hex, stage_type)

        if phase is None:
            entity, phase = find_entity(
                EntityType.phase, remote_id)
            create_entity = entity is None
        else:
            create_entity = False

        if phase is None:
            phase = Phase()

        phase.build = build
        phase.repository = build.repository
        phase.project = build.project
        phase.label = stage_type.title()

        phase.date_started = self._get_start_time(stage_list)
        phase.date_finished = self._get_end_time(stage_list)

        # for stage in (s for s in stages if s['status'] == 'failed'):
        if phase.date_started and phase.date_finished:
            if all(s['status'] == 'passed' for s in stage_list):
                phase.result = Result.passed
            else:
                phase.result = Result.failed
            phase.status = Status.finished
        elif phase.date_started:
            if any(s['status'] == 'failed' for s in stage_list):
                phase.result = Result.failed
            else:
                phase.result = Result.unknown
            phase.status = Status.in_progress
        else:
            phase.status = Status.queued
            phase.result = Result.unknown

        if create_entity:
            entity = RemoteEntity(
                provider='koality', remote_id=remote_id,
                internal_id=phase.id, type=EntityType.phase,
            )
            db.session.add(entity)

        db.session.add(phase)

        return phase

    def _sync_step(self, build, phase, stage, step=None):
        if step is None:
            entity, step = find_entity(
                EntityType.step, str(stage['id']))
            create_entity = entity is None
        else:
            create_entity = False

        if step is None:
            step = Step()

        node = self._get_node(stage['buildNode'])

        step.build = build
        step.repository = build.repository
        step.project = build.project
        step.phase = phase
        step.node = node
        step.label = stage['name']
        step.date_started = self._get_start_time([stage])
        step.date_finished = self._get_end_time([stage])

        if step.date_started and step.date_finished:
            if stage['status'] == 'passed':
                step.result = Result.passed
            else:
                step.result = Result.failed
            step.status = Status.finished
        elif step.date_started:
            if stage['status'] == 'failed':
                step.result = Result.failed
            else:
                step.result = Result.unknown
            step.status = Status.in_progress
        else:
            step.status = Status.queued
            step.result = Result.unknown

        if create_entity:
            entity = RemoteEntity(
                provider='koality', remote_id=str(stage['id']),
                internal_id=step.id, type=EntityType.step,
            )
            db.session.add(entity)

        db.session.add(step)

        return step

    def _sync_build(self, project, change, stage_list=None, build=None):
        if build is None:
            entity, build = find_entity(
                EntityType.build, str(change['id']))
            create_entity = entity is None
        else:
            create_entity = False

        if build is None:
            build = Build()

        author = self._sync_author(change['headCommit']['user'])
        parent_revision = self._sync_revision(
            project.repository, author, change['headCommit'])

        build.label = change['headCommit']['message'].splitlines()[0][:128]
        build.author = author
        build.parent_revision_sha = parent_revision.sha
        build.parent_revision = parent_revision
        build.repository = project.repository
        build.project = project

        if stage_list:
            build.date_created = datetime.utcfromtimestamp(change['createTime'] / 1000)
            build.date_started = self._get_start_time(stage_list)
            build.date_finished = self._get_end_time(stage_list)

            if change['startTime']:
                build.date_started = min(
                    build.date_started,
                    datetime.utcfromtimestamp(change['startTime'] / 1000))

            # for stage in (s for s in stages if s['status'] == 'failed'):
            if build.date_started and build.date_finished:
                if all(s['status'] == 'passed' for s in stage_list):
                    build.result = Result.passed
                else:
                    build.result = Result.failed
                build.status = Status.finished
            elif build.date_started:
                if any(s['status'] == 'failed' for s in stage_list):
                    build.result = Result.failed
                else:
                    build.result = Result.unknown
                build.status = Status.in_progress
            else:
                build.status = Status.queued
                build.result = Result.unknown
        elif change['startTime']:
            build.date_started = datetime.utcfromtimestamp(change['startTime'] / 1000)

        if create_entity:
            entity = RemoteEntity(
                provider='koality',
                type=EntityType.build,
                remote_id=str(change['id']),
                internal_id=build.id,
            )
            db.session.add(entity)

        db.session.add(build)

        return build

    def sync_build_list(self, project, project_entity=None):
        if project_entity is None:
            project_entity = get_entity(project)
            if not project_entity:
                raise ValueError('Project does not have a remote entity')

        project_id = project_entity.remote_id

        change_list = self._get_response('GET', '{base_uri}/api/v/0/repositories/{project_id}/changes'.format(
            base_uri=self.base_url, project_id=project_id
        ))

        build_list = []
        for change in change_list:
            build = self._sync_build(project, change)
            # self.application.publish('builds', as_json(build))
            build_list.append(build)

        return build_list

    def sync_build_details(self, build, project=None, build_entity=None,
                           project_entity=None):
        if project is None:
            project = db.session.query(Project).options(
                joinedload(Project.repository),
            ).get(build.project_id)

        if project_entity is None:
            project_entity = get_entity(project)
            if not project_entity:
                raise ValueError('Project does not have a remote entity')

        if build_entity is None:
            build_entity = get_entity(build)
            if not build_entity:
                raise ValueError('Build does not have a remote entity')

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

        build = self._sync_build(project, change, stage_list, build=build)
        # self.application.publish('builds', as_json(build))

        grouped_stages = defaultdict(list)
        for stage in stage_list:
            grouped_stages[stage['type']].append(stage)

        for stage_type, stage_list in grouped_stages.iteritems():
            stage_list.sort(key=lambda x: x['status'] == 'passed')

            phase = self._sync_phase(build, stage_type, stage_list)
            # self.application.publish('phases:%s' % (build.id.hex,), as_json(phase))

            for stage in stage_list:
                self._sync_step(build, phase, stage)

        return build

    def create_build(self):
        pass
