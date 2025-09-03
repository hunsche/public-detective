import os
import unittest

from source.providers.config import Config


class TestConfigProvider(unittest.TestCase):
    def test_derived_pubsub_names_are_not_overridden(self):
        dlq_topic = "my-custom-dlq"
        subscription = "my-custom-subscription"

        os.environ["GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS"] = dlq_topic
        os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription

        config = Config()

        self.assertEqual(config.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS, dlq_topic)
        self.assertEqual(config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS, subscription)

        # Clean up environment variables
        del os.environ["GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS"]
        del os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"]
