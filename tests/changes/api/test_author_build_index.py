from uuid import uuid4

from changes.config import db
from changes.models import Author
from changes.testutils import APITestCase


class AuthorBuildListTest(APITestCase):
    def test_simple(self):
        fake_author_id = uuid4()

        self.create_build(self.project)

        path = '/api/0/authors/{0}/builds/'.format(fake_author_id.hex)

        resp = self.client.get(path)
        assert resp.status_code == 200
        data = self.unserialize(resp)
        assert len(data['builds']) == 0

        author = Author(email='foo@example.com', name='Foo Bar')
        db.session.add(author)
        build = self.create_build(self.project, author=author)

        path = '/api/0/authors/{0}/builds/'.format(author.id.hex)

        resp = self.client.get(path)
        assert resp.status_code == 200
        data = self.unserialize(resp)
        assert len(data['builds']) == 1
        assert data['builds'][0]['id'] == build.id.hex
