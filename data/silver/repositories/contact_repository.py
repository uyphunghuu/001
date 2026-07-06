from data.silver.models.contact import Contact
from data.silver.repositories.base import BaseRepository


class ContactRepository(BaseRepository):
    def save(self, data: dict) -> str:
        with self.session as s:
            existing = s.query(Contact).filter(
                Contact.source == data.get("source", ""),
                Contact.email == data.get("email", ""),
            ).first()
            if existing:
                for k, v in data.items():
                    if v is not None:
                        setattr(existing, k, v)
                s.commit()
                return str(existing.id)
            contact = Contact(**data)
            s.add(contact)
            s.commit()
            return str(contact.id)

    def find_by_email(self, email: str) -> Contact | None:
        with self.session as s:
            return s.query(Contact).filter(Contact.email == email).first()

    def search(self, query: str, limit: int = 20):
        with self.session as s:
            return s.query(Contact).filter(
                Contact.name.ilike(f"%{query}%") | Contact.email.ilike(f"%{query}%")
            ).limit(limit).all()
