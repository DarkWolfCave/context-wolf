"""
ContextWolf - Main Entry Point

Usage:
    python3 -m src save "Implemented feature X"
    python3 -m src search "database"
    python3 -m src ai --quick
"""

import sys

from .core.database import Database
from .core.config import Config
from .cli.parser import create_parser
from .cli.handlers import CommandHandlers, dispatch_command


def main():
    """
    Main entry point for ContextWolf.

    Architecture:
    1. Parse arguments
    2. Initialize database and config
    3. Create all managers
    4. Dispatch command to handler

    Clean dependency flow:
    CLI → Features → Domain → Core
    """
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Setup commands run WITHOUT database connection
    if args.command in ('init', 'doctor', 'setup-mcp'):
        from .cli.setup_commands import cmd_init, cmd_doctor, cmd_setup_mcp
        commands = {'init': cmd_init, 'doctor': cmd_doctor, 'setup-mcp': cmd_setup_mcp}
        commands[args.command](args)
        sys.exit(0)

    try:
        # Initialize infrastructure
        config = Config()
        db = Database()

        # Create handlers (which initialize all managers)
        handlers = CommandHandlers(db, config)

        # Dispatch to appropriate handler
        dispatch_command(args, handlers)

    except KeyboardInterrupt:
        print("\n\n⚠️  Aborted")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if '--debug' in sys.argv:
            raise
        sys.exit(1)
    finally:
        # Clean up database connection
        try:
            db.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()