import uuid

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from buildbox.config import db
from buildbox.db.types.guid import GUID


class Project(db.Model):
    __tablename__ = 'project'

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    slug = Column(String(64), unique=True, nullable=False)
    repository_id = Column(GUID, ForeignKey('repository.id'), nullable=False)
    name = Column(String(64))
    date_created = Column(DateTime, default=datetime.utcnow)
    avg_build_time = Column(Integer)

    repository = relationship('Repository')

    def __init__(self, **kwargs):
        super(Project, self).__init__(**kwargs)
        if not self.id:
            self.id = uuid.uuid4()

    def to_dict(self):
        return {
            'id': self.id.hex,
            'slug': self.slug,
            'name': self.name,
        }
