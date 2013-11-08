from flask import Response

from changes.api.base import APIView
from changes.api.serializer.models.testgroup import TestGroupSerializer
from changes.constants import Status, NUM_PREVIOUS_RUNS
from changes.models import Build, TestGroup, TestCase


class TestGroupWithBuildSerializer(TestGroupSerializer):
    def serialize(self, instance):
        data = super(TestGroupWithBuildSerializer, self).serialize(instance)
        data['build'] = instance.build
        return data


class TestGroupDetailsAPIView(APIView):
    def get(self, testgroup_id):
        testgroup = TestGroup.query.get(testgroup_id)
        if testgroup is None:
            return Response(status=404)

        child_testgroups = list(TestGroup.query.filter_by(
            parent_id=testgroup.id,
        ))
        for test_group in child_testgroups:
            test_group.parent = testgroup

        if child_testgroups:
            test_case = None
        else:
            # we make the assumption that if theres no child testgroups, then
            # there should be a single test case
            test_case = TestCase.query.filter(
                TestCase.groups.contains(testgroup),
            ).first()

        previous_runs = TestGroup.query.join(Build).filter(
            TestGroup.name_sha == testgroup.name_sha,
            Build.date_created < testgroup.build.date_created,
            Build.status == Status.finished,
            TestGroup.id != testgroup.id,
        ).order_by(Build.date_created.desc())[:NUM_PREVIOUS_RUNS]

        extended_serializers = {
            TestGroup: TestGroupWithBuildSerializer(),
        }

        # O(N) db calls, so dont abuse it
        context = []
        parent = testgroup
        while parent:
            context.append(parent)
            parent = parent.parent
        context.reverse()

        context = {
            'build': testgroup.build,
            'testGroup': testgroup,
            'childTestGroups': child_testgroups,
            'context': context,
            'testCase': test_case,
            'previousRuns': self.serialize(previous_runs, extended_serializers),
        }

        return self.respond(context)
