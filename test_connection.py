"""Console alternative. Use --fleet fleet.csv, --imo 1234567, or no option for login only."""
import argparse
import getpass
import json
from datetime import datetime, timezone
from pathlib import Path
from marorka_client import APIError, MarorkaClient, fetch_fleet, parse_fleet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--imo')
    group.add_argument('--fleet', type=Path)
    args = parser.parse_args()
    rows = parse_fleet(args.fleet.read_text(encoding='utf-8-sig')) if args.fleet else (
        [{'ShipName': '', 'IMONo': args.imo}] if args.imo else [])
    username = input('Marorka Weather Routing API username: ')
    password = getpass.getpass('Password (hidden): ')
    with MarorkaClient(username, password) as client:
        password = None
        print('Requesting token from /api/auth/online/token ...')
        client.authenticate()
        print('SUCCESS: Token generated. Token value is not displayed or saved.')
        if rows:
            results = fetch_fleet(client, rows, lambda n, t: print(f'Processed {n}/{t}'))
            target = Path('marorka_results_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.json')
            target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            for row in results:
                print(row['IMONo'], row['Status'], row['Error'] or '')
            print('Saved:', target.resolve())
            return 1 if any(r['Status'] in ('Failed', 'Not attempted') for r in results) else 0
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (APIError, ValueError, OSError) as exc:
        print('FAILED:', exc)
        if isinstance(exc, APIError) and exc.diagnostics:
            print('Safe authentication diagnostics:')
            print(json.dumps(exc.diagnostics, indent=2))
        raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        raise SystemExit(1)
