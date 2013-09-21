from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text

from buildbox.db.base import Base
from buildbox.db.types.guid import GUID


class Revision(Base):
    __tablename__ = 'revision'

    repository_id = Column(GUID, ForeignKey('repository.id'), primary_key=True)
    sha = Column(String(40), primary_key=True)
    author_id = Column(GUID, ForeignKey('author.id'))
    date_created = Column(DateTime, default=datetime.utcnow)
    message = Column(Text)
