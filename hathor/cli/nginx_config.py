import json
import os
from enum import Enum
from typing import Any, Dict, List, NamedTuple, Optional, TextIO, Tuple

from hathor.cli.openapi_json import get_openapi_dict

BASE_PATH = os.path.join(os.path.dirname(__file__), 'nginx_files')


def get_openapi(src_file: Optional[TextIO] = None) -> Dict[str, Any]:
    """ Open and parse the json file or generate OpenAPI dict on-the-fly
    """
    if src_file is None:
        return get_openapi_dict()
    else:
        return json.load(src_file)


def warn(msg: str) -> None:
    """ Print a warning to stderr
    """
    import sys
    print(msg, file=sys.stderr)


class Visibility(Enum):
    PRIVATE = 'private'
    PUBLIC = 'public'


class RateLimitZone(NamedTuple):
    name: str
    key: str
    size: str
    rate: str

    def to_nginx_config(self) -> str:
        """ Convert to nginx configuration line
        """
        return f'limit_req_zone {self.key} zone={self.name}:{self.size} rate={self.rate};\n'


class RateLimit(NamedTuple):
    zone: str
    burst: Optional[int] = None
    delay: Optional[int] = None

    def to_nginx_config(self) -> str:
        """ Convert to nginx configuration line
        """
        conf = f'limit_req zone={self.zone}'
        if self.burst is not None:
            conf += f' burst={self.burst}'
        if self.delay is not None:
            if self.delay == 0:
                conf += ' nodelay'
            else:
                conf += f' delay={self.delay}'
        conf += ';\n'
        return conf


def _scale_rate_limit(raw_rate: str, rate_k: float) -> str:
    """ Multiplies a string rate limit by a contant amount returning a valid rate limit

    Examples:
    >>> _scale_rate_limit('10r/s', 0.5)
    '5r/s'
    >>> _scale_rate_limit('1r/s', 0.5)
    '30r/m'
    >>> _scale_rate_limit('1r/s', 2.5)
    '2r/s'
    """
    if not raw_rate.endswith('r/s') or raw_rate.endswith('r/m'):
        raise ValueError(f'"{raw_rate}" must end in either "r/s" or "r/m"')
    raw_rate_amount = int(raw_rate[:-3])
    rate_units = raw_rate[-3:]
    scaled_rate_amount = raw_rate_amount * rate_k
    if scaled_rate_amount < 1:
        if rate_units == 'r/m':
            raise ValueError(f'final rate {scaled_rate_amount}r/m is too small')
        rate_units = 'r/m'
        scaled_rate_amount *= 60
    if scaled_rate_amount < 1:
        raise ValueError(f'final rate {scaled_rate_amount}r/m is too small')
    return f'{int(scaled_rate_amount)}{rate_units}'


def _get_visibility(source: dict, fallback: Visibility) -> Tuple[Visibility, bool]:
    if 'x-visibility' in source:
        return Visibility(source['x-visibility']), False
    else:
        return fallback, True


def generate_nginx_config(openapi, *, out_file, rate_k: float = 1.0,
                          fallback_visibility: Visibility = Visibility.PRIVATE) -> None:
    """ Entry point of the functionality provided by the cli
    """
    from datetime import datetime

    locations: Dict[str, Dict[str, Any]] = {}
    limit_rate_zones: List[RateLimitZone] = []
    for path, params in openapi['paths'].items():
        visibility, did_fallback = _get_visibility(params, fallback_visibility)
        if did_fallback:
            warn(f'Visibility not set for path `{path}`, falling back to {fallback_visibility}')
        if visibility is Visibility.PRIVATE:
            continue

        location_params: Dict[str, Any] = {
            'rate_limits': [],
            'path_vars_re': params.get('x-path-params-regex', {}),
        }

        allowed_methods = {'OPTIONS'}
        for method in 'get post put patch delete head options trace'.split():
            if method not in params:
                continue
            method_params = params[method]
            method_visibility, _ = _get_visibility(method_params, Visibility.PUBLIC)
            if method_visibility is Visibility.PRIVATE:
                continue
            allowed_methods.add(method.upper())
        location_params['allowed_methods'] = sorted(allowed_methods)

        if not allowed_methods:
            warn(f'Path `{path}` has no public methods but is public')
            continue

        rate_limits = params.get('x-rate-limit')
        if not rate_limits:
            continue

        path_key = path.lower().replace('/', '__').replace('.', '__').replace('{', '').replace('}', '')

        global_rate_limits = rate_limits.get('global', [])
        for i, rate_limit in enumerate(global_rate_limits):
            # zone, for top level `limit_req_zone`
            name = f'global{path_key}__{i}'  # must match [a-z][a-z0-9_]*
            size = '32k'  # min is 32k which is enough
            rate = _scale_rate_limit(rate_limit['rate'], rate_k)
            zone = RateLimitZone(name, 'global', size, rate)
            limit_rate_zones.append(zone)
            # limit, for location level `limit_req`
            burst = rate_limit.get('burst')
            delay = rate_limit.get('delay')
            location_params['rate_limits'].append(RateLimit(zone.name, burst, delay))

        per_ip_rate_limits = rate_limits.get('per-ip', [])
        for i, rate_limit in enumerate(per_ip_rate_limits):
            name = f'per_ip{path_key}__{i}'  # must match [a-z][a-z0-9_]*
            # zone, for top level `limit_req_zone`
            size = '10m'
            rate = _scale_rate_limit(rate_limit['rate'], rate_k)
            zone = RateLimitZone(name, '$perip', size, rate)
            limit_rate_zones.append(zone)
            # limit, for location level `limit_req`
            burst = rate_limit.get('burst')
            delay = rate_limit.get('delay')
            location_params['rate_limits'].append(RateLimit(zone.name, burst, delay))

        locations[path] = location_params

    # TODO: consider using a templating engine

    header = f'''# THIS FILE WAS AUTOGENERATED BY THE `hathor-cli nginx-config` TOOL AT {datetime.now()}

server_tokens off;

'''

    server_open = '''
upstream backend {
    server fullnode:8080;
}

server {
    listen 80;
    server_name localhost;

    set $perip $remote_addr;  # binary_remote_addr won't help much anyway
    if ($http_x_forwarded_for) {
        set $perip $http_x_forwarded_for;
    }

    limit_req_status 429;
    error_page 429 @429;
    location @429 {
        include cors_params;
        try_files /path/doesnt/matter =429;
    }
    location ~ ^/ws/?$ {
        include cors_params;
        include proxy_params;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_pass http://backend;
    }'''
    # TODO: maybe return 403 instead?
    server_close = '''
    location / {
        return 403;
    }
}
'''

    out_file.write(header)

    # http level settings
    for zone in sorted(limit_rate_zones):
        out_file.write(zone.to_nginx_config())

    out_file.write(server_open)
    # server level settings
    for location_path, location_params in locations.items():
        location_path = location_path.replace('.', r'\.').strip('/').format(**location_params['path_vars_re'])
        location_open = f'''
    location ~ ^/{location_path}/?$ {{
        include cors_params;
        include proxy_params;
'''
        location_close = '''\
        proxy_pass http://backend;
    }'''
        out_file.write(location_open)
        methods = ' '.join(location_params['allowed_methods'])
        out_file.write(' ' * 8 + f'limit_except {methods} {{ deny all; }}\n')
        for rate_limit in location_params.get('rate_limits', []):
            out_file.write(' ' * 8 + rate_limit.to_nginx_config())
        out_file.write(location_close)
    out_file.write(server_close)


def main():
    import argparse
    import sys

    from hathor.cli.util import create_parser

    parser = create_parser()
    parser.add_argument('-k', '--rate-multiplier', type=float, default=1.0,
                        help='How much to multiply all rates by (float)')
    parser.add_argument('-i', '--input-openapi-json', type=argparse.FileType('r', encoding='UTF-8'), default=None,
                        help='Input file with OpenAPI json, if not specified the spec is generated on-the-fly')
    parser.add_argument('--fallback-visibility', type=Visibility, default=Visibility.PRIVATE,
                        help='Set the visibility for paths without `x-visibility`, defaults to private')
    parser.add_argument('out', type=argparse.FileType('w', encoding='UTF-8'), default=sys.stdout, nargs='?',
                        help='Output file where nginx config will be written')
    args = parser.parse_args()

    openapi = get_openapi(args.input_openapi_json)
    generate_nginx_config(openapi, out_file=args.out, rate_k=args.rate_multiplier,
                          fallback_visibility=args.fallback_visibility)
