"""
Copyright 2019 Hathor Labs

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json

from twisted.web import resource

import hathor
from hathor.api_util import set_cors
from hathor.cli.openapi_files.register import register_resource
from hathor.conf import HathorSettings

settings = HathorSettings()


@register_resource
class VersionResource(resource.Resource):
    """ Implements a web server API with POST to return the api version and some configuration

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        # Important to have the manager so we can have access to min_tx_weight_coefficient
        self.manager = manager

    def render_GET(self, request):
        """ GET request for /version/ that returns the API version

            :rtype: string (json)
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        data = {
            'version': hathor.__version__,
            'network': self.manager.network,
            'min_weight': self.manager.min_tx_weight,  # DEPRECATED
            'min_tx_weight': self.manager.min_tx_weight,
            'min_tx_weight_coefficient': self.manager.min_tx_weight_coefficient,
            'min_tx_weight_k': self.manager.min_tx_weight_k,
            'token_deposit_percentage': settings.TOKEN_DEPOSIT_PERCENTAGE,
        }
        return json.dumps(data, indent=4).encode('utf-8')


VersionResource.openapi = {
    '/version': {
        'x-visibility': 'public',
        'x-rate-limit': {
            'global': [
                {
                    'rate': '360r/s',
                    'burst': 360,
                    'delay': 180
                }
            ],
            'per-ip': [
                {
                    'rate': '3r/s',
                    'burst': 10,
                    'delay': 3
                }
            ]
        },
        'get': {
            'operationId': 'version',
            'summary': 'Hathor version',
            'responses': {
                '200': {
                    'description': 'Success',
                    'content': {
                        'application/json': {
                            'examples': {
                                'success': {
                                    'summary': 'Success',
                                    'value': {
                                        'version': '0.16.0-beta',
                                        'network': 'testnet-bravo',
                                        'min_weight': 14,
                                        'min_tx_weight': 14,
                                        'min_tx_weight_coefficient': 1.6,
                                        'min_tx_weight_k': 100,
                                        'token_deposit_percentage': 0.01,
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
