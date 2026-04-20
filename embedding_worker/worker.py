#!/usr/bin/env python3
"""
Embedding Worker for Context Manager
Generates vector embeddings using ONNX Runtime (no PyTorch).

Modes:
  --embed "text"     → Output embedding as JSON to stdout
  --batch            → Embed all entries without embeddings
  --batch --limit N  → Embed N entries at a time
  --stats            → Show embedding statistics

Runs in its own venv, separate from the MCP server.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


# Configuration
SCRIPT_DIR = Path(__file__).parent
MODEL_DIR = SCRIPT_DIR / "model"
MAX_SEQ_LENGTH = 256  # all-MiniLM-L6-v2 max tokens
EMBEDDING_DIM = 384
BATCH_SIZE = 32  # entries per DB batch


class EmbeddingModel:
    """Lightweight ONNX-based embedding model."""

    def __init__(self, model_dir: Path = MODEL_DIR):
        model_path = model_dir / "model.onnx"
        tokenizer_path = model_dir / "tokenizer.json"

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}\n"
                f"Run: bash {SCRIPT_DIR}/setup.sh"
            )

        # Load tokenizer
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_length=MAX_SEQ_LENGTH)
        self.tokenizer.enable_padding(length=MAX_SEQ_LENGTH)

        # Load ONNX model
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4

        self.session = ort.InferenceSession(
            str(model_path),
            sess_options,
            providers=["CoreMLExecutionProvider", "CPUExecutionProvider"]
        )

    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns 384-dim vector."""
        encoded = self.tokenizer.encode(text)

        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            }
        )

        # Mean pooling over token embeddings (masked)
        token_embeddings = outputs[0]  # (1, seq_len, 384)
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask

        # Normalize to unit length
        norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        normalized = mean_pooled / np.clip(norm, a_min=1e-9, a_max=None)

        return normalized[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently."""
        if not texts:
            return []

        encodings = self.tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            }
        )

        token_embeddings = outputs[0]
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask

        norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        normalized = mean_pooled / np.clip(norms, a_min=1e-9, a_max=None)

        return normalized.tolist()


def get_db_connection():
    """Connect to PostgreSQL using shared Config (reads ~/.context/config.yaml + env vars)."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from src.core.config import Config

    config = Config()
    return psycopg2.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
        cursor_factory=RealDictCursor,
    )


def cmd_embed(args):
    """Embed a single text and output as JSON."""
    model = EmbeddingModel()
    vector = model.embed(args.text)
    print(json.dumps(vector))


def _record_run(conn, success: bool, processed: int, duration_ms: int, error: str = None):
    """Insert a row into embedding_worker_runs and trim entries older than 30 days.

    Safe to call even if the table doesn't exist yet (old installs without
    migration 006) - logs once and moves on.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO embedding_worker_runs
                (success, processed_count, duration_ms, error_message)
            VALUES (%s, %s, %s, %s)
        """, (success, processed, duration_ms, error))
        cursor.execute("""
            DELETE FROM embedding_worker_runs
            WHERE ran_at < EXTRACT(EPOCH FROM NOW() - INTERVAL '30 days')::BIGINT
        """)
        conn.commit()
    except Exception as e:
        # Non-fatal: worker run succeeded even if we can't log it
        print(f"Warning: could not record worker run: {e}", file=sys.stderr)
        try:
            conn.rollback()
        except Exception:
            pass


def cmd_batch(args):
    """Batch-embed all entries without embeddings."""
    start_time = time.time()
    processed = 0
    error_msg = None

    try:
        model = EmbeddingModel()
        conn = get_db_connection()
        cursor = conn.cursor()

        # Count work
        cursor.execute("SELECT count(*) as cnt FROM actions WHERE embedding IS NULL")
        total = cursor.fetchone()["cnt"]

        if total == 0:
            print("All entries already have embeddings.")
            _record_run(conn, True, 0, int((time.time() - start_time) * 1000))
            return
    except Exception as e:
        # Failure before we even have a connection - log via fresh connection
        error_msg = f"{type(e).__name__}: {e}"
        duration = int((time.time() - start_time) * 1000)
        try:
            conn2 = get_db_connection()
            _record_run(conn2, False, 0, duration, error_msg)
            conn2.close()
        except Exception:
            pass
        raise

    print(f"Entries without embeddings: {total}")
    limit = args.limit or total

    try:
        while processed < limit:
            batch_limit = min(BATCH_SIZE, limit - processed)
            cursor.execute("""
                SELECT a.id, a.summary, ac.content
                FROM actions a
                LEFT JOIN action_content ac ON a.id = ac.action_id
                WHERE a.embedding IS NULL
                ORDER BY a.id
                LIMIT %s
            """, (batch_limit,))

            rows = cursor.fetchall()
            if not rows:
                break

            # Prepare texts: use content if available, fallback to summary
            texts = []
            ids = []
            for row in rows:
                text = row.get("content") or row.get("summary") or ""
                # Truncate very long texts (tokenizer handles the rest)
                text = text[:2000]
                texts.append(text)
                ids.append(row["id"])

            # Generate embeddings
            vectors = model.embed_batch(texts)

            # Write to DB
            for entry_id, vector in zip(ids, vectors):
                vector_str = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
                cursor.execute(
                    "UPDATE actions SET embedding = %s::vector WHERE id = %s",
                    (vector_str, entry_id)
                )

            conn.commit()
            processed += len(rows)

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (limit - processed) / rate if rate > 0 else 0
            print(f"  {processed}/{limit} ({rate:.0f}/s, ETA {eta:.0f}s)")

        elapsed = time.time() - start_time
        print(f"\nDone: {processed} entries in {elapsed:.1f}s ({processed/elapsed:.0f}/s)")
        _record_run(conn, True, processed, int(elapsed * 1000))
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"{type(e).__name__}: {e}"
        _record_run(conn, False, processed, int(elapsed * 1000), error_msg)
        raise


def cmd_stats(args):
    """Show embedding statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # embedding column may not exist yet on fresh installs (added by migration)
    cursor.execute("SELECT count(*) as total FROM actions")
    total = cursor.fetchone()['total']

    cursor.execute("""
        SELECT count(*) as has_col
        FROM information_schema.columns
        WHERE table_name = 'actions' AND column_name = 'embedding'
    """)
    has_col = cursor.fetchone()['has_col'] > 0

    if has_col:
        cursor.execute("SELECT count(embedding) as embedded FROM actions")
        embedded = cursor.fetchone()['embedded']
    else:
        embedded = 0

    print(f"Total entries:    {total}")
    print(f"With embeddings:  {embedded}")
    print(f"Missing:          {total - embedded}")

    conn.close()


def cmd_setup(args):
    """Download ONNX model and install cron/launchd timer."""
    import platform
    import subprocess
    import shutil

    project_dir = SCRIPT_DIR.parent
    model_dir = SCRIPT_DIR / "model"

    # Step 1: Download model
    model_path = model_dir / "model.onnx"
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"✅ Model already downloaded ({size_mb:.0f}MB)")
    else:
        print("📦 Downloading ONNX model (all-MiniLM-L6-v2)...")
        try:
            from huggingface_hub import hf_hub_download
            import shutil as sh

            model_dir.mkdir(parents=True, exist_ok=True)
            repo = "sentence-transformers/all-MiniLM-L6-v2"
            for filename in ['onnx/model.onnx', 'tokenizer.json', 'config.json']:
                path = hf_hub_download(repo_id=repo, filename=filename)
                basename = os.path.basename(filename)
                sh.copy2(path, str(model_dir / basename))
                print(f"  Downloaded: {basename}")
            print("✅ Model download complete")
        except Exception as e:
            print(f"❌ Model download failed: {e}")
            return

    # Step 2: Verify model works
    print()
    print("🔍 Verifying model...")
    try:
        model = EmbeddingModel()
        result = model.embed("test")
        print(f"✅ Model works ({len(result)} dimensions)")
    except Exception as e:
        print(f"❌ Model verification failed: {e}")
        return

    # Step 3: Install timer
    print()
    system = platform.system()

    if system == "Darwin":
        _setup_launchd(project_dir)
    elif system == "Linux":
        _setup_cron(project_dir)
    else:
        print(f"⚠️  Auto-timer not supported on {system}")
        print(f"   Run manually: cm-embed batch")

    # Step 4: Summary
    print()
    print("🎉 Embedding setup complete!")
    print(f"   Model: {model_dir}")
    print(f"   Batch: cm-embed batch")
    print(f"   Stats: cm-embed stats")


def _setup_launchd(project_dir):
    """Install launchd plist for macOS."""
    import subprocess

    plist_name = "dev.context-wolf.embedding"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{plist_name}.plist"
    cron_script = project_dir / "embedding_worker" / "cron_embed.sh"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{cron_script}</string>
    </array>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>StandardOutPath</key>
    <string>{project_dir}/embedding_worker/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>{project_dir}/embedding_worker/launchd.log</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    # Unload old if exists
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)],
                       capture_output=True)

    plist_path.write_text(plist_content)

    result = subprocess.run(["launchctl", "load", str(plist_path)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ launchd timer installed (every 10 min)")
    else:
        print(f"❌ launchd install failed: {result.stderr}")
        print(f"   Plist written to: {plist_path}")


def _setup_cron(project_dir):
    """Install cron job for Linux."""
    import subprocess

    cron_script = project_dir / "embedding_worker" / "cron_embed.sh"
    cron_line = f"*/10 * * * * {cron_script}"

    # Check if already installed
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    if "cron_embed.sh" in existing:
        print("✅ Cron job already installed")
        return

    new_crontab = existing.rstrip() + f"\n{cron_line}\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab,
                          capture_output=True, text=True)
    if proc.returncode == 0:
        print("✅ Cron job installed (every 10 min)")
    else:
        print(f"❌ Cron install failed: {proc.stderr}")
        print(f"   Add manually: {cron_line}")


def main():
    parser = argparse.ArgumentParser(description="CM Embedding Worker")
    sub = parser.add_subparsers(dest="command")

    # embed
    embed_p = sub.add_parser("embed", help="Embed single text → JSON")
    embed_p.add_argument("text", type=str)
    embed_p.set_defaults(func=cmd_embed)

    # batch
    batch_p = sub.add_parser("batch", help="Batch-embed missing entries")
    batch_p.add_argument("--limit", type=int, default=None, help="Max entries")
    batch_p.set_defaults(func=cmd_batch)

    # stats
    stats_p = sub.add_parser("stats", help="Show embedding stats")
    stats_p.set_defaults(func=cmd_stats)

    # setup
    setup_p = sub.add_parser("setup", help="Download model + install timer")
    setup_p.set_defaults(func=cmd_setup)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
