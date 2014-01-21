from __future__ import absolute_import, division

import re

from changes.config import db
from changes.db.utils import get_or_create
from changes.jobs.sync_job_step import sync_job_step
from changes.models import JobPhase

from .builder import JenkinsBuilder

BASE_XPATH = '/freeStyleProject/build[action/cause/upstreamProject="{upstream_job}" and action/cause/upstreamBuild="{build_no}"]/number'
DOWNSTREAM_XML_RE = re.compile(r'<number>(\d+)</number>')


class JenkinsFactoryBuilder(JenkinsBuilder):
    provider = 'jenkins'

    def __init__(self, *args, **kwargs):
        self.downstream_job_names = kwargs.pop('downstream_job_names', ())
        super(JenkinsFactoryBuilder, self).__init__(*args, **kwargs)

    def _get_downstream_jobs(self, job, downstream_job_name):
        xpath = BASE_XPATH.format(
            upstream_job=job.data['job_name'],
            build_no=job.data['build_no']
        )
        response = self._get_raw_response('/job/{job_name}/api/xml/'.format(
            job_name=downstream_job_name,
        ), params={
            'depth': 1,
            'xpath': xpath,
            'wrapper': 'a',
        })
        if not response:
            return []

        return map(int, DOWNSTREAM_XML_RE.findall(response))

    def sync_job(self, job):
        # for any downstream jobs, pull their results using xpath magic
        for downstream_job_name in self.downstream_job_names:
            phase, created = get_or_create(JobPhase, where={
                'job': job,
                'label': downstream_job_name,
            }, defaults={
                'status': job.status,
                'result': job.result,
                'project_id': job.project_id,
            })
            db.session.commit()

            for build_no in self._get_downstream_jobs(job, downstream_job_name):
                # XXX(dcramer): ideally we would grab this with the first query
                # but because we dont want to rely on an XML parser, we're doing
                # a second http request for build details
                step = self._create_job_step(
                    phase, downstream_job_name, build_no)

                db.session.commit()

                sync_job_step.delay_if_needed(
                    step_id=step.id.hex,
                    task_id=step.id.hex,
                    parent_task_id=job.id.hex,
                )

        super(JenkinsFactoryBuilder, self).sync_job(job)
