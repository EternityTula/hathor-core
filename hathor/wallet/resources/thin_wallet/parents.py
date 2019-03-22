import json
from threading import Lock
from typing import Optional

from twisted.web.http import Request
from twisted.web import resource

from hathor.api_util import get_missing_params_msg, set_cors
from hathor.cli.openapi_files.register import register_resource
from hathor.exception import InvalidNewTransaction
from hathor.transaction import Transaction
from hathor.transaction.exceptions import TxValidationError


@register_resource
class ParentsResource(resource.Resource):
    """ Implements a web server API to get parents for a tx

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        # Important to have the manager so we can know the tx_storage
        self.manager = manager
        self.lock = Lock()

    def render_GET(self, request: Request):
        """ POST request for /thin_wallet/parents/
            We expect 'tx_hex' as request args
            'tx_hex': serialized tx in hexadecimal
            We return success (bool)

            :rtype: string (json)
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        if b'tx_hex' not in request.args:
            return get_missing_params_msg('hex_tx')

        tx_hex = request.args[b'tx_hex'][0].decode('utf-8')
        try:
            tx = Transaction.create_from_struct(bytes.fromhex(tx_hex))
        except struct.error:
            data = {'success': False, 'message': 'Invalid transaction'}
            return json.dumps(data).encode('utf-8')

        assert isinstance(tx, Transaction)
        tx.storage = self.manager.tx_storage

        max_ts_spent_tx = max(tx.get_spent_tx(txin).timestamp for txin in tx.inputs)
        # Timestamp as max between tx and inputs
        timestamp = max(max_ts_spent_tx + 1, tx.timestamp)
        parents = self.manager.get_new_tx_parents(timestamp)
        parents_hex = [parent.hex() for parent in parents]
        data = {'success': True, 'parents': ','.join(parents_hex)}
        return json.dumps(data).encode('utf-8')


ParentsResource.openapi = {
    '/thin_wallet/parents': {
        'get': {
            'tags': ['thin-wallet'],
            'operationId': 'thin_wallet_parents',
            'summary': 'Parents of a transaction',
            'description': 'Returns the transactions that will be confirmed by the one sent as parameter. (tx_id in hex separated by ,)',
            'parameters': [
                {
                    'name': 'hex_tx',
                    'in': 'query',
                    'description': 'Transaction that wants the parents',
                    'required': True,
                    'schema': {
                        'type': 'string'
                    }
                }
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
                                        'success': True,
                                        'parents': ('00000257054251161adff5899a451ae974ac62ca44a7a31179eec5750b0ea406,'
                                                    '00000b8792cb13e8adb51cc7d866541fc29b532e8dec95ae4661cf3da4d42cb4'),
                                    }
                                },
                                'error': {
                                    'summary': 'Invalid transaction',
                                    'value': {
                                        'success': False,
                                        'message': 'Invalid transaction'
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