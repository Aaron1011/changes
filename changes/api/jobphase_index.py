from __future__ import absolute_import

from sqlalchemy.orm import joinedload, subqueryload_all

from changes.api.base import APIView
from changes.api.serializer.models.jobphase import JobPhaseWithStepsSerializer
from changes.models import Job, JobPhase, JobStep


class JobPhaseIndexAPIView(APIView):
    def get(self, job_id):
        job = Job.query.options(
            subqueryload_all(Job.phases),
            joinedload('project', innerjoin=True),
        ).get(job_id)
        if job is None:
            return '', 404

        phase_list = list(JobPhase.query.options(
            subqueryload_all(JobPhase.steps, JobStep.node),
        ).filter(
            JobPhase.job_id == job.id,
        ).order_by(JobPhase.date_started.asc(), JobPhase.date_created.asc()))

        return self.respond(self.serialize(phase_list, {
            JobPhase: JobPhaseWithStepsSerializer(),
        }))

    def get_stream_channels(self, job_id):
        return [
            'jobs:{0}'.format(job_id),
            'testgroups:{0}:*'.format(job_id),
            'logsources:{0}:*'.format(job_id),
        ]
