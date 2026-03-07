"""Single entry point to start EarWitness."""

import sys

import uvicorn

if __name__ == "__main__":
    # --dev flag enables auto-reload for development
    dev = "--dev" in sys.argv
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=dev)
