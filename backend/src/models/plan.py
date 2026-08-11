"""Plan models for agent planning and observability."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """A single step in the execution plan."""

    agent_name: str = Field(..., description="Name of the agent responsible for this step")
    title: str = Field(..., description="Brief title of the step")
    description: str = Field(..., description="Detailed description of what the agent should do")
    status: Literal["pending", "in_progress", "completed", "failed"] = Field(
        default="pending", description="Current status of the step"
    )
    result: Optional[str] = Field(None, description="Result from this step (if completed)")
    note: Optional[str] = Field(None, description="Optional additional notes or reminders")


class Plan(BaseModel):
    """Complete execution plan with thought process and steps."""

    thought: str = Field(..., description="Restatement of user's requirement in your own words")
    title: str = Field(..., description="Title of the overall plan")
    steps: list[PlanStep] = Field(..., description="List of steps to execute in order")
