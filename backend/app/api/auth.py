"""
Simplified authentication for this MVP.

Production note: replace this with real session/JWT auth. The important
architectural point preserved here is that EVERY endpoint resolves a
`current_user` and every document query is filtered by `user_id` — see
api/documents.py, api/analysis.py, api/chat.py. Swapping this function for
real auth (e.g. decoding a JWT from the Authorization header) does not
require touching any other file, because ownership checks already flow
through this single dependency.
"""
from fastapi import Header, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app import models


def get_current_user(
    x_user_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    """Resolves the current user from an X-User-Id header, defaulting to a
    demo user so the app works immediately without a login flow."""
    user_id = x_user_id or settings.DEMO_USER_ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        user = models.User(id=user_id, email=f"{user_id}@lexclarity.local", name="Demo User")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
