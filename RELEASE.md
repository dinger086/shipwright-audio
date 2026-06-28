# Release Checklist

1. Confirm `version` in `pyproject.toml` matches `shipwright/__init__.py`.
2. Run `uv run --extra dev pytest`.
3. Run `env SHIPWRIGHT_SOUNDS=examples uv run shipwright ui_blip`.
4. Run `env SHIPWRIGHT_SOUNDS=examples uv run shipwright sea_bed`.
5. Run `uv build`.
6. Run `uvx twine check dist/*`.
7. Confirm `shipwright-audio` is still available on PyPI if this is the first release.
8. Upload with `uvx twine upload dist/*`.
