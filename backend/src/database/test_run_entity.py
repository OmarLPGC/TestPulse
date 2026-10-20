from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Test_run(Base):
    __tablename__ = 'test_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    commit_sha = Column(String(40), nullable=False)
    branch = Column(String(255), nullable=False)
    report_sha = Column(String(64), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    ingested_at = Column(DateTime, nullable=False)
    duration = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False)

    project = relationship("Project", back_populates="test_runs")