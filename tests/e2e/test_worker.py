import json
import os
import uuid

import pytest
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1, storage
from models.procurements import Procurement
from providers.pubsub import PubSubProvider
from repositories.procurements import ProcurementsRepository
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import run_command


@pytest.fixture(scope="function")
def worker_e2e_test_setup(db_session: Engine):
    """Set up the environment for a single worker E2E test."""
    # Ensure E2E tests for GCS and AI run against real GCP services,
    # while Pub/Sub can still use an emulator.
    os.environ.pop("GCP_GCS_HOST", None)
    os.environ.pop("GCP_AI_HOST", None)

    print("\n--- Setting up Worker E2E test environment ---")
    project_id = "total-entity-463718-k1"
    os.environ["GCP_PROJECT"] = project_id


    run_id = uuid.uuid4().hex
    topic_name = f"procurements-topic-worker-test-{run_id}"
    subscription_name = f"procurements-subscription-worker-test-{run_id}"

    # Use a pre-existing bucket for all GCS operations in the test
    bucket_name = "vertex-ai-test-files"
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = bucket_name
    os.environ["GCP_VERTEX_AI_BUCKET"] = bucket_name

    publisher = pubsub_v1.PublisherClient(credentials=AnonymousCredentials())
    subscriber = pubsub_v1.SubscriberClient(credentials=AnonymousCredentials())
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    gcs_credentials_path = os.path.expanduser("~/.gcp/credentials.json")
    if not os.path.exists(gcs_credentials_path):
        pytest.fail(f"Service account credentials not found at {gcs_credentials_path}")
    with open(gcs_credentials_path, "r") as f:
        gcs_credentials_json = f.read()

    os.environ["GCP_SERVICE_ACCOUNT_CREDENTIALS"] = gcs_credentials_json

    # This client is only for test setup/teardown, not for the application itself.
    # It can use the standard ADC which will find the file via GOOGLE_APPLICATION_CREDENTIALS
    # if it's set globally, or it can be initialized differently if needed.
    # For the purpose of this test, we'll create a temporary client for bucket operations.
    temp_gcs_client = storage.Client.from_service_account_json(gcs_credentials_path, project=project_id)
    bucket = temp_gcs_client.bucket(bucket_name)
    # In a real environment, the bucket should exist. We are not creating it anymore.
    # try:
    #     if not bucket.exists():
    #         print(f"Creating GCS bucket: {bucket_name}")
    #         gcs_client.create_bucket(bucket)

    try:
        print(f"Creating Pub/Sub topic: {topic_path}")
        publisher.create_topic(request={"name": topic_path})

        print(f"Creating Pub/Sub subscription: {subscription_path}")
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})

        yield publisher, topic_path

    finally:
        print("\n--- Tearing down Worker E2E test environment ---")
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
        except exceptions.NotFound:
            pass
        try:
            publisher.delete_topic(request={"topic": topic_path})
        except exceptions.NotFound:
            pass
        try:
            for blob in bucket.list_blobs():
                blob.delete()
            # bucket.delete() # Do not delete a pre-existing bucket
        except exceptions.NotFound:
            pass


@pytest.mark.timeout(240)
def test_worker_flow(worker_e2e_test_setup, db_session: Engine):
    """Tests the worker processing a single message."""
    publisher, topic_path = worker_e2e_test_setup
    analysis_id = uuid.uuid4()
    procurement_control_number = "43776491000170-1-000251/2025"
    version_number = 1

    pubsub_provider = PubSubProvider()
    procurement_repo = ProcurementsRepository(engine=db_session, pubsub_provider=pubsub_provider)

    raw_data_json = json.dumps({
        "anoCompra": 2025,
        "dataAtualizacao": "2025-08-23T14:30:00",
        "dataPublicacaoPncp": "2025-08-23T14:30:00",
        "sequencialCompra": 251,
        "numeroControlePNCP": procurement_control_number,
        "objetoCompra": "Aquisição de material de escritório",
        "srp": False,
        "orgaoEntidade": {
            "cnpj": "43776491000170",
            "razaoSocial": "MUNICIPIO DE ARACATUBA",
            "poderId": "E",
            "esferaId": "M"
        },
        "processo": "123/2025",
        "amparoLegal": {"codigo": 1, "nome": "Lei 14.133/2021", "descricao": "Art. 75, II"},
        "numeroCompra": "001/2025",
        "unidadeOrgao": {
            "codigoUnidade": "12345",
            "nomeUnidade": "Secretaria de Administração",
            "ufNome": "São Paulo",
            "ufSigla": "SP",
            "municipioNome": "ARACATUBA",
            "codigoIbge": "3502804"
        },
        "modalidadeId": 1,
        "dataAtualizacaoGlobal": "2025-08-23T14:30:00",
        "modoDisputaId": 1,
        "situacaoCompraId": 1,
        "usuarioNome": "Teste"
    })

    procurement_model = Procurement.model_validate(json.loads(raw_data_json))
    procurement_repo.save_procurement_version(
        procurement=procurement_model,
        raw_data=raw_data_json,
        version_number=version_number,
        content_hash=f"dummy_hash_{analysis_id}",
    )

    with db_session.connect() as connection:
        connection.execute(
            text(
                """INSERT INTO procurement_analyses (analysis_id, procurement_control_number, version_number, status, created_at, updated_at)
                   VALUES (:analysis_id, :procurement_control_number, :version_number, 'PENDING_ANALYSIS', NOW(), NOW())"""
            ),
            {
                "analysis_id": analysis_id,
                "procurement_control_number": procurement_control_number,
                "version_number": version_number,
            },
        )
        connection.commit()

    message_data = {"analysis_id": str(analysis_id)}
    message_json = json.dumps(message_data)
    publisher.publish(topic_path, message_json.encode())
    print(f"Published message for analysis_id: {analysis_id}")

    # Pass environment variables directly to the worker command to ensure it uses the unique
    # topic and subscription for this test run.
    topic_name = topic_path.split("/")[-1]
    run_id = topic_name.split("-")[-1]
    subscription_name = f"procurements-subscription-worker-test-{run_id}"
    env_vars = (
        f"GCP_PUBSUB_TOPIC_PROCUREMENTS='{topic_name}' "
        f"GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS='{subscription_name}' "
    )
    worker_command = f"{env_vars} poetry run python -m source.worker --max-messages 1 --timeout 5"
    run_command(worker_command)

    with db_session.connect() as connection:
        result = connection.execute(
            text("SELECT status FROM procurement_analyses WHERE analysis_id = :analysis_id"),
            {"analysis_id": analysis_id},
        ).scalar_one_or_none()

        print(f"Final status for analysis {analysis_id}: {result}")
        assert result == "ANALYSIS_SUCCESSFUL", f"Expected ANALYSIS_SUCCESSFUL, but got {result}"
