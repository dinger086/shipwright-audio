#!/usr/bin/env python3
"""In-repo dev shim. The real entry point is `shipwright` (shipwright.cli:main),
installed via pyproject. This lets you run the CLI from a checkout without
installing: `python render.py sea_bed`."""
from shipwright.cli import main

if __name__ == "__main__":
    main()
