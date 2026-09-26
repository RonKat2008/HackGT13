"""Generate fixtures/demo_paper.pdf.

Run from services/orchestrator:

    .venv/bin/python fixtures/make_demo_paper.py
"""

from build_examples import adaptive, main

__all__ = ["adaptive", "main"]

if __name__ == "__main__":
    main()
