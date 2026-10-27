from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import uuid4


@dataclass(frozen=True)
class PendingRefund:
    action_id: str
    order_id: str
    reason: str


@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    pending_refund: PendingRefund | None
    updated_at: datetime
    tenant_id: str | None = None
    last_order_id: str | None = None


class ConversationNotFoundError(LookupError):
    pass


class ConversationStore:
    """Thread-safe, process-local conversation state for the MVP."""

    def __init__(self, *, ttl: timedelta = timedelta(minutes=30), max_entries: int = 1000) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._items: dict[str, Conversation] = {}
        self._lock = Lock()

    def get_or_create(self, user_id: str, conversation_id: str | None = None) -> Conversation:
        now = datetime.now(UTC)
        with self._lock:
            self._remove_expired(now)
            if conversation_id is not None:
                conversation = self._items.get(conversation_id)
                if conversation is None or conversation.user_id != user_id:
                    raise ConversationNotFoundError("conversation was not found")
                conversation.updated_at = now
                return conversation

            if len(self._items) >= self.max_entries:
                oldest_id = min(self._items, key=lambda item_id: self._items[item_id].updated_at)
                del self._items[oldest_id]
            conversation = Conversation(str(uuid4()), user_id, None, now)
            self._items[conversation.conversation_id] = conversation
            return conversation

    def set_pending_refund(self, conversation_id: str, pending: PendingRefund | None) -> None:
        with self._lock:
            conversation = self._items[conversation_id]
            conversation.pending_refund = pending
            conversation.updated_at = datetime.now(UTC)

    def set_task_context(self, conversation_id: str, tenant_id: str, order_id: str | None) -> None:
        with self._lock:
            conversation = self._items[conversation_id]
            if conversation.tenant_id is not None and conversation.tenant_id != tenant_id:
                raise ValueError("conversation tenant does not match request")
            conversation.tenant_id = tenant_id
            if order_id:
                conversation.last_order_id = order_id
            conversation.updated_at = datetime.now(UTC)

    def _remove_expired(self, now: datetime) -> None:
        expired = [item_id for item_id, conversation in self._items.items() if now - conversation.updated_at > self.ttl]
        for item_id in expired:
            del self._items[item_id]


conversation_store = ConversationStore()
