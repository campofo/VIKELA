"""Emergency contacts CRUD (per user).

These are the numbers the firmware SMSs on a panic. The hardware alert endpoint
returns them (ordered by priority) so the SIM7000G can send the messages.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import EmergencyContact, User
from app.schemas import ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/api", tags=["contacts"])


@router.get("/users/{user_id}/contacts", response_model=list[ContactOut])
def list_contacts(user_id: int, session: Session = Depends(get_session)):
    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return session.exec(
        select(EmergencyContact)
        .where(EmergencyContact.user_id == user_id)
        .order_by(EmergencyContact.priority)
    ).all()


@router.post("/users/{user_id}/contacts", response_model=ContactOut, status_code=201)
def add_contact(
    user_id: int, payload: ContactCreate, session: Session = Depends(get_session)
):
    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    contact = EmergencyContact(user_id=user_id, **payload.model_dump())
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: int, payload: ContactUpdate, session: Session = Depends(get_session)
):
    contact = session.get(EmergencyContact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int, session: Session = Depends(get_session)):
    contact = session.get(EmergencyContact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    session.delete(contact)
    session.commit()
