-- Migration 004: Normalize ai_instructions.priority to CLI vocabulary
-- The GUI (context-wolf-ui) initially used 'may' (RFC 2119), while the CLI
-- and docs have always used 'nice'. Unify on 'nice' so both clients see the
-- same values. No-op when no 'may' rows exist.

UPDATE ai_instructions SET priority = 'nice' WHERE priority = 'may';
