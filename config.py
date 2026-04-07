import os

# DEBUG from environment (True when 'true', '1', 'yes')
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')

# Flask secret (can be overridden by env)
FLASK_SECRET = os.environ.get('FLASK_SECRET', 'dev-secret')
