"""Serve a separate sample seller database, never a real store database."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8783)
    parser.add_argument('--local-http', action='store_true')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if not args.env_file.is_file():
        parser.error('Supply a private env file with the isolated demo database and session secret.')
    root = Path(__file__).resolve().parent
    sys.path[:0] = [str(root), str(root / 'backend')]
    os.environ['DIP_ENV_FILE'] = str(args.env_file.resolve())
    os.environ['DJANGO_SETTINGS_MODULE'] = (
        'config.seller_web_demo_local' if args.local_http else 'config.seller_public_demo')
    import django
    django.setup()
    if args.prepare:
        from django.core.management import call_command
        call_command('migrate', interactive=False)
        call_command('createcachetable')
        call_command('collectstatic', interactive=False, verbosity=0)
        return
    from django.core.wsgi import get_wsgi_application
    from waitress import serve
    options = {} if args.local_http else {
        'trusted_proxy': '127.0.0.1',
        'trusted_proxy_headers': {'x-forwarded-proto'},
    }
    serve(get_wsgi_application(), host='127.0.0.1', port=args.port, threads=6, **options)


if __name__ == '__main__':
    main()
