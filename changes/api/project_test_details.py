from __future__ import absolute_import, division, unicode_literals

from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import joinedload, subqueryload

from changes.api.base import APIView
from changes.api.serializer.models.testgroup import TestGroupWithJobSerializer
from changes.api.serializer.models.aggregatetestgroup import AggregateTestGroupWithJobSerializer
from changes.config import db
from changes.constants import Result, Status
from changes.models import Project, AggregateTestGroup, TestGroup, Job, Source


class ProjectTestDetailsAPIView(APIView):
    def _get_project(self, project_id):
        queryset = Project.query.options(
            joinedload(Project.repository, innerjoin=True),
        )

        project = queryset.filter_by(slug=project_id).first()
        if project is None:
            project = queryset.get(project_id)
        return project

    def get(self, project_id, test_id):
        project = self._get_project(project_id)
        if not project:
            return '', 404

        test = AggregateTestGroup.query.filter(
            AggregateTestGroup.id == test_id,
            AggregateTestGroup.project_id == project_id,
        ).first()
        if not test:
            return '', 404

        cutoff = datetime.utcnow() - timedelta(days=3)

        last_job = Job.query.filter(
            Job.project_id == project_id,
            Job.result == Result.passed,
            Job.status == Status.finished,
            Job.date_created > cutoff,
            Job.source_id == Source.id,
            Source.patch_id == None,  # NOQA
        ).order_by(Job.date_created.desc()).first()

        if last_job:
            test.last_testgroup = TestGroup.query.filter(
                TestGroup.job_id == last_job.id,
                TestGroup.name_sha == AggregateTestGroup.name_sha,
            ).first()

            queryset = db.session.query(AggregateTestGroup, TestGroup).options(
                subqueryload(AggregateTestGroup.first_job),
                subqueryload(AggregateTestGroup.last_job),
                subqueryload(AggregateTestGroup.parent),
            ).join(TestGroup, and_(
                TestGroup.job_id == last_job.id,
                TestGroup.name_sha == AggregateTestGroup.name_sha,
            )).order_by(TestGroup.duration.desc())

            test_results = list(queryset.filter(
                AggregateTestGroup.parent_id == test.id,
                AggregateTestGroup.project_id == project.id,
            ))
            test_list = []
            for agg, group in test_results:
                agg.last_testgroup = group
                test_list.append(agg)

            previous_runs = list(TestGroup.query.options(
                joinedload('job', innerjoin=True),
                joinedload('job.source'),
            ).join(
                Job, TestGroup.job_id == Job.id,
            ).join(
                Source, Job.source_id == Source.id,
            ).filter(
                Source.patch_id == None,  # NOQA
                Source.revision_sha != None,  # NOQA
                Job.status == Status.finished,
                TestGroup.name_sha == test.name_sha,
                TestGroup.project_id == test.project_id,
            ).order_by(Job.date_created.desc())[:25])

        else:
            test_list = list(AggregateTestGroup.query.filter(
                AggregateTestGroup.parent_id == test.id,
                AggregateTestGroup.project_id == project.id,
            ))
            previous_runs = []

        # O(N) db calls, so dont abuse it
        context = []
        parent = test
        while parent:
            context.append(parent)
            parent = parent.parent
        context.reverse()

        extended_serializers = {
            TestGroup: TestGroupWithJobSerializer(),
        }

        context = {
            'test': self.serialize(test, {
                AggregateTestGroup: AggregateTestGroupWithJobSerializer(),
            }),
            'childTests': self.serialize(test_list, {
                AggregateTestGroup: AggregateTestGroupWithJobSerializer(),
            }),
            'context': context,
            'previousRuns': self.serialize(previous_runs, extended_serializers),
        }

        return self.respond(context)
