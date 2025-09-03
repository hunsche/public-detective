import os
from unittest.mock import patch

from providers.config import Config


def test_derived_pubsub_names_are_set_by_default():
    """
    Tests that the DLQ topic and subscription names are derived correctly
    when they are not provided explicitly.
    """
    with patch.dict(os.environ, {}, clear=True):
        # Unset the environment variables to ensure they are derived
        if "GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS" in os.environ:
            del os.environ["GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS"]
        if "GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS" in os.environ:
            del os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"]

        config = Config(GCP_PUBSUB_TOPIC_PROCUREMENTS="my-topic")

        assert config.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS == "my-topic-dlq"
        assert config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS == "my-topic-subscription"


def test_explicit_dlq_topic_name_is_used():
    """
    Tests that an explicitly provided DLQ topic name is used instead of
    being derived. This covers the 'else' branch for the DLQ check.
    """
    dlq_topic = "my-explicit-dlq"
    with patch.dict(os.environ, {"GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS": dlq_topic}, clear=True):
        config = Config(GCP_PUBSUB_TOPIC_PROCUREMENTS="my-topic")

        assert config.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS == dlq_topic


def test_explicit_subscription_name_is_used():
    """
    Tests that an explicitly provided subscription name is used instead of
    being derived. This covers the missing branch.
    """
    subscription_name = "my-explicit-subscription"
    with patch.dict(os.environ, {"GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS": subscription_name}, clear=True):
        config = Config(GCP_PUBSUB_TOPIC_PROCUREMENTS="my-topic")

        assert config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS == subscription_name


def test_config_provider_returns_fresh_config():
    """
    Tests that the ConfigProvider returns a fresh, re-evaluated config instance.
    """
    with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}, clear=True):
        from providers.config import ConfigProvider

        config1 = ConfigProvider.get_config()
        assert config1.LOG_LEVEL == "INFO"

        os.environ["LOG_LEVEL"] = "DEBUG"

        config2 = ConfigProvider.get_config()
        assert config2.LOG_LEVEL == "DEBUG"
        # Ensure it's a new instance
        assert config1 is not config2
