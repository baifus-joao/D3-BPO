from __future__ import annotations

import traceback

from render_prepare_db import prepare_database


def main() -> None:
    prepare_database()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
