from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey

from buildbox.db.base import Base
from buildbox.db.types.guid import GUID


class Project(Base):
    __tablename__ = 'project'

    project_id = Column(GUID, primary_key=True)
    repository_id = Column(GUID, ForeignKey('repository.repository_id'), nullable=False)
    name = Column(String(64))
    date_created = Column(DateTime, default=datetime.utcnow)
