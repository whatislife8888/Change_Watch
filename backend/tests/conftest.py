"""
conftest.py — shared pytest setup: point DATA_DIR at a temporary folder so tests never touch real data.
"""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cw-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret")
