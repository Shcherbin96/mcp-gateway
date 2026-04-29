"""initial schema with append-only audit_log

Revision ID: 0001
Revises:
Create Date: 2026-04-29

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "oauth_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(128), nullable=False, unique=True),
        sa.Column("client_secret_hash", sa.String(255), nullable=False),
        sa.Column(
            "redirect_uris",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tool_name", sa.String(128), primary_key=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("owner_email", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(128), nullable=False),
        sa.Column("params_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("decision_reason", sa.String(1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_approval_requests_pending",
        "approval_requests",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool", sa.String(128), nullable=True),
        sa.Column("params_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result_status", sa.String(64), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_log_tenant_time", "audit_log", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_audit_log_agent_time", "audit_log", ["agent_id", "created_at"]
    )

    # Append-only protection
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_no_modify_fn() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_modify
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify_fn();
        """
    )

    # Application user with restricted permissions on audit_log
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'mcp_app') THEN
                CREATE USER mcp_app WITH PASSWORD 'mcp_app';
            END IF;
        END $$;
        """
    )
    op.execute("GRANT INSERT, SELECT ON audit_log TO mcp_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM mcp_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO mcp_app")
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE
        ON tenants, oauth_clients, agents, roles, role_permissions, approval_requests
        TO mcp_app
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_modify ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_modify_fn()")
    op.drop_index("ix_audit_log_agent_time", table_name="audit_log")
    op.drop_index("ix_audit_log_tenant_time", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_approval_requests_pending", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_table("agents")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("oauth_clients")
    op.drop_table("tenants")
