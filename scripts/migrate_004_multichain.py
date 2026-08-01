"""
Migration 004: Multichain schema support (Wallets, Payment network, EscrowDetail chain_data).

Run once:
    python scripts/migrate_004_multichain.py

Idempotent: safe to run multiple times.
Makes an automatic backup in data/backups/ before modifying existing data.
"""

import json
import os
import sqlite3
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import DB_PATH, backup_database


def migrate(db_path=DB_PATH):
    if not os.path.exists(db_path):
        print(f"Database file does not exist at {db_path}, skipping migration.")
        return

    print("Creating backup before migration...")
    if db_path == DB_PATH:
        backup_database()
    else:
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        conn_src = sqlite3.connect(db_path)
        conn_dst = sqlite3.connect(os.path.join(backup_dir, "test_backup.db"))
        conn_src.backup(conn_dst)
        conn_dst.close()
        conn_src.close()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. CREATE TABLE wallets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_type VARCHAR(20) NOT NULL,
                owner_id INTEGER NOT NULL,
                network VARCHAR(20) NOT NULL,
                address VARCHAR(100) NOT NULL,
                is_default BOOLEAN DEFAULT 0,
                created_at DATETIME,
                CONSTRAINT uq_wallet_net_addr UNIQUE (network, address)
            );
        """)
        print("  + Table created/verified: wallets")

        # 2. Copy producers.xrpl_address to wallets
        cursor.execute("PRAGMA table_info(producers)")
        prod_cols = [row[1] for row in cursor.fetchall()]
        if "xrpl_address" in prod_cols:
            cursor.execute("""
                INSERT OR IGNORE INTO wallets (owner_type, owner_id, network, address, is_default, created_at)
                SELECT 'producer', id, 'XRPL', xrpl_address, 1, strftime('%Y-%m-%d %H:%M:%S', 'now')
                FROM producers
                WHERE xrpl_address IS NOT NULL AND xrpl_address != '';
            """)
            print("  + Copied producers.xrpl_address to wallets table")

        # Copy users.xrpl_address to wallets
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [row[1] for row in cursor.fetchall()]
        if "xrpl_address" in user_cols:
            cursor.execute("""
                INSERT OR IGNORE INTO wallets (owner_type, owner_id, network, address, is_default, created_at)
                SELECT 'user', id, 'XRPL', xrpl_address, 1, strftime('%Y-%m-%d %H:%M:%S', 'now')
                FROM users
                WHERE xrpl_address IS NOT NULL AND xrpl_address != '';
            """)
            print("  + Copied users.xrpl_address to wallets table")

        # 3. Update payments table: xrpl_tx_hash -> tx_hash, + network
        cursor.execute("PRAGMA table_info(payments)")
        pay_cols = [row[1] for row in cursor.fetchall()]

        if "xrpl_tx_hash" in pay_cols and "tx_hash" not in pay_cols:
            cursor.execute("ALTER TABLE payments RENAME COLUMN xrpl_tx_hash TO tx_hash;")
            print("  + Renamed payments.xrpl_tx_hash -> tx_hash")

        if "network" not in pay_cols:
            cursor.execute("ALTER TABLE payments ADD COLUMN network VARCHAR(20) NOT NULL DEFAULT 'XRPL';")
            cursor.execute("UPDATE payments SET network = 'XRPL' WHERE network IS NULL OR network = '';")
            print("  + Added payments.network column (default 'XRPL')")

        # 4. Update escrow_details table: + network, + chain_data, remove legacy columns
        cursor.execute("PRAGMA table_info(escrow_details)")
        esc_cols = [row[1] for row in cursor.fetchall()]

        if esc_cols:  # table exists
            has_offer_seq = "offer_sequence" in esc_cols
            has_chain_data = "chain_data" in esc_cols

            if has_offer_seq:
                if not has_chain_data:
                    cursor.execute("ALTER TABLE escrow_details ADD COLUMN network VARCHAR(20) NOT NULL DEFAULT 'XRPL';")
                    cursor.execute("ALTER TABLE escrow_details ADD COLUMN chain_data TEXT;")
                    print("  + Added escrow_details.network and chain_data columns")

                cursor.execute("SELECT id, offer_sequence, condition_hex, fulfillment_hex FROM escrow_details;")
                rows = cursor.fetchall()
                for row in rows:
                    row_id, offer_seq, cond_hex, ful_hex = row
                    cd = {
                        "offer_sequence": offer_seq,
                        "condition_hex": cond_hex,
                        "fulfillment_hex": ful_hex
                    }
                    cursor.execute(
                        "UPDATE escrow_details SET chain_data = ?, network = 'XRPL' WHERE id = ?;",
                        (json.dumps(cd), row_id)
                    )
                print(f"  + Converted {len(rows)} escrow_details rows to JSON chain_data")

                if sqlite3.sqlite_version_info >= (3, 35, 0):
                    try:
                        cursor.execute("ALTER TABLE escrow_details DROP COLUMN offer_sequence;")
                        cursor.execute("ALTER TABLE escrow_details DROP COLUMN condition_hex;")
                        cursor.execute("ALTER TABLE escrow_details DROP COLUMN fulfillment_hex;")
                        print("  + Dropped legacy columns from escrow_details via ALTER TABLE DROP COLUMN")
                    except Exception as exc:
                        print(f"  ~ DROP COLUMN failed ({exc}), falling back to table rebuild...")
                        _rebuild_escrow_details_table(cursor)
                else:
                    _rebuild_escrow_details_table(cursor)

        conn.commit()
        print("Migration 004 completed successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error during migration 004: {e}")
        raise
    finally:
        conn.close()


def _rebuild_escrow_details_table(cursor):
    """Rebuild escrow_details table to remove legacy columns for SQLite < 3.35 or fallback."""
    cursor.execute("""
        CREATE TABLE escrow_details_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id INTEGER NOT NULL UNIQUE REFERENCES payments(id),
            network VARCHAR(20) NOT NULL DEFAULT 'XRPL',
            chain_data TEXT NOT NULL,
            cancel_after DATETIME NOT NULL,
            create_tx_hash VARCHAR(100) NOT NULL,
            finish_tx_hash VARCHAR(100),
            cancel_tx_hash VARCHAR(100),
            quality_notes TEXT,
            resolved_at DATETIME
        );
    """)

    cursor.execute("PRAGMA table_info(escrow_details)")
    old_cols = [row[1] for row in cursor.fetchall()]

    if "chain_data" in old_cols:
        cursor.execute("""
            INSERT INTO escrow_details_new (
                id, payment_id, network, chain_data, cancel_after,
                create_tx_hash, finish_tx_hash, cancel_tx_hash, quality_notes, resolved_at
            )
            SELECT
                id, payment_id, COALESCE(network, 'XRPL'), chain_data, cancel_after,
                create_tx_hash, finish_tx_hash, cancel_tx_hash, quality_notes, resolved_at
            FROM escrow_details;
        """)
    else:
        cursor.execute("SELECT id, payment_id, offer_sequence, condition_hex, fulfillment_hex, cancel_after, create_tx_hash, finish_tx_hash, cancel_tx_hash, quality_notes, resolved_at FROM escrow_details;")
        rows = cursor.fetchall()
        for r in rows:
            r_id, p_id, off_seq, cond_h, ful_h, can_aft, cr_hash, fin_hash, can_hash, q_notes, res_at = r
            cd = json.dumps({"offer_sequence": off_seq, "condition_hex": cond_h, "fulfillment_hex": ful_h})
            cursor.execute("""
                INSERT INTO escrow_details_new (
                    id, payment_id, network, chain_data, cancel_after,
                    create_tx_hash, finish_tx_hash, cancel_tx_hash, quality_notes, resolved_at
                ) VALUES (?, ?, 'XRPL', ?, ?, ?, ?, ?, ?, ?);
            """, (r_id, p_id, cd, can_aft, cr_hash, fin_hash, can_hash, q_notes, res_at))

    cursor.execute("DROP TABLE escrow_details;")
    cursor.execute("ALTER TABLE escrow_details_new RENAME TO escrow_details;")
    print("  + Rebuilt escrow_details table without legacy XRPL columns")


if __name__ == "__main__":
    print("Running migration 004: multichain schema...")
    migrate()
    print("Done.")
