from uuid import uuid4

from changes.testutils import APITestCase


class ProjectCommitIndexTest(APITestCase):
    def test_simple(self):
        fake_commit_id = uuid4()

        self.create_build(self.project)

        project = self.create_project()
        revision = self.create_revision(repository=project.repository)

        build1 = self.create_build(project, revision_sha=revision.sha)
        build2 = self.create_build(project, revision_sha=revision.sha)

        path = '/api/0/projects/{0}/commits/{1}/'.format(
            self.project.id.hex, fake_commit_id)

        resp = self.client.get(path)
        assert resp.status_code == 404

        path = '/api/0/projects/{0}/commits/{1}/'.format(
            project.id.hex, revision.sha)

        resp = self.client.get(path)
        assert resp.status_code == 200
        data = self.unserialize(resp)
        assert data['commit']['id'] == revision.sha
        assert len(data['builds']) == 2
        assert data['builds'][0]['id'] == build2.id.hex
        assert data['builds'][1]['id'] == build1.id.hex
