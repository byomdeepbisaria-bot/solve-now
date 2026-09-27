
import sys
try:
    import core.redis
    import services.events
    import worker.celery
    import main
    print('All imports successful.')
except Exception as e:
    print(f'Import failed: {e}')
    sys.exit(1)

