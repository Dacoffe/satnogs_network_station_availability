#!/usr/bin/env python
"""WSGI module for SatNOGS Network"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'network.settings')

application = get_wsgi_application()

if os.environ.get('USE_DEBUGPY') == '1':
    import debugpy
    debugpy.listen(("0.0.0.0", 5678))
