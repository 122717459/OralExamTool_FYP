from sqlalchemy import Column, Integer, Text, String, DateTime, func
from db import Base

class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id = Column(Integer, primary_key=True)
    input_text = Column(Text, nullable=False)      # user's transcript text
    feedback_text = Column(Text, nullable=False)   # AI feedback text
    model_name = Column(String(120), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
