from datetime import timedelta
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import utc_now
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.recommendation import RecommendationItem
from app.models.user import User
from app.services.recommendation_service import RECENT_MESSAGE_WINDOW, RecommendationService


@pytest.mark.asyncio
async def test_listing_hides_recommendations_from_old_topics(test_user: User, db_session: AsyncSession):
    conv = Conversation(is_group=True, title="Topics", created_by_id=test_user.id)
    db_session.add(conv)
    await db_session.commit()
    db_session.add(ConversationMember(conversation_id=conv.id, user_id=test_user.id, role="admin"))

    start = utc_now() - timedelta(hours=1)
    messages = [
        Message(conversation_id=conv.id, sender_id=test_user.id, content=f"m{i}", created_at=start + timedelta(seconds=i))
        for i in range(RECENT_MESSAGE_WINDOW + 5)
    ]
    db_session.add_all(messages)
    await db_session.commit()

    old_topic = RecommendationItem(
        conversation_id=conv.id, triggered_by_message_id=messages[0].id,
        source="spotify", title="Old song", url="https://open.spotify.com/track/old",
    )
    current_topic = RecommendationItem(
        conversation_id=conv.id, triggered_by_message_id=messages[-1].id,
        source="youtube", title="Today's match highlights", url="https://www.youtube.com/watch?v=new",
    )
    unanchored = RecommendationItem(
        conversation_id=conv.id, triggered_by_message_id=None,
        source="tavily", title="Unanchored", url="https://example.com/x",
    )
    db_session.add_all([old_topic, current_topic, unanchored])
    await db_session.commit()

    items = await RecommendationService(db_session).get_conversation_recommendations(conv.id, test_user.id)
    assert [i.title for i in items] == ["Today's match highlights"]
