from datetime import datetime
from typing import List
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class URL(Base):
    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    short_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship to analytics
    analytics: Mapped[List["ClickAnalytic"]] = relationship(
        "ClickAnalytic",
        back_populates="url",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

class ClickAnalytic(Base):
    __tablename__ = "click_analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_id: Mapped[int] = mapped_column(Integer, ForeignKey("urls.id", ondelete="CASCADE"), nullable=False, index=True)
    referrer: Mapped[str] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(1000), nullable=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship back to url
    url: Mapped["URL"] = relationship("URL", back_populates="analytics")
