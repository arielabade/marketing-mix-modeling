"""``mmm <job>``: one entry point for the container and the Makefile."""

from __future__ import annotations

import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: mmm {geolift|train|evaluate|optimize|report|serve|pipeline} [--profile small]")
        return 0
    job, rest = argv[0], argv[1:]
    if job == "serve":
        import os

        import uvicorn

        uvicorn.run("mmm.serve.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
        return 0
    if job == "pipeline":
        for j in ("geolift", "train", "evaluate", "optimize", "report"):
            main([j, *rest])
        return 0
    from importlib import import_module

    import_module(f"mmm.jobs.{job}").main(rest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
