import json
from typing import Any, Dict

from twisted.web import resource

from hathor.api_util import set_cors, validate_tx_hash
from hathor.cli.openapi_files.register import register_resource
from hathor.conf import HathorSettings
from hathor.transaction.base_transaction import BaseTransaction, TxVersion
from hathor.transaction.token_creation_tx import TokenCreationTransaction

settings = HathorSettings()


def update_serialized_tokens_array(tx: BaseTransaction, serialized: Dict[str, Any]) -> None:
    """ A token creation tx to_json does not add its hash to the array of tokens
        We manually have to add it here to make it equal to the other transactions
    """
    if TxVersion(tx.version) == TxVersion.TOKEN_CREATION_TRANSACTION:
        # Token creation tx does not add tokens array in to_json method but we need it in this API
        assert isinstance(tx, TokenCreationTransaction)
        serialized['tokens'] = [h.hex() for h in tx.tokens]


def get_tx_extra_data(tx: BaseTransaction) -> Dict[str, Any]:
    """ Get the data of a tx to be returned to the frontend
        Returns success, tx serializes, metadata and spent outputs
    """
    serialized = tx.to_json(decode_script=True)
    serialized['raw'] = tx.get_struct().hex()
    # Update tokens array
    update_serialized_tokens_array(tx, serialized)
    meta = tx.get_metadata(force_reload=True)
    # To get the updated accumulated weight just need to call the
    # TransactionAccumulatedWeightResource (/transaction_acc_weight)

    # In the metadata we have the spent_outputs, that are the txs that spent the outputs for each index
    # However we need to send also which one of them is not voided
    spent_outputs = {}
    for index, spent_set in meta.spent_outputs.items():
        for spent in spent_set:
            if tx.storage:
                spent_tx = tx.storage.get_transaction(spent)
                spent_meta = spent_tx.get_metadata()
                if not spent_meta.voided_by:
                    spent_outputs[index] = spent_tx.hash_hex
                    break

    # Sending also output information for each input
    inputs = []
    for index, tx_in in enumerate(tx.inputs):
        if tx.storage:
            tx2 = tx.storage.get_transaction(tx_in.tx_id)
            tx2_out = tx2.outputs[tx_in.index]
            output = tx2_out.to_json(decode_script=True)
            output['tx_id'] = tx2.hash.hex()
            output['index'] = tx_in.index

            # We need to get the token_data from the current tx, and not the tx being spent
            token_uid = tx2.get_token_uid(tx2_out.get_token_index())
            for out in tx.outputs:
                out_token_uid = tx.get_token_uid(out.get_token_index())
                if out_token_uid == token_uid:
                    output['decoded']['token_data'] = out.token_data
                    break
            else:
                # This is the case when the token from the input does not appear in the outputs
                # This case can happen when we have a full melt, so all tokens from the inputs are destroyed
                # So we manually add this token to the array and set the token_data properly
                serialized['tokens'].append(token_uid.hex())
                output['decoded']['token_data'] = len(serialized['tokens'])

            inputs.append(output)

    serialized['inputs'] = inputs

    detailed_tokens = []
    for token_uid in serialized['tokens']:
        assert tx.storage is not None
        tokens_index = tx.storage.tokens_index
        assert tokens_index is not None
        token_info = tokens_index.get_token_info(bytes.fromhex(token_uid))
        detailed_tokens.append({'uid': token_uid, 'name': token_info.name, 'symbol': token_info.symbol})

    serialized['tokens'] = detailed_tokens

    return {
        'success': True,
        'tx': serialized,
        'meta': meta.to_json(),
        'spent_outputs': spent_outputs,
    }


@register_resource
class TransactionResource(resource.Resource):
    """ Implements a web server API to return the tx.

    You must run with option `--status <PORT>`.
    """
    isLeaf = True

    def __init__(self, manager):
        # Important to have the manager so we can know the tx_storage
        self.manager = manager

    def render_GET(self, request):
        """ Get request /transaction/ that returns list of tx or a single one

            If receive 'id' (hash) as GET parameter we return the tx with this hash
            Else we return a list of tx. We expect 'type' and 'count' as parameters in this case

            'type': 'block' or 'tx', to indicate if we should return a list of blocks or tx
            'count': int, to indicate the quantity of elements we should return
            'hash': string, the hash reference we are in the pagination
            'page': 'previous' or 'next', to indicate if the user wants after or before the hash reference

            :rtype: string (json)
        """
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        set_cors(request, 'GET')

        if b'id' in request.args:
            # Get one tx
            data = self.get_one_tx(request)
        else:
            # Get all tx
            data = self.get_list_tx(request)

        return json.dumps(data, indent=4).encode('utf-8')

    def get_one_tx(self, request):
        """ Get 'id' (hash) from request.args
            Returns the tx with this hash or {'success': False} if hash is invalid or tx does not exist
        """
        if not self.manager.tx_storage.tokens_index:
            request.setResponseCode(503)
            return {'success': False}

        requested_hash = request.args[b'id'][0].decode('utf-8')
        success, message = validate_tx_hash(requested_hash, self.manager.tx_storage)
        if not success:
            data = {'success': False, 'message': message}
        else:
            hash_bytes = bytes.fromhex(requested_hash)
            tx = self.manager.tx_storage.get_transaction(hash_bytes)
            tx.storage = self.manager.tx_storage
            data = get_tx_extra_data(tx)

        return data

    def get_list_tx(self, request):
        """ Get parameter from request.args and return list of blocks/txs

            'type': 'block' or 'tx', to indicate if we should return a list of blocks or tx
            'count': int, to indicate the quantity of elements we should return
            'hash': string, the hash reference we are in the pagination
            'timestamp': int, the timestamp reference we are in the pagination
            'page': 'previous' or 'next', to indicate if the user wants after or before the hash reference
        """
        try:
            count = min(int(request.args[b'count'][0]), settings.MAX_TX_COUNT)
        except ValueError:
            return {'success': False, 'message': 'Invalid \'count\' parameter, expected an integer'}

        try:
            type_tx = request.args[b'type'][0].decode('utf-8')
        except KeyError:
            return {'success': False, 'message': 'Missing \'type\' parameter'}
        if type_tx != 'tx' and type_tx != 'block':
            return {'success': False, 'message': 'Invalid \'type\' parameter, expected \'block\' or \'tx\''}

        ref_hash = None
        page = ''
        if b'hash' in request.args:
            ref_hash = request.args[b'hash'][0].decode('utf-8')

            try:
                ref_timestamp = int(request.args[b'timestamp'][0].decode('utf-8'))
            except KeyError:
                return {'success': False, 'message': 'Missing \'timestamp\' parameter'}
            except ValueError:
                return {'success': False, 'message': 'Invalid \'timestamp\' parameter, expected an integer'}

            try:
                page = request.args[b'page'][0].decode('utf-8')
            except KeyError:
                return {'success': False, 'message': 'Missing \'page\' parameter'}
            if page != 'previous' and page != 'next':
                return {'success': False, 'message': 'Invalid \'page\' parameter, expected \'previous\' or \'next\''}

            if type_tx == 'block':
                if page == 'previous':
                    elements, has_more = self.manager.tx_storage.get_newer_blocks_after(
                        ref_timestamp, bytes.fromhex(ref_hash), count)
                else:
                    elements, has_more = self.manager.tx_storage.get_older_blocks_after(
                        ref_timestamp, bytes.fromhex(ref_hash), count)

            else:
                if page == 'previous':
                    elements, has_more = self.manager.tx_storage.get_newer_txs_after(
                        ref_timestamp, bytes.fromhex(ref_hash), count)
                else:
                    elements, has_more = self.manager.tx_storage.get_older_txs_after(
                        ref_timestamp, bytes.fromhex(ref_hash), count)
        else:
            if type_tx == 'block':
                elements, has_more = self.manager.tx_storage.get_newest_blocks(count=count)
            else:
                elements, has_more = self.manager.tx_storage.get_newest_txs(count=count)

        serialized = [element.to_json_extended() for element in elements]

        data = {'transactions': serialized, 'has_more': has_more}
        return data


TransactionResource.openapi = {
    '/transaction': {
        'x-visibility': 'public',
        'x-rate-limit': {
            'global': [
                {
                    'rate': '50r/s',
                    'burst': 100,
                    'delay': 50
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
            'tags': ['transaction'],
            'operationId': 'transaction',
            'summary': 'Transaction or list of transactions/blocks',
            'description': ('Returns a transaction by hash or a list of transactions/blocks depending on the '
                            'parameters sent. If "id" is sent as parameter, we return only one transaction, '
                            'else we return a list. In the list return we have a key "has_more" that indicates'
                            'if there are more transactions/blocks to be fetched'),
            'parameters': [
                {
                    'name': 'id',
                    'in': 'query',
                    'description': 'Hash in hex of the transaction/block',
                    'required': False,
                    'schema': {
                        'type': 'string'
                    }
                },
                {
                    'name': 'type',
                    'in': 'query',
                    'description': 'Type of list to return (block or tx)',
                    'required': False,
                    'schema': {
                        'type': 'string'
                    }
                },
                {
                    'name': 'count',
                    'in': 'query',
                    'description': 'Quantity of elements to return',
                    'required': False,
                    'schema': {
                        'type': 'int'
                    }
                },
                {
                    'name': 'page',
                    'in': 'query',
                    'description': 'If the user clicked "previous" or "next" button',
                    'required': False,
                    'schema': {
                        'type': 'string'
                    }
                },
                {
                    'name': 'hash',
                    'in': 'query',
                    'description': 'Hash reference for the pagination',
                    'required': False,
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
                                    'summary': 'One success',
                                    'value': {
                                        'tx': {
                                            'hash': '00002b3be4e3876e67b5e090d76dcd71cde1a30ca1e54e38d65717ba131cd22f',
                                            'nonce': 17076,
                                            'timestamp': 1539271482,
                                            'version': 1,
                                            'weight': 14.0,
                                            'parents': [],
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
                                            'outputs': [],
                                            'tokens': []
                                        },
                                        'meta': {
                                            'hash': '00002b3be4e3876e67b5e090d76dcd71cde1a30ca1e54e38d65717ba131cd22f',
                                            'spent_outputs': [
                                                ['0', [
                                                    '00002b3be4e3876e67b5e090d76dcd71cde1a30ca1e54e38d65717ba131cd22e'
                                                ]],
                                                ['1', [
                                                    '00002b3ce4e3876e67b5e090d76dcd71cde1a30ca1e54e38d65717ba131cd22e'
                                                ]]
                                            ],
                                            'received_by': [],
                                            'children': [
                                                '00002b3ee4e3876e67b5e090d76dcd71cde1a30ca1e54e38d65717ba131cd22d'
                                            ],
                                            'conflict_with': [],
                                            'voided_by': [],
                                            'twins': [],
                                            'accumulated_weight': 10,
                                            'score': 12,
                                            'first_block': None
                                        },
                                        'spent_outputs': {
                                            0: '00002b3ce4e3876e67b5e090d76dcd71cde1a30ca1e54e38d65717ba131cd22e'
                                        },
                                        'success': True
                                    }
                                },
                                'error': {
                                    'summary': 'Transaction not found',
                                    'value': {
                                        'success': False,
                                        'message': 'Transaction not found'
                                    }
                                },
                                'success_list': {
                                    'summary': 'List success',
                                    'value': {
                                        'transactions': [
                                            {
                                                'tx_id': ('00000257054251161adff5899a451ae9'
                                                          '74ac62ca44a7a31179eec5750b0ea406'),
                                                'nonce': 99579,
                                                'timestamp': 1547163030,
                                                'version': 1,
                                                'weight': 18.861583646228,
                                                'parents': [
                                                    '00000b8792cb13e8adb51cc7d866541fc29b532e8dec95ae4661cf3da4d42cb4',
                                                    '00001417652b9d7bd53eb14267834eab08f27e5cbfaca45a24370e79e0348bb9'
                                                ],
                                                'inputs': [
                                                    {
                                                        'tx_id': ('0000088c5a4dfcef7fd3c04a5b1eccfd'
                                                                  '2de032b23749deff871b0a090000f5f6'),
                                                        'index': 1,
                                                        'data': ('RzBFAiEAvv17vp8XyHYq36PFlOGd7V2vzIkf+XIuqfyUnc2fZugC'
                                                                 'IDnwM7PdkA/qwt2QXLB3WnegtdOqV8gv+H63voWVbsScIQPqg7y2'
                                                                 'RanTdnQcDvFneIzjrUzJoPzkmoNStoN8XtLTUA==')
                                                    },
                                                    {
                                                        'tx_id': ('0000003398322f99355f37439e32881c'
                                                                  '83ff08b83e744e799b1d6a67f73bee45'),
                                                        'index': 0,
                                                        'data': ('RzBFAiEAqPvD18Uzd6NsMVkGMaI9RsxWqLow22W1KBHUUW/35UEC'
                                                                 'IEUU9pxJEHBvXyEwYAB2/bCiWxNd4iLvyvQXGKaSaDV2IQPDL3iZ'
                                                                 'vsDS8jdFDmlcvc2Em/ZNYYDOBWd3oZWxpuA5DQ==')
                                                    }
                                                ],
                                                'outputs': [
                                                    {
                                                        'value': 1909,
                                                        'script': 'dqkUllFFDJByV5TjVUly3Zc3bB4mMH2IrA=='
                                                    },
                                                    {
                                                        'value': 55,
                                                        'script': 'dqkUjjPg+zwG6JDe901I0ybQxcAPrAuIrA=='
                                                    }
                                                ],
                                                'tokens': []
                                            },
                                            {
                                                'tx_id': ('00000b8792cb13e8adb51cc7d866541f'
                                                          'c29b532e8dec95ae4661cf3da4d42cb4'),
                                                'nonce': 119816,
                                                'timestamp': 1547163025,
                                                'version': 1,
                                                'weight': 17.995048894541107,
                                                'parents': [
                                                    '00001417652b9d7bd53eb14267834eab08f27e5cbfaca45a24370e79e0348bb9',
                                                    '0000088c5a4dfcef7fd3c04a5b1eccfd2de032b23749deff871b0a090000f5f6'
                                                ],
                                                'inputs': [
                                                    {
                                                        'tx_id': ('0000088c5a4dfcef7fd3c04a5b1eccfd'
                                                                  '2de032b23749deff871b0a090000f5f6'),
                                                        'index': 0,
                                                        'data': ('SDBGAiEA/rtsn1oQ68uGeTj/7IVtqijxoUxzr9S/u3UGAC7wQvU'
                                                                 'CIQDaYkL1R8LICfSCpYIn4xx6A+lxU0Fw3oKR1hK91fRnSiEDCo'
                                                                 'A74tfBQa4IR7iXtlz+jH9UV7+YthKX4yQNaMSMfb0=')
                                                    }
                                                ],
                                                'outputs': [
                                                    {
                                                        'value': 1894,
                                                        'script': 'dqkUduvtU77hZm++Pwavtl9OrOSA+XiIrA=='
                                                    },
                                                    {
                                                        'value': 84,
                                                        'script': 'dqkUjjPg+zwG6JDe901I0ybQxcAPrAuIrA=='
                                                    }
                                                ],
                                                'tokens': []
                                            }
                                        ],
                                        'has_more': True
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
