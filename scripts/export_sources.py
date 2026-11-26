"""Write ui/src/sources.json, the sources page's list, from sources/manifest.toml.

    uv run python scripts/export_sources.py

Run it after changing the manifest. tests/ingest/test_manifest.py fails until you do.
"""

from __future__ import annotations

import json

from climate_chat.config import repo_root
from climate_chat.ingest.manifest import load_manifest, public_sources


def main() -> None:
    path = repo_root() / "ui" / "src" / "sources.json"
    sources = public_sources(load_manifest())
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(sources)} sources to {path.relative_to(repo_root())}")


if __name__ == "__main__":
    main()
