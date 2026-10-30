# Prompt texts (v1)

The prompts Safe Cut sends, from the specs in `docs/prompts/` (v0). `{name}` slots are filled by
`safecut.scout.prompts.render`; nothing else in a file is ever interpreted. Change a prompt by editing its file
and bumping `VERSION` in `safecut/scout/prompts/__init__.py`; the version is recorded with every call.
