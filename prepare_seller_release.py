"""Build an immutable native release candidate without server credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def validate(origin, appid, operator, contact, version):
    parts = urlsplit(origin)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.port or parts.path not in ('', '/') or parts.query or parts.fragment
            or parts.hostname.endswith(('.trycloudflare.com', '.invalid', '.test', '.localhost'))
            or not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', parts.hostname)
            or parts.hostname.startswith('replace')):
        raise ValueError('Use a permanent HTTPS domain; temporary preview origins are not accepted.')
    if not re.fullmatch(r'wx[0-9a-f]{16}', appid):
        raise ValueError('A real Mini Program AppID is required.')
    if len(operator.strip()) < 2 or operator.startswith('REPLACE_'):
        raise ValueError('Supply the actual operator name that can be published.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', contact) or contact.startswith('REPLACE_'):
        raise ValueError('Supply a monitored public support email.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Use a version such as 1.0.0.')
    return 'https://' + parts.hostname


def build(origin, appid, operator, contact, version, target):
    origin = validate(origin, appid, operator, contact, version)
    if target.exists():
        raise ValueError('Release directory already exists; use a new version.')
    target.mkdir(parents=True)
    for source in (ROOT / 'miniprogram').rglob('*'):
        relative = source.relative_to(ROOT / 'miniprogram')
        if source.is_file() and source.suffix in ('.js', '.json', '.wxml', '.wxss') and not (
            'tests' in relative.parts or source.name == 'project.private.config.json' or any(p.startswith('.') for p in relative.parts)
        ):
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
    (target / 'config.js').write_text('module.exports = ' + json.dumps({
        'apiBase': origin + '/api/seller-agent/v1', 'authMode': 'wechat'}) + ';\n', encoding='utf-8')
    (target / 'public-config.js').write_text('module.exports = ' + json.dumps({
        'name': '卖家智能X助手', 'operator': operator, 'contact': contact,
        'privacyVersion': '2026-10-16'}, ensure_ascii=False) + ';\n', encoding='utf-8')
    project_path = target / 'project.config.json'
    project = json.loads(project_path.read_text(encoding='utf-8'))
    project.update(appid=appid, projectname='seller-release-' + version)
    project.setdefault('setting', {})['urlCheck'] = True
    project_path.write_text(json.dumps(project, indent=2) + '\n', encoding='utf-8')
    files = {str(p.relative_to(target)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(target.rglob('*')) if p.is_file()}
    manifest = {'version': version, 'appid': appid, 'origin': origin, 'files': files,
                'uploaded': False, 'submittedForReview': False, 'published': False}
    (target.parent / (target.name + '.manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--appid', default='wx8cb01bd3c9f16e2a')
    parser.add_argument('--operator', required=True)
    parser.add_argument('--contact', required=True)
    parser.add_argument('--version', default='1.0.0')
    args = parser.parse_args()
    target = ROOT / '.seller-agent-runtime' / 'releases' / args.version
    try:
        manifest = build(args.origin, args.appid, args.operator, args.contact, args.version, target)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({'project': str(target), 'fileCount': len(manifest['files']), 'uploaded': False}))


if __name__ == '__main__':
    main()
