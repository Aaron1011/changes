from datetime import datetime

from changes.constants import Result, Status
from changes.testutils import TestCase
from changes.utils.originfinder import find_failure_origins


class FindFailureOriginsTest(TestCase):
    def test_simple(self):
        build_a = self.create_build(
            self.project, result=Result.passed, status=Status.finished,
            label='build a', date_created=datetime(2013, 9, 19, 22, 15, 22))
        build_b = self.create_build(
            self.project, result=Result.failed, status=Status.finished,
            label='build b', date_created=datetime(2013, 9, 19, 22, 15, 23))
        build_c = self.create_build(
            self.project, result=Result.failed, status=Status.finished,
            label='build c', date_created=datetime(2013, 9, 19, 22, 15, 24))
        build_d = self.create_build(
            self.project, result=Result.failed, status=Status.finished,
            label='build d', date_created=datetime(2013, 9, 19, 22, 15, 25))

        self.create_testgroup(build_a, name='foo', result=Result.passed)
        self.create_testgroup(build_a, name='bar', result=Result.passed)
        self.create_testgroup(build_b, name='foo', result=Result.failed)
        self.create_testgroup(build_b, name='bar', result=Result.passed)
        self.create_testgroup(build_c, name='foo', result=Result.failed)
        self.create_testgroup(build_c, name='bar', result=Result.failed)
        foo_d = self.create_testgroup(build_d, name='foo', result=Result.failed)
        bar_d = self.create_testgroup(build_d, name='bar', result=Result.failed)

        result = find_failure_origins(build_d, [foo_d, bar_d])
        assert result == {
            foo_d: build_b,
            bar_d: build_c
        }
