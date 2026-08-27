# Contributing to Assay

Thanks for taking a look. This repo packages a Claude Code plugin — markdown
commands, skills, and shell hooks — plus a Python test harness that validates
the plugin's own structure.

## Dev setup

The plugin itself has no runtime dependencies. The Python toolchain exists only
to run the structure tests. You need [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/shadybad/assay.git
cd assay
uv sync
```

## The checks

CI runs exactly what you can run locally:

```bash
uv run pytest              # validate plugin structure
uv run ruff check .        # lint
uv run ruff format .       # format (use --check in CI)
```

`tests/` does not test application logic — there is none. It enforces invariants
that keep the plugin loadable and the docs honest:

| Test file | Enforces |
|-----------|----------|
| `test_plugin_manifest.py` | `plugin.json` is valid, versioned, and its stated skill count matches reality. |
| `test_skills.py` | Every skill has a `SKILL.md` with well-formed frontmatter whose `name` matches its directory. |
| `test_commands.py` | Every command has frontmatter whose `name` matches its filename. |
| `test_judge_panel.py` | The judge-panel roster actually contains the 29 judges it claims. |
| `test_docs_links.py` | Every relative link in the docs resolves to a real file. |
| `test_hooks.py` | Every hook/script has a shebang and the executable bit. |
| `test_config.py` | The per-install config reader degrades to defaults on an absent, partial, or corrupt file. |
| `test_pipeline_wiring.py` | No dangling cross-references: the lifecycle commands exist, done-gate documents nine checks, `/assay` invokes the TDD loop, every config key is documented, and nothing still delegates to an uninstalled plugin. |

If you add a skill, command, or doc, the harness will tell you what's
inconsistent before CI does.

## Pull requests

- Keep changes focused; one concern per PR.
- Run the three checks above before pushing. CI gates on them.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for messages
  (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `perf:`).
- Update `CHANGELOG.md` under `[Unreleased]` for anything user-facing.

## Dogfooding

This repo is developed with its own pipeline — changes ship through `/assay`,
which runs the same lint/test/judge gates described above before any commit.
