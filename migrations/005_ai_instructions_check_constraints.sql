-- Migration 005: Enforce allowed values for ai_instructions.scope and priority
-- Mirrors the CHECK constraints that already exist on infra_hosts.scope and
-- infra_services.scope. Prevents future client drift: any INSERT/UPDATE with
-- an unknown value fails at the database layer instead of silently landing
-- in the table.
--
-- Safe to run now: migration 004 normalized priority 'may' -> 'nice', and all
-- existing rows use allowed scope/priority values (verified on 2026-04-19).

ALTER TABLE ai_instructions
    ADD CONSTRAINT ai_instructions_scope_check
    CHECK (scope IN ('global', 'project', 'session'));

ALTER TABLE ai_instructions
    ADD CONSTRAINT ai_instructions_priority_check
    CHECK (priority IN ('must', 'should', 'nice'));
