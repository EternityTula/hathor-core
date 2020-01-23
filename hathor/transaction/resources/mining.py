import enum

from twisted.web import resource

from hathor.api_util import set_cors
from hathor.cli.openapi_files.register import register_resource
from hathor.crypto.util import decode_address
from hathor.transaction.base_transaction import tx_or_block_from_bytes
from hathor.util import json_dumpb, json_loadb


class Capabilities(enum.Enum):
    MERGED_MINING = 'mergedmining'


@register_resource
class GetBlockTemplateResource(resource.Resource):
    """ TODO

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        # Important to have the manager so we can know the tx_storage
        self.manager = manager

    def render_GET(self, request):
        """ GET request for /get_block_template/
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        # params
        raw_address = request.args.get(b'address')
        if raw_address:
            address = decode_address(raw_address[0].decode())
        else:
            address = None
        caps = set(map(lambda s: Capabilities(s.decode()), request.args.get(b'capabilities', [])))
        merged_mining = Capabilities.MERGED_MINING in caps

        # get block
        # XXX: miner can edit block data and output_script, so it's fine if address is Nonne
        block = self.manager.generate_mining_block(address=address, merge_mined=merged_mining)

        # serialize
        data = block.to_json()
        del data['hash']
        data.pop('nonce', None)
        data.pop('aux_pow', None)

        return json_dumpb(data)


@register_resource
class SubmitBlockResource(resource.Resource):
    """ TODO

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        # Important to have the manager so we can know the tx_storage
        self.manager = manager

    def render_POST(self, request):
        """ POST request for /submit_block/
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        data = json_loadb(request.content.read())
        tx = tx_or_block_from_bytes(bytes.fromhex(data['hexdata']), storage=self.manager.tx_storage)
        if tx.is_block:
            res = self.manager.propagate_tx(tx)
        else:
            # not a block
            res = False

        return json_dumpb({'result': res})


GetBlockTemplateResource.openapi = {
    '/get_block_template': {
        'x-visibility': 'private',
        'get': {
            'tags': ['mining'],
            'operationId': 'get_block_template',
            'summary': 'Get parameters to help a miner, pool or proxy, gather enough info to mine a block.',
            'parameters': [
                {
                    'name': 'capabilities',
                    'in': 'query',
                    'description': 'Requested capabilities when generating a block template',
                    'schema': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'enum': [i.value for i in Capabilities]
                        }
                    }
                }
            ],
            'responses': {
                '200': {
                    'description': 'Success',
                    'content': {
                        'application/json': {
                            'examples': {
                                #  TODO
                                # 'success': {
                                #     'summary': 'Success',
                                #     'value': {
                                #         'success': True
                                #     }
                                # },
                                # 'error1': {
                                #     'summary': 'Transaction invalid',
                                #     'value': {
                                #         'success': False,
                                #         'message': 'This transaction is invalid.',
                                #         'can_force': False
                                #     }
                                # },
                                # 'error2': {
                                #     'summary': 'Error propagating transaction',
                                #     'value': {
                                #         'success': False,
                                #         'message': 'Error message',
                                #         'can_force': True
                                #     }
                                # },
                                # 'error3': {
                                #     'summary': 'Double spending error',
                                #     'value': {
                                #         'success': False,
                                #         'message': ('Invalid transaction. At least one of your inputs has'
                                #                     'already been spent.')
                                #     }
                                # },
                            }
                        }
                    }
                }
            }
        }
    }
}


SubmitBlockResource.openapi = {
    '/submit_block': {
        'x-visibility': 'private',
        'post': {
            'tags': ['mining'],
            'operationId': 'submit_block',
            'summary': 'Called by a miner to submit a block they found',
            'requestBody': {
                'description': 'Data to be propagated',
                'required': True,
                'content': {
                    'application/json': {
                        'schema': {
                            'type': 'object',
                            'properties': {
                                'hexdata': {
                                    'type': 'string'
                                }
                            }
                        }
                    }
                }
            },
            'responses': {
                '200': {
                    'description': 'Success',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'result': {
                                        'type': 'bool'
                                    }
                                }
                            },
                            'examples': {
                                'result': None
                            }
                        }
                    }
                }
            }
        }
    }
}
