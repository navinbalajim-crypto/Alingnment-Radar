"""UserContact repository for managing private address book contacts."""

import uuid
from typing import Dict, List, Optional
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import normalize_email
from app.db.base import utc_now
from app.models.user_contact import UserContact


class UserContactRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_contacts_by_user(
        self,
        user_id: uuid.UUID,
        query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[UserContact]:
        stmt = select(UserContact).where(UserContact.user_id == user_id)

        if query:
            clean_query = query.strip().lower()
            stmt = stmt.where(
                or_(
                    UserContact.contact_email_normalized.ilike(f"%{clean_query}%"),
                    UserContact.contact_name.ilike(f"%{query.strip()}%"),
                )
            )

        stmt = stmt.order_by(UserContact.contact_name.asc(), UserContact.contact_email_normalized.asc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_contacts_by_user(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count(UserContact.id)).where(UserContact.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def sync_matched_contacts(
        self,
        user_id: uuid.UUID,
        matched_contacts: List[Dict[str, Optional[str]]],
    ) -> int:
        """Persist strictly registered teammate contacts, pruning unreferenced contacts for privacy."""
        existing_stmt = select(UserContact).where(UserContact.user_id == user_id)
        existing_res = await self.session.execute(existing_stmt)
        existing_contacts = {c.contact_email_normalized: c for c in existing_res.scalars().all()}

        valid_emails = set()
        count = 0
        now = utc_now()

        for item in matched_contacts:
            raw_email = item.get("contact_email")
            if not raw_email:
                continue
            normalized_email = normalize_email(raw_email)
            valid_emails.add(normalized_email)
            name = item.get("contact_name")
            resource_name = item.get("google_resource_name")

            if normalized_email in existing_contacts:
                contact = existing_contacts[normalized_email]
                if name:
                    contact.contact_name = name
                contact.contact_email = normalized_email
                if resource_name:
                    contact.google_resource_name = resource_name
                contact.updated_at = now
            else:
                contact = UserContact(
                    user_id=user_id,
                    contact_email=normalized_email,
                    contact_email_normalized=normalized_email,
                    contact_name=name,
                    google_resource_name=resource_name,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(contact)
                existing_contacts[normalized_email] = contact
            count += 1

        for email_norm, contact in list(existing_contacts.items()):
            if email_norm not in valid_emails:
                await self.session.delete(contact)

        await self.session.flush()
        return count

    async def bulk_upsert_contacts(self, user_id: uuid.UUID, contacts_data: List[Dict[str, Optional[str]]]) -> int:
        """Upsert contacts for user, avoiding duplicates on (user_id, contact_email_normalized)."""
        return await self.sync_matched_contacts(user_id, contacts_data)


    async def delete_contacts_by_user(self, user_id: uuid.UUID) -> int:
        stmt = delete(UserContact).where(UserContact.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0
