"""drop_procurement_overall_status_view

Revision ID: f66aba35044e
Revises: 306b4a0d0604
Create Date: 2025-08-31 12:07:33.431613

"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

# revision identifiers, used by Alembic.
revision: str = "f66aba35044e"
down_revision: str | None = "306b4a0d0604"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    view_name = get_table_name("procurement_overall_status")
    op.execute(f"DROP VIEW {view_name};")


def downgrade() -> None:
    procurement_table = get_table_name("procurement")
    analysis_table = get_table_name("procurement_analysis")
    view_name = get_table_name("procurement_overall_status")

    sql = f"""
        CREATE OR REPLACE VIEW {view_name} AS
        WITH latest AS (
          SELECT pncp_control_number, MAX(version_number) AS latest_version
          FROM {procurement_table}
          GROUP BY pncp_control_number
        ),
        per_version AS (
          SELECT
            pa.procurement_control_number,
            pa.version_number,
            BOOL_OR(pa.status::text = 'ANALYSIS_SUCCESSFUL') AS v_has_success,
            BOOL_OR(pa.status::text = 'ANALYSIS_IN_PROGRESS') AS v_has_in_progress,
            BOOL_OR(pa.status::text = 'ANALYSIS_FAILED')     AS v_has_failed,
            BOOL_OR(pa.status::text = 'PENDING_ANALYSIS')    AS v_has_pending
          FROM {analysis_table} pa
          GROUP BY pa.procurement_control_number, pa.version_number
        ),
        any_previous_success AS (
          SELECT
            l.pncp_control_number,
            BOOL_OR(pv.v_has_success) AS has_success_in_previous
          FROM latest l
          JOIN per_version pv
            ON pv.procurement_control_number = l.pncp_control_number
           AND pv.version_number  < l.latest_version
          GROUP BY l.pncp_control_number
        ),
        latest_rollup AS (
          SELECT
            l.pncp_control_number,
            l.latest_version,
            COALESCE(pv.v_has_success, false)     AS lv_has_success,
            COALESCE(pv.v_has_in_progress, false) AS lv_has_in_progress,
            COALESCE(pv.v_has_failed, false)      AS lv_has_failed,
            COALESCE(pv.v_has_pending, false)     AS lv_has_pending
          FROM latest l
          LEFT JOIN per_version pv
            ON pv.procurement_control_number = l.pncp_control_number
           AND pv.version_number  = l.latest_version
        )
        SELECT
          lr.pncp_control_number AS procurement_id,
          lr.latest_version,
          CASE
            WHEN lr.lv_has_in_progress THEN 'ANALYSIS_IN_PROGRESS'
            WHEN lr.lv_has_success     THEN 'ANALYZED_CURRENT'
            WHEN lr.lv_has_failed      THEN 'FAILED_CURRENT'
            WHEN aps.has_success_in_previous IS TRUE THEN 'ANALYZED_OUTDATED'
            WHEN lr.lv_has_pending OR lr.latest_version IS NOT NULL THEN 'PENDING'
            ELSE 'NOT_ANALYZED'
          END AS overall_status
        FROM latest_rollup lr
        LEFT JOIN any_previous_success aps
          ON aps.pncp_control_number = lr.pncp_control_number;
        """
    op.execute(sql)
