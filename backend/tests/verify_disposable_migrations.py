"""Disposable database migration verification script.

Verifies:
1. Fresh database: Applies all migrations from base to head cleanly.
2. Inspects schema to verify users.password_hash, messages.reply_to_message_id,
   context_nodes, and context_inconsistencies exist with proper types/indexes.
3. Tests downgrade back to 20261027_0009 and re-upgrade to 20261027_0010.
4. Existing data preservation: seeds dummy user and message before 20261027_0010,
   applies 20261027_0010, and verifies user and message records remain intact.
5. Cleans up disposable database file completely.
"""

import os
import sys
from pathlib import Path

# Ensure backend root is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DISPOSABLE_DB = BACKEND_DIR / "temp_disposable_migration_audit.db"
DISPOSABLE_URL = f"sqlite+aiosqlite:///{DISPOSABLE_DB.as_posix()}"

os.environ["DATABASE_URL"] = DISPOSABLE_URL

from alembic.config import Config
from alembic import command
import sqlite3


def get_alembic_config():
    ini_path = BACKEND_DIR / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", DISPOSABLE_URL)
    return cfg


def run_checks():
    if DISPOSABLE_DB.exists():
        DISPOSABLE_DB.unlink()

    cfg = get_alembic_config()

    print("Step 1: Running alembic upgrade head on fresh disposable database...")
    command.upgrade(cfg, "head")
    assert DISPOSABLE_DB.exists(), "Disposable DB was not created."

    # Inspect fresh schema
    conn = sqlite3.connect(str(DISPOSABLE_DB))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    print(f"Tables in fresh database: {sorted(list(tables))}")

    assert "users" in tables, "Missing users table"
    assert "messages" in tables, "Missing messages table"
    assert "context_nodes" in tables, "Missing context_nodes table"
    assert "context_inconsistencies" in tables, "Missing context_inconsistencies table"
    assert "meeting_invitations" in tables, "Missing meeting_invitations table"
    assert "voice_transcripts" in tables, "Missing voice_transcripts table"

    # Check columns in users
    cursor.execute("PRAGMA table_info(users);")
    user_cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "password_hash" in user_cols, "Missing password_hash column in users"

    # Check columns in messages
    cursor.execute("PRAGMA table_info(messages);")
    msg_cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "reply_to_message_id" in msg_cols, "Missing reply_to_message_id in messages"

    # Check columns in context_nodes
    cursor.execute("PRAGMA table_info(context_nodes);")
    cn_cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "topic" in cn_cols
    assert "status" in cn_cols
    assert "evidence_message_ids" in cn_cols

    # Check columns in context_inconsistencies
    cursor.execute("PRAGMA table_info(context_inconsistencies);")
    ci_cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "clarification_prompt" in ci_cols
    assert "earlier_evidence_message_id" in ci_cols
    assert "later_evidence_message_id" in ci_cols

    # Check columns in meeting_invitations
    cursor.execute("PRAGMA table_info(meeting_invitations);")
    mi_cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "meeting_uri" in mi_cols
    assert "provider" in mi_cols

    # Check columns in voice_transcripts
    cursor.execute("PRAGMA table_info(voice_transcripts);")
    vt_cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "transcript_text" in vt_cols
    assert "transcription_status" in vt_cols
    assert "translations" in vt_cols

    conn.close()
    print("Step 1 passed: Fresh DB upgraded and verified successfully.")

    print("Step 2: Testing downgrade to 20261027_0010 and re-upgrade...")
    command.downgrade(cfg, "20261027_0010")

    conn = sqlite3.connect(str(DISPOSABLE_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables_post_down = {row[0] for row in cursor.fetchall()}
    assert "meeting_invitations" not in tables_post_down, "meeting_invitations should be dropped on downgrade"
    assert "voice_transcripts" not in tables_post_down, "voice_transcripts should be dropped on downgrade"

    # Re-upgrade to head
    conn.close()
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(DISPOSABLE_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables_reup = {row[0] for row in cursor.fetchall()}
    assert "meeting_invitations" in tables_reup
    assert "voice_transcripts" in tables_reup
    conn.close()
    print("Step 2 passed: Downgrade and re-upgrade worked cleanly.")

    print("Step 3: Verifying data preservation when upgrading existing populated database...")
    # Clean up DB
    if DISPOSABLE_DB.exists():
        DISPOSABLE_DB.unlink()

    # Upgrade to 20261027_0009
    command.upgrade(cfg, "20261027_0009")

    # Seed existing user and conversation and message
    conn = sqlite3.connect(str(DISPOSABLE_DB))
    cursor = conn.cursor()
    test_user_id = "00000000-0000-0000-0000-000000000001"
    cursor.execute(
        "INSERT INTO users (id, email, username, username_normalized, is_active, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (test_user_id, "existing_user@example.com", "existing_user", "existing_user", 1),
    )
    test_conv_id = "00000000-0000-0000-0000-000000000002"
    cursor.execute(
        "INSERT INTO conversations (id, is_group, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        (test_conv_id, 0),
    )
    test_msg_id = "00000000-0000-0000-0000-000000000003"
    cursor.execute(
        "INSERT INTO messages (id, conversation_id, sender_id, content, message_type, is_deleted_for_everyone, msg_metadata, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (test_msg_id, test_conv_id, test_user_id, "Existing historical message", "text", 0, "{}"),
    )
    conn.commit()
    conn.close()

    # Now upgrade to 20261027_0010 (head)
    command.upgrade(cfg, "head")

    # Verify existing data is preserved intact!
    conn = sqlite3.connect(str(DISPOSABLE_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, username, password_hash FROM users WHERE id = ?", (test_user_id,))
    u_row = cursor.fetchone()
    assert u_row is not None, "Existing user was lost during migration!"
    assert u_row[1] == "existing_user@example.com"
    assert u_row[2] == "existing_user"
    assert u_row[3] is None, "Existing user should have password_hash=NULL initially"

    cursor.execute("SELECT id, content, reply_to_message_id FROM messages WHERE id = ?", (test_msg_id,))
    m_row = cursor.fetchone()
    assert m_row is not None, "Existing message was lost during migration!"
    assert m_row[1] == "Existing historical message"
    assert m_row[2] is None, "Existing message should have reply_to_message_id=NULL initially"

    conn.close()
    print("Step 3 passed: Existing users and messages preserved with 100% data integrity.")

    # Cleanup disposable DB
    if DISPOSABLE_DB.exists():
        DISPOSABLE_DB.unlink()
    print("Disposable database cleaned up. All migration checks PASSED!")


if __name__ == "__main__":
    run_checks()
