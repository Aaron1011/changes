from __future__ import absolute_import, division, unicode_literals

from flask import session
from sqlalchemy.orm import joinedload

from changes.api.base import APIView
from changes.models import Author, Job


class AuthorBuildIndexAPIView(APIView):
    def _get_author(self, author_id):
        if author_id == 'me':
            if not session.get('email'):
                return
            return Author.query.filter_by(email=session['email']).first()
        return Author.query.get(author_id)

    def get(self, author_id):
        author = self._get_author(author_id)
        if not author:
            return self.respond({
                'builds': [],
            })

        queryset = Job.query.options(
            joinedload(Job.project),
            joinedload(Job.author),
        ).filter_by(
            author=author,
        ).order_by(Job.date_created.desc(), Job.date_started.desc())

        build_list = list(queryset)[:25]

        context = {
            'builds': build_list,
        }

        return self.respond(context)

    def get_stream_channels(self, author_id):
        author = self._get_author(author_id)
        if not author:
            return []
        return ['authors:{0}:jobs'.format(author.id.hex)]
