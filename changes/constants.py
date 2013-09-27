from enum import Enum


class Status(Enum):
    unknown = 0
    queued = 1
    in_progress = 2
    finished = 3

    def __str__(self):
        return STATUS_LABELS[self]


class Result(Enum):
    unknown = 0
    passed = 1
    failed = 2
    skipped = 3
    errored = 4
    aborted = 5
    timedout = 6

    def __str__(self):
        return RESULT_LABELS[self]


class Provider(Enum):
    unknown = 0
    koality = 'koality'


STATUS_LABELS = {
    Status.unknown: 'unknown',
    Status.queued: 'queued',
    Status.in_progress: 'in progress',
    Status.finished: 'finished'
}

RESULT_LABELS = {
    Result.unknown: 'unknown',
    Result.passed: 'passed',
    Result.failed: 'failed',
    Result.skipped: 'skipped',
    Result.errored: 'errored',
    Result.aborted: 'aborted',
    Result.timedout: 'timed out'
}
