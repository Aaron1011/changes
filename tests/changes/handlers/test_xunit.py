import uuid

from cStringIO import StringIO

from changes.constants import Result
from changes.models import Job
from changes.models.test import TestCase
from changes.handlers.xunit import XunitHandler


UNITTEST_RESULT_XML = """
<?xml version="1.0" encoding="utf-8"?>
<testsuite errors="1" failures="0" name="" skips="0" tests="0" time="0.077">
    <testcase classname="" name="tests.test_report" time="0">
        <failure message="collection failure">tests/test_report.py:1: in &lt;module&gt;
&gt;   import mock
E   ImportError: No module named mock</failure>
    </testcase>
    <testcase classname="tests.test_report.ParseTestResultsTest" name="test_simple" time="0.00165796279907"/>
</testsuite>
""".strip()  # remove leading whitespace to prevent xml error


def test_result_generation():
    job = Job(
        id=uuid.uuid4(),
        project_id=uuid.uuid4()
    )

    fp = StringIO(UNITTEST_RESULT_XML)

    handler = XunitHandler(job)
    results = handler.get_tests(fp)

    assert len(results) == 2

    r1 = results[0]
    assert type(r1) == TestCase
    assert r1.job_id == job.id
    assert r1.project_id == job.project_id
    assert r1.package is None
    assert r1.name == 'tests.test_report'
    assert r1.duration == 0.0
    assert r1.result == Result.failed
    assert r1.message == """tests/test_report.py:1: in <module>
>   import mock
E   ImportError: No module named mock"""
    r2 = results[1]
    assert type(r2) == TestCase
    assert r2.job_id == job.id
    assert r2.project_id == job.project_id
    assert r2.package == 'tests.test_report.ParseTestResultsTest'
    assert r2.name == 'test_simple'
    assert r2.duration == 0.00165796279907
    assert r2.result == Result.passed
    assert r2.message == ''
