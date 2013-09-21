from datetime import datetime
from sqlalchemy import Column, String, DateTime

from buildbox.db.base import Base
from buildbox.db.types.guid import GUID


class Repository(Base):
    __tablename__ = 'repository'

    repository_id = Column(GUID, primary_key=True)
    url = Column(String(200), nullable=False, unique=True)
    date_created = Column(DateTime, default=datetime.utcnow)
