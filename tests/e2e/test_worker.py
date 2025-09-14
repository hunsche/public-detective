import json
import os
import uuid

import pytest
from public_detective.models.procurements import Procurement
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.procurements import ProcurementsRepository
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import run_command


@pytest.mark.timeout(240)
def test_worker_flow(e2e_environment: tuple, db_session: Engine) -> None:
    """Tests the worker processing a single message."""
    publisher, topic_path = e2e_environment
    analysis_id = uuid.uuid4()
    procurement_control_number = "43776491000170-1-000251/2025"
    version_number = 1

    pubsub_provider = PubSubProvider()
    procurement_repo = ProcurementsRepository(engine=db_session, pubsub_provider=pubsub_provider)

    raw_data_json = json.dumps(
        {
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
                "esferaId": "M",
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
                "codigoIbge": "3502804",
            },
            "modalidadeId": 1,
            "dataAtualizacaoGlobal": "2025-08-23T14:30:00",
            "modoDisputaId": 1,
            "situacaoCompraId": 1,
            "usuarioNome": "Teste",
        }
    )

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
                """INSERT INTO procurement_analyses (
                    analysis_id,
                    procurement_control_number,
                    version_number,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    :analysis_id,
                    :procurement_control_number,
                    :version_number,
                    'PENDING_ANALYSIS',
                    NOW(),
                    NOW()
                )"""
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
    topic_name = os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"]
    subscription_name = os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"]
    env_vars = (
        f"GCP_PUBSUB_TOPIC_PROCUREMENTS='{topic_name}' "
        f"GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS='{subscription_name}'"
    )
    worker_command = f"{env_vars} poetry run python -m public_detective.worker --max-messages 1 --timeout 5"
    run_command(worker_command)

    with db_session.connect() as connection:
        result = connection.execute(
            text("SELECT status FROM procurement_analyses WHERE analysis_id = :analysis_id"),
            {"analysis_id": analysis_id},
        ).scalar_one_or_none()

        print(f"Final status for analysis {analysis_id}: {result}")
        assert result == "ANALYSIS_SUCCESSFUL", f"Expected ANALYSIS_SUCCESSFUL, but got {result}"
