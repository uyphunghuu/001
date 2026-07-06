"""Extract agent nodes from Silver records."""

from data.gold.repositories.node_repository import NodeRepository


class AgentExtractor:
    def __init__(self):
        self.node_repo = NodeRepository()

    def get_or_create(self, email: str, name: str | None = None, source: str = "") -> str | None:
        if not email:
            return None

        existing = self.node_repo.find_agent_by_email(email)
        if existing:
            return str(existing.id)

        agent_data = {
            "type": "agent",
            "subtype": "person",
            "name": name or email,
            "properties": {
                "email": email,
                "name": name or email,
            },
            "source_ref": {
                "table": "agents",
                "id": email,
                "source": source or "unknown",
                "source_type": "agent",
                "checksum": "",
            },
            "confidence": 0.9,
            "importance": 2,
        }
        return self.node_repo.save(agent_data)

    def extract_from_communication(self, comm) -> list[dict]:
        results = []
        sender_id = self.get_or_create(comm.sender_email, comm.sender_name, comm.source)
        if sender_id:
            results.append({"agent_id": sender_id, "role": "sender", "email": comm.sender_email})

        for r in (comm.recipients or []):
            email = r.get("email") if isinstance(r, dict) else r
            if email:
                agent_id = self.get_or_create(email, source=comm.source)
                if agent_id:
                    results.append({"agent_id": agent_id, "role": "to", "email": email})

        for c in (comm.cc or []):
            email = c.get("email") if isinstance(c, dict) else c
            if email:
                agent_id = self.get_or_create(email, source=comm.source)
                if agent_id:
                    results.append({"agent_id": agent_id, "role": "cc", "email": email})

        return results

    def extract_from_event(self, event) -> list[dict]:
        results = []
        org_id = self.get_or_create(event.organizer_email, event.organizer_name, event.source)
        if org_id:
            results.append({"agent_id": org_id, "role": "organizer", "email": event.organizer_email})

        for a in (event.attendees or []):
            email = a.get("email") if isinstance(a, dict) else a
            name = a.get("name") if isinstance(a, dict) else None
            if email:
                agent_id = self.get_or_create(email, name, event.source)
                if agent_id:
                    results.append({"agent_id": agent_id, "role": "attendee", "email": email})

        return results
