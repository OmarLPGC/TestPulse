from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Test_case(Base):
    __tablename__ = 'test_cases'

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    node_id = Column(String(255), nullable=False)
    class_name = Column(String(255), nullable=True)
    name = Column(String(255), nullable=False)

    project = relationship("Project", back_populates="test_cases")