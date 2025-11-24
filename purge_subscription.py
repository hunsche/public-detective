from google.cloud import pubsub_v1
from datetime import datetime
import os
from public_detective.providers.config import ConfigProvider

config = ConfigProvider.get_config()

# Ensure emulator usage
if config.GCP_PUBSUB_HOST:
    os.environ["PUBSUB_EMULATOR_HOST"] = config.GCP_PUBSUB_HOST

project_id = config.GCP_PROJECT
subscription_id = config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)

print(f"Purgando assinatura: {subscription_path}")

# Seek to current time to acknowledge all pending messages
timestamp = datetime.now()
try:
    subscriber.seek(
        request={
            "subscription": subscription_path,
            "time": timestamp,
        }
    )
    print(f"Assinatura {subscription_id} purgada com sucesso.")
except Exception as e:
    print(f"Erro ao purgar assinatura: {e}")
