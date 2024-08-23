"""Setup code to be run before all tests"""
from django.core.cache import cache


def pytest_sessionstart(session):
    """
    This function sets the 'satellites' key in cache
    so that fetching from DB is avoided in the tests
    """
    cache.set('satellites', {'dummy_entry': ''})
