# Kiro setup

## Hooks to create (Agent Hooks panel → new hook)

Create these through Kiro's hook UI; the trigger and prompt below are what to enter.

**1. Analyzer guard**
- Trigger: file saved, matching `src/schemalens/analyzer/**/*.py`
- Prompt: "Run `pytest tests/test_analyzer.py -q`. If anything fails, explain the failure and propose a fix to the analyzer, not the tests. Once the bench command exists, also run `schemalens bench` and report the F1 change versus benchmark/RESULTS.md."

**2. Fixture-label sync**
- Trigger: file saved, matching `docker/initdb/03-bench-fixtures.sql`
- Prompt: "List any function in 03-bench-fixtures.sql that has no entry in benchmark/labels.yaml. Do not write labels yourself; remind me to label them by reading the source."

**3. Contract sync**
- Trigger: file saved, matching `src/schemalens/bundle.py`
- Prompt: "Check that web/src/types.ts still mirrors the Pydantic bundle models. List any mismatches and propose the TypeScript change."

Hook 2 deliberately does not let the AI write labels: ground truth written by the same AI that writes the analyzer would make the benchmark meaningless.

## MCP server (from task 9)

Add SchemaLens to Kiro's MCP config (workspace: `.kiro/settings/mcp.json`; confirm the location in Kiro's docs):

```json
{
  "mcpServers": {
    "schemalens": { "command": "schemalens", "args": ["mcp", "--db", "./schemalens.db"] }
  }
}
```
