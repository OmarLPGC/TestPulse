from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Test_result(Base):
    __tablename__ = 'test_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_run_id = Column(Integer, ForeignKey('test_runs.id'), nullable=False)
    test_case_id = Column(Integer, ForeignKey('test_cases.id'), nullable=False)
    outcome = Column(String(50), nullable=False)
    duration = Column(Integer, nullable=True)
    error_message = Column(String(255), nullable=True)
    traceback = Column(String(255), nullable=True)

    test_run = relationship("Test_run", back_populates="test_results")