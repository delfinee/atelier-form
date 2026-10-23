"""Prepare a real-WeChat client and serve its authenticated API behind HTTPS."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.seller-agent-runtime'


def https_origin(value):
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.port or parts.path not in ('', '/') or parts.query or parts.fragment):
        raise argparse.ArgumentTypeError('Use an HTTPS origin without a path, credentials or port.')
    return 'https://' + parts.hostname


def prepare_project(origin, appid):
    target = RUNTIME / 'phone-miniprogram'
    target.mkdir(parents=True, exist_ok=True)
    # Only source files, never credentials, IDE private configuration or test harnesses.
    for source in (ROOT / 'miniprogram').rglob('*'):
        relative = source.relative_to(ROOT / 'miniprogram')
        if 'tests' in relative.parts or source.name.startswith('.') or source.name == 'project.private.config.json':
            continue
        if source.is_file():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    (target / 'config.js').write_text('module.exports = ' + json.dumps({
        'apiBase': origin + '/api/seller-agent/v1', 'authMode': 'wechat'}) + ';\n', encoding='utf-8')
    config_path = target / 'project.config.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    config.update(appid=appid, projectname='atelier-form-seller-phone')
    config.setdefault('setting', {})['urlCheck'] = True
    config_path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, default=RUNTIME / 'wechat-secrets.env')
    parser.add_argument('--origin', type=https_origin, required=True)
    parser.add_argument('--port', type=int, default=8781)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    import environ
    for filename in (args.env_file, args.credentials):
        if not filename.is_file():
            parser.error('Missing server configuration file: ' + str(filename))
    environ.Env.read_env(args.env_file, overwrite=True)
    environ.Env.read_env(args.credentials, overwrite=True)
    if not os.environ.get('WECHAT_APP_ID', '').startswith('wx'):
        parser.error('Set the intended WECHAT_APP_ID in the server credentials file.')
    os.environ.update(DIP_ENV_FILE=str(args.env_file.resolve()), DJANGO_DEBUG='0',
        DJANGO_SETTINGS_MODULE='config.seller_phone', DJANGO_ALLOWED_HOSTS=urlsplit(args.origin).hostname,
        CSRF_TRUSTED_ORIGINS=args.origin, CORS_ALLOWED_ORIGINS=args.origin,
        WECHAT_SELLER_DEV_LOGIN='0', WECHAT_SELLER_ENABLED='1', SELLER_AGENT_ENABLED='1')
    sys.path.insert(0, str(ROOT / 'backend'))
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    RUNTIME.mkdir(exist_ok=True)
    project = prepare_project(args.origin, settings.WECHAT_APP_ID)
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)
    call_command('check', verbosity=0)
    state = {'origin': args.origin, 'project': str(project), 'port': args.port,
             'appid': settings.WECHAT_APP_ID, 'credentials_configured': bool(settings.WECHAT_APP_SECRET)}
    (RUNTIME / 'phone-preview.json').write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(state), flush=True)
    if args.prepare_only:
        return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            raise SystemExit('Phone API port is in use. Stop the previous phone server first.')
    from waitress import create_server
    server = create_server(get_wsgi_application(), host='127.0.0.1', port=args.port, threads=6,
        max_request_body_size=8 * 1024 * 1024, trusted_proxy='127.0.0.1', trusted_proxy_count=1,
        trusted_proxy_headers={'x-forwarded-proto'})
    stop = RUNTIME / ('stop-' + str(args.port))
    stop.unlink(missing_ok=True)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    print('Phone API ready. Developer identities are disabled; official WeChat credentials are required.', flush=True)
    try:
        while thread.is_alive() and not stop.exists():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        stop.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
