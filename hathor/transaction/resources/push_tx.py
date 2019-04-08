import json
import re
import struct

from twisted.web import resource

from hathor.api_util import set_cors
from hathor.cli.openapi_files.register import register_resource
from hathor.transaction import Transaction


@register_resource
class PushTxResource(resource.Resource):
    """ Implements a web server API that receives hex form of a tx and send it to the network

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        # Important to have the manager so we can know the tx_storage
        self.manager = manager

    def render_GET(self, request):
        """ GET request for /push_tx/
            Expects 'hex_tx' as args parameter that is the hex representation of the whole tx

            :rtype: string (json)
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        requested_decode = request.args[b'hex_tx'][0].decode('utf-8')

        pattern = r'[a-fA-F\d]+'
        if re.match(pattern, requested_decode) and len(requested_decode) % 2 == 0:
            tx_bytes = bytes.fromhex(requested_decode)

            try:
                tx = Transaction.create_from_struct(tx_bytes)
            except struct.error:
                data = {
                    'success': False,
                    'message': 'This transaction is invalid. Try to decode it first to validate it.',
                    'can_force': False
                }
            else:
                if len(tx.inputs) == 0:
                    # It's a block and we can't push blocks
                    data = {
                        'success': False,
                        'message': 'This transaction is invalid. A transaction must have at least one input',
                        'can_force': False
                    }
                else:
                    tx.storage = self.manager.tx_storage
                    # If this tx is a double spending, don't even try to propagate in the network
                    is_double_spending = tx.is_double_spending()
                    if is_double_spending:
                        data = {
                            'success': False,
                            'message': 'Invalid transaction. At least one of your inputs has already been spent.',
                            'can_force': False
                        }
                    else:
                        success, message = tx.validate_tx_error()

                        force = b'force' in request.args and request.args[b'force'][0].decode('utf-8') == 'true'
                        if success or force:
                            success = self.manager.propagate_tx(tx)
                            data = {'success': success}
                        else:
                            data = {'success': success, 'message': message, 'can_force': True}
        else:
            data = {
                'success': False,
                'message': 'This transaction is invalid. Try to decode it first to validate it.',
                'can_force': False
            }

        return json.dumps(data, indent=4).encode('utf-8')


PushTxResource.openapi = {
    '/push_tx': {
        'get': {
            'tags': ['transaction'],
            'operationId': 'push_tx',
            'summary': 'Push transaction to the network',
            'parameters': [
                {
                    'name': 'hex_tx',
                    'in': 'query',
                    'description': 'Transaction to be pushed in hexadecimal',
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
                                        'success': True
                                    }
                                },
                                'error1': {
                                    'summary': 'Transaction invalid',
                                    'value': {
                                        'success': False,
                                        'message': 'This transaction is invalid.',
                                        'can_force': False
                                    }
                                },
                                'error2': {
                                    'summary': 'Error propagating transaction',
                                    'value': {
                                        'success': False,
                                        'message': 'Error message',
                                        'can_force': True
                                    }
                                },
                                'error3': {
                                    'summary': 'Double spending error',
                                    'value': {
                                        'success': False,
                                        'message': ('Invalid transaction. At least one of your inputs has'
                                                    'already been spent.')
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
