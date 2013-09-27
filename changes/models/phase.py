import uuid

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, backref

from changes.config import db
from changes.constants import Status, Result
from changes.db.types.enum import Enum
from changes.db.types.guid import GUID


class Phase(db.Model):
    __tablename__ = 'phase'

    id = Column(GUID, nullable=False, primary_key=True, default=uuid.uuid4)
    build_id = Column(GUID, ForeignKey('build.id'), nullable=False)
    repository_id = Column(GUID, ForeignKey('repository.id'), nullable=False)
    project_id = Column(GUID, ForeignKey('project.id'), nullable=False)
    label = Column(String(128), nullable=False)
    status = Column(Enum(Status), nullable=False, default=Status.unknown)
    result = Column(Enum(Result), nullable=False, default=Result.unknown)
    date_started = Column(DateTime)
    date_finished = Column(DateTime)
    date_created = Column(DateTime, default=datetime.utcnow)

    build = relationship('Build', backref=backref('phases', order_by='Phase.date_started'))
    project = relationship('Project')
    repository = relationship('Repository')

    def __init__(self, **kwargs):
        super(Phase, self).__init__(**kwargs)
        if self.id is None:
            self.id = uuid.uuid4()
        if self.result is None:
            self.result = Result.unknown
        if self.status is None:
            self.status = Result.unknown
        if self.date_created is None:
            self.date_created = datetime.utcnow()

    @property
    def duration(self):
        if self.date_started and self.date_finished:
            duration = (self.date_finished - self.date_started).total_seconds()
        else:
            duration = None
        return duration
