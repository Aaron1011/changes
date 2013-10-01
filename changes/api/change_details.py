from sqlalchemy.orm import joinedload

from changes.api.base import APIView
from changes.models import Change


class ChangeDetailsAPIView(APIView):
    def get(self, change_id):
        change = Change.query.options(
            joinedload(Change.project),
            joinedload(Change.author),
        ).get(change_id)

        context = {
            'change': change,
        }

        return self.respond(context)

    def get_stream_channels(self, change_id):
        return ['change:{0}'.format(change_id)]
