"""Dev entry point. Production runs uvicorn against ainews.app:app directly."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("ainews.app:app", host="127.0.0.1", port=8006, reload=True)


if __name__ == "__main__":
    main()
