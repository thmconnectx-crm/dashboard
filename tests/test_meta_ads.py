from app.connectors.meta_ads import _sum_messages


def test_sum_messages_counts_only_started_conversations():
    actions = [
        {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "54"},
        {"action_type": "onsite_conversion.messaging_first_reply", "value": "56"},
        {"action_type": "onsite_conversion.messaging_user_depth_2_message_send", "value": "56"},
        {"action_type": "link_click", "value": "412"},
    ]

    assert _sum_messages(actions) == 54


def test_sum_messages_supports_legacy_started_conversation_key():
    actions = [
        {"action_type": "messaging_conversation_started_7d", "value": "12"},
        {"action_type": "onsite_conversion.messaging_user_subscribed", "value": "20"},
    ]

    assert _sum_messages(actions) == 12
