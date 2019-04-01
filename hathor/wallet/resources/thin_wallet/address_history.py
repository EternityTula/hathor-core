import json
from typing import Set

from twisted.web import resource
from twisted.web.http import Request

from hathor.api_util import set_cors
from hathor.cli.openapi_files.register import register_resource


@register_resource
class AddressHistoryResource(resource.Resource):
    """ Implements a web server API to return the address history

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        self.manager = manager

    def render_GET(self, request: Request) -> bytes:
        """ GET request for /thin_wallet/address_history/
            Expects 'addresses[]' as request args
            'addresses[]' is an array of address

            Returns an array of WalletIndex for each address

            :rtype: string (json)
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        wallet_index = self.manager.tx_storage.wallet_index

        if not wallet_index:
            request.setResponseCode(503)
            return json.dumps({'success': False}, indent=4).encode('utf-8')

        addresses = request.args[b'addresses[]']

        history = []
        seen: Set[bytes] = set()
        for address_to_decode in addresses:
            address = address_to_decode.decode('utf-8')
            for tx_hash in wallet_index.get_from_address(address):
                tx = self.manager.tx_storage.get_transaction(tx_hash)
                if tx_hash not in seen:
                    seen.add(tx_hash)
                    history.append(tx.to_json_extended())

        data = {'history': history}
        return json.dumps(data, indent=4).encode('utf-8')


AddressHistoryResource.openapi = {
    '/thin_wallet/address_history': {
        'get': {
            'tags': ['thin_wallet'],
            'operationId': 'address_history',
            'summary': 'History of some addresses',
            'parameters': [
                {
                    'name': 'addresses[]',
                    'in': 'query',
                    'description': 'Stringified array of addresses',
                    'required': True,
                    'schema': {
                        'type': 'string'
                    }
                },
            ],
            'responses': {
                '200': {
                    'description': 'Success',
                    'content': {
                        'application/json': {
                            'examples': {
                                'success': {
                                    'summary': 'Success',
                                    'value': {
                                        'history': [
                                            {
                                                "hash": "00000299670db5814f69cede8b347f83"
                                                        "0f73985eaa4cd1ce87c9a7c793771336",
                                                "timestamp": 1552422415,
                                                "is_voided": False,
                                                "inputs": [
                                                    {
                                                        "value": 42500000044,
                                                        "script": "dqkURJPA8tDMJHU8tqv3SiO18ZCLEPaIrA==",
                                                        "decoded": {
                                                            "type": "P2PKH",
                                                            "address": "17Fbx9ouRUD1sd32bp4ptGkmgNzg7p2Krj",
                                                            "timelock": None
                                                            },
                                                        "token": "00",
                                                        "tx": "000002d28696f94f89d639022ae81a1d"
                                                              "870d55d189c27b7161d9cb214ad1c90c",
                                                        "index": 0
                                                        }
                                                    ],
                                                "outputs": [
                                                    {
                                                        "value": 42499999255,
                                                        "script": "dqkU/B6Jbf5OnslsQrvHXQ4WKDTSEGKIrA==",
                                                        "decoded": {
                                                            "type": "P2PKH",
                                                            "address": "1Pz5s5WVL52MK4EwBy9XVQUzWjF2LWWKiS",
                                                            "timelock": None
                                                            },
                                                        "token": "00"
                                                        },
                                                    {
                                                        "value": 789,
                                                        "script": "dqkUrWoWhiP+qPeI/qwfwb5fgnmtd4CIrA==",
                                                        "decoded": {
                                                            "type": "P2PKH",
                                                            "address": "1GovzJvbzLw6x4H2a1hHb529cpEWzh3YRd",
                                                            "timelock": None
                                                            },
                                                        "token": "00"
                                                        }
                                                    ]
                                                }
                                        ]
                                    }
                                },
                                'error': {
                                    'summary': 'Invalid address',
                                    'value': {
                                        'success': False,
                                        'message': 'The address xx is invalid',
                                    }
                                },
                            }
                        }
                    }
                }
            }
        }
    }
}
