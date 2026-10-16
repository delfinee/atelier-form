"""Serve both seller channels using one configured Django database."""
import argparse
import os
from pathlib import Path
import socket
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, help='Existing platform .env, shared by website and Mini Program')
    parser.add_argument('--port',type=int,default=8780)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--storefront',action='store_true',help='Open the buyer storefront; seller operations remain in WeChat')
    args=parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            raise SystemExit('The selected environment file does not exist.')
        os.environ['DIP_ENV_FILE']=str(args.env_file.resolve())
    os.environ['DJANGO_SETTINGS_MODULE']='config.marketplace_local' if args.storefront else 'config.seller_agent_local'
    sys.path.insert(0,str(ROOT/'backend'))
    import django
    django.setup()
    from django.core.management import call_command
    if not args.prepare_only:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',args.port))==0:
                raise SystemExit('The selected port is already in use; keep the existing server or choose --port.')
    call_command('migrate',interactive=False,verbosity=0)
    call_command('collectstatic',interactive=False,verbosity=0)
    call_command('check',verbosity=0)
    if args.prepare_only:
        return
    from django.core.wsgi import get_wsgi_application
    from waitress import create_server
    server=create_server(get_wsgi_application(),host='127.0.0.1',port=args.port,threads=6,max_request_body_size=8 * 1024 * 1024)
    stop=ROOT/'.seller-agent-runtime'/f'stop-{args.port}'
    stop.unlink(missing_ok=True)
    thread=threading.Thread(target=server.run,daemon=True)
    thread.start()
    print(f'Buyer storefront: http://127.0.0.1:{args.port}/' if args.storefront else f'Seller website: http://127.0.0.1:{args.port}/seller/ai/',flush=True)
    if not args.storefront:
        print(f'Mini Program browser preview: http://127.0.0.1:{args.port}/seller/ai/mini-preview/',flush=True)
    else:
        print(f'Seller Mini Program information: http://127.0.0.1:{args.port}/seller/mini-program/',flush=True)
    print('Both channels use the same existing database. Official WeChat access is not configured by this launcher.',flush=True)
    try:
        while thread.is_alive() and not stop.exists():
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        stop.unlink(missing_ok=True)


if __name__=='__main__':
    main()
