"""
Setup commands that run WITHOUT a database connection.
Used for initial setup (cm init) and diagnostics (cm doctor).
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def cmd_init(args):
    """Interactive setup wizard for new users."""
    print("🚀 ContextWolf - Setup")
    print()

    config_path = Path.home() / '.context' / 'config.yaml'

    if config_path.exists():
        print(f"⚠️  Config already exists: {config_path}")
        response = input("   Overwrite? (y/N) ").strip().lower()
        if response != 'y':
            print("   Aborted.")
            return

    # Ask: Docker or external?
    print("How do you want to run PostgreSQL?")
    print()
    print("  [1] Local Docker (recommended - we start it for you)")
    print("  [2] External server (you already have PostgreSQL running)")
    print()
    choice = input("Choice (1/2): ").strip()

    if choice == '1':
        _init_docker(config_path)
    elif choice == '2':
        _init_external(config_path)
    else:
        print("❌ Invalid choice.")
        sys.exit(1)

    # Test connection
    print()
    print("🔍 Testing connection...")
    try:
        from src.core.config import Config
        from src.core.database import Database
        config = Config()
        db = Database(config=config)
        result = db.fetchone("SELECT 1 as ok")
        db.close()
        if result and result['ok'] == 1:
            print("✅ Connection successful!")
        else:
            print("❌ Connection test failed.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print(f"   Check your config: {config_path}")
        sys.exit(1)

    print()
    print("🎉 Setup complete!")
    print()
    print("Next steps:")
    print("  cm stats                 # Verify everything works")
    print("  cm setup-mcp             # Configure Claude Code integration")


def _init_docker(config_path):
    """Ensure .env exists, start PostgreSQL via docker compose, write CLI config."""
    # Check docker is available
    if not shutil.which('docker'):
        print("❌ Docker not found. Install Docker Desktop first.")
        sys.exit(1)

    project_dir = Path(__file__).parent.parent.parent
    compose_file = project_dir / 'docker-compose.yml'
    env_file = project_dir / '.env'
    env_example = project_dir / '.env.example'

    if not compose_file.exists():
        print(f"❌ docker-compose.yml not found at {compose_file}")
        sys.exit(1)

    # Ensure .env exists (copy from template, prompt for password)
    if not env_file.exists():
        if not env_example.exists():
            print(f"❌ .env.example missing - cannot create .env")
            sys.exit(1)
        print()
        print("📄 Creating .env from template...")
        password = input("  Set POSTGRES_PASSWORD: ").strip()
        if not password:
            print("❌ Password cannot be empty.")
            sys.exit(1)
        env_content = env_example.read_text().replace(
            'POSTGRES_PASSWORD=change_me_please',
            f'POSTGRES_PASSWORD={password}'
        )
        env_file.write_text(env_content)
        os.chmod(env_file, 0o600)
        print(f"✅ Wrote {env_file}")

    # Parse .env for CLI config (so cm and docker use identical credentials)
    env = _parse_env(env_file)
    user = env.get('POSTGRES_USER', 'cm_user')
    password = env.get('POSTGRES_PASSWORD', '')
    database = env.get('POSTGRES_DB', 'context_manager')
    port = int(env.get('POSTGRES_PORT', '5432'))

    if not password:
        print("❌ POSTGRES_PASSWORD is empty in .env")
        sys.exit(1)

    print()
    print("Starting PostgreSQL + pgvector (waiting for healthcheck)...")
    result = subprocess.run(
        ['docker', 'compose', '-f', str(compose_file), 'up', '-d', '--wait'],
        capture_output=True, text=True, cwd=str(project_dir)
    )
    if result.returncode != 0:
        print(f"❌ Docker failed: {result.stderr}")
        sys.exit(1)

    print(f"✅ PostgreSQL container healthy (port {port})")

    _write_config(config_path, host='localhost', port=port,
                  database=database, user=user, password=password)


def _parse_env(env_file):
    """Minimal .env parser (KEY=VALUE, ignores comments and blank lines)."""
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _init_external(config_path):
    """Ask for external PostgreSQL credentials and write config."""
    print()
    print("Enter your PostgreSQL connection details:")
    host = input("  Host [localhost]: ").strip() or 'localhost'
    port = input("  Port [5432]: ").strip() or '5432'
    database = input("  Database [context_manager]: ").strip() or 'context_manager'
    user = input("  User [cm_user]: ").strip() or 'cm_user'
    password = input("  Password: ").strip()

    _write_config(config_path, host=host, port=int(port),
                  database=database, user=user, password=password)


def _write_config(config_path, host, port, database, user, password):
    """Write ~/.context/config.yaml"""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""database:
  backend: postgres
  postgres:
    host: {host}
    port: {port}
    database: {database}
    user: {user}
    password: {password}
"""
    config_path.write_text(content)
    os.chmod(config_path, 0o600)  # Restrict permissions (contains password)
    print(f"✅ Config written: {config_path} (mode 600)")


def _check_embedding_worker_health():
    """Inspect embedding_worker_runs table and report worker status."""
    import time
    try:
        from src.core.config import Config
        from src.core.database import Database
        db = Database(config=Config())
    except Exception:
        # PostgreSQL already reported as failing; nothing more to add
        return

    # Does the table exist? (Migration 006 may not be applied on old installs)
    try:
        row = db.fetchone("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'embedding_worker_runs'
        """)
        if not row:
            print("⚠️  Embedding worker: no run history yet (table missing or never run)")
            db.close()
            return
    except Exception:
        db.close()
        return

    # Coverage
    try:
        row = db.fetchone("""
            SELECT
                count(*) AS total,
                count(embedding) AS embedded
            FROM actions
        """)
        if row and row['total'] > 0:
            pct = 100.0 * row['embedded'] / row['total']
            mark = "✅" if pct >= 95 else "⚠️"
            print(f"{mark} Embedding coverage: {pct:.1f}% ({row['embedded']}/{row['total']})")
    except Exception:
        pass

    # Last successful run
    try:
        row = db.fetchone("""
            SELECT
                ran_at,
                EXTRACT(EPOCH FROM NOW())::BIGINT - ran_at AS seconds_since
            FROM embedding_worker_runs
            WHERE success = true
            ORDER BY ran_at DESC
            LIMIT 1
        """)
        if row:
            hours = row['seconds_since'] // 3600
            if hours < 24:
                print(f"✅ Embedding worker: last success {hours}h ago")
            elif hours < 48:
                print(f"⚠️  Embedding worker: last success {hours}h ago (getting stale)")
            else:
                print(f"❌ Embedding worker: last success {hours}h ago - likely broken")
                print("   Fix: uv sync --extra embeddings")
        else:
            print("⚠️  Embedding worker: no successful run yet")
    except Exception:
        pass

    # Recent failures (last 24h)
    try:
        row = db.fetchone("""
            SELECT count(*) AS fails, MAX(error_message) AS last_err
            FROM embedding_worker_runs
            WHERE success = false
              AND ran_at > EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')::BIGINT
        """)
        if row and row['fails'] > 0:
            print(f"❌ Embedding worker: {row['fails']} failure(s) in the last 24h")
            if row.get('last_err'):
                print(f"   Latest error: {row['last_err'][:100]}")
    except Exception:
        pass

    db.close()


def cmd_doctor(args):
    """Check prerequisites and system health."""
    print("🩺 ContextWolf - Doctor")
    print()
    issues = 0

    # 1. Python version
    py_version = sys.version_info
    if py_version >= (3, 12):
        print(f"✅ Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        print(f"❌ Python {py_version.major}.{py_version.minor} - need 3.12+")
        issues += 1

    # 2. uv
    if shutil.which('uv'):
        result = subprocess.run(['uv', '--version'], capture_output=True, text=True)
        print(f"✅ {result.stdout.strip()}")
    else:
        print("⚠️  uv not found (optional, but recommended)")

    # 3. Docker
    if shutil.which('docker'):
        print("✅ Docker available")
    else:
        print("⚠️  Docker not found (needed for local PostgreSQL)")

    # 4. Config file
    config_path = Path.home() / '.context' / 'config.yaml'
    if config_path.exists():
        print(f"✅ Config: {config_path}")
    else:
        print(f"❌ Config missing: {config_path}")
        print("   Run: cm init")
        issues += 1

    # 5. PostgreSQL connection
    try:
        from src.core.config import Config
        from src.core.database import Database
        config = Config()
        db = Database(config=config)
        result = db.fetchone("SELECT version() as v")
        pg_version = result['v'].split(',')[0] if result else 'unknown'
        db.close()
        print(f"✅ PostgreSQL: {pg_version}")
    except Exception as e:
        error_msg = str(e).split('\n')[0]
        print(f"❌ PostgreSQL: {error_msg}")
        issues += 1

    # 6. pgvector extension
    try:
        from src.core.config import Config
        from src.core.database import Database
        config = Config()
        db = Database(config=config)
        result = db.fetchone("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        if result:
            print(f"✅ pgvector: {result['extversion']}")
        else:
            print("⚠️  pgvector not installed (semantic search won't work)")
        db.close()
    except Exception:
        pass  # Already reported above

    # 7. MCP config
    claude_json = Path.home() / '.claude.json'
    if claude_json.exists():
        import json
        try:
            data = json.loads(claude_json.read_text())
            mcp_servers = data.get('mcpServers', {})
            if 'context-manager' in mcp_servers:
                print("✅ MCP: configured in ~/.claude.json")
            else:
                print("⚠️  MCP: not configured (run: cm setup-mcp)")
        except Exception:
            print("⚠️  MCP: ~/.claude.json exists but can't be parsed")
    else:
        print("⚠️  MCP: ~/.claude.json not found")

    # 8. Embedding model
    model_path = Path(__file__).parent.parent.parent / 'embedding_worker' / 'model' / 'model.onnx'
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"✅ Embedding model: {size_mb:.0f}MB")
    else:
        print("⚠️  Embedding model not downloaded (semantic search won't work)")

    # 9. Embedding worker health
    _check_embedding_worker_health()

    # Summary
    print()
    if issues == 0:
        print("🎉 Everything looks good!")
    else:
        print(f"⚠️  {issues} issue(s) found. Fix them and run cm doctor again.")


def cmd_setup_mcp(args):
    """Configure MCP server in ~/.claude.json"""
    import json

    claude_json = Path.home() / '.claude.json'
    project_dir = Path(__file__).parent.parent.parent.resolve()

    mcp_entry = {
        "type": "stdio",
        "command": "uv",
        "args": [
            "--directory", str(project_dir),
            "run", "cm-mcp"
        ]
    }

    if claude_json.exists():
        data = json.loads(claude_json.read_text())
    else:
        data = {}

    if 'mcpServers' not in data:
        data['mcpServers'] = {}

    old = data['mcpServers'].get('context-manager')
    data['mcpServers']['context-manager'] = mcp_entry

    claude_json.write_text(json.dumps(data, indent=2) + '\n')

    if old:
        print("✅ MCP config updated in ~/.claude.json")
    else:
        print("✅ MCP config added to ~/.claude.json")

    print(f"   Server: uv --directory {project_dir} run cm-mcp")
    print()
    print("Restart Claude Code to apply changes.")
