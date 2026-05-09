from pydantic import BaseModel, Field


class CreditAssessmentRequest(BaseModel):
    company_name: str = Field(..., min_length=1, description="심사 대상 기업명")
