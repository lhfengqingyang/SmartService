from datetime import timedelta

import pytest

from app.ai.conversations import ConversationNotFoundError, ConversationStore, PendingRefund


def test_conversation_store_binds_state_to_user() -> None:
    store = ConversationStore(ttl=timedelta(minutes=5))
    conversation = store.get_or_create("user-1")
    pending = PendingRefund("action-1", "order-1", "damaged")
    store.set_pending_refund(conversation.conversation_id, pending)

    loaded = store.get_or_create("user-1", conversation.conversation_id)
    assert loaded.pending_refund == pending

    with pytest.raises(ConversationNotFoundError):
        store.get_or_create("user-2", conversation.conversation_id)
