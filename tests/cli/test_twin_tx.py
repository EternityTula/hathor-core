import json
import urllib.parse
from contextlib import redirect_stdout
from io import StringIO

from hathor.cli.mining import create_parser as create_parser_mining, execute as execute_mining
from hathor.cli.twin_tx import create_parser, execute
from hathor.cli.tx_generator import create_parser as create_parser_tx, execute as execute_tx
from hathor.transaction import Transaction, TransactionMetadata
from tests import unittest
from tests.utils import add_new_blocks, add_new_transactions, request_server, run_server


def prepare_transactions(host):
    # Unlock wallet to start mining
    request_server('wallet/unlock', 'POST', data={'passphrase': '123'})

    # Mining
    parser_mining = create_parser_mining()
    args = parser_mining.parse_args([urllib.parse.urljoin(host, 'mining'), '--count', '2'])
    execute_mining(args)

    # Generating txs
    parser_tx = create_parser_tx()
    args = parser_tx.parse_args([host, '--count', '4'])
    execute_tx(args)


class TwinTxTest(unittest.TestCase):
    def setUp(self):
        super().setUp()

        self.network = 'testnet'
        self.manager = self.create_peer(self.network, unlock_wallet=True)

        add_new_blocks(self.manager, 1)
        self.tx = add_new_transactions(self.manager, 1, advance_clock=1)[0]

        self.parser = create_parser()

    def test_twin(self):
        # Normal twin
        params = ['--raw_tx', self.tx.get_struct().hex()]
        args = self.parser.parse_args(params)

        f = StringIO()
        with redirect_stdout(f):
            execute(args)

        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        twin_tx = Transaction.create_from_struct(bytes.fromhex(output[0]))
        # Parents are the same but in different order
        self.assertEqual(twin_tx.parents[0], self.tx.parents[1])
        self.assertEqual(twin_tx.parents[1], self.tx.parents[0])

        # Testing metadata creation from json
        meta_before_conflict = self.tx.get_metadata()
        meta_before_conflict_json = meta_before_conflict.to_json()
        del meta_before_conflict_json['conflict_with']
        del meta_before_conflict_json['voided_by']
        del meta_before_conflict_json['twins']
        new_meta = TransactionMetadata.create_from_json(meta_before_conflict_json)
        self.assertEqual(meta_before_conflict, new_meta)

        self.manager.propagate_tx(twin_tx)

        # Validate they are twins
        meta = self.tx.get_metadata(force_reload=True)
        self.assertEqual(meta.twins, [twin_tx.hash])

        meta2 = twin_tx.get_metadata()
        self.assertFalse(meta == meta2)

    def test_twin_different(self):
        # Running with ssl just to test listening tcp with TLS factory
        server = run_server(listen_ssl=True)

        host = 'http://localhost:8085'
        prepare_transactions(host)

        response = request_server('transaction', 'GET', data={b'count': 4, b'type': 'tx'})
        tx = response['transactions'][-1]

        response = request_server('transaction', 'GET', data={b'id': tx['tx_id']})
        tx = response['tx']

        # Twin different weight and parents
        params = ['--url', host, '--hash', tx['hash'], '--parents', '--weight', '14']
        args = self.parser.parse_args(params)

        f = StringIO()
        with redirect_stdout(f):
            execute(args)

        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        twin_tx = Transaction.create_from_struct(bytes.fromhex(output[0]))
        # Parents are differents
        self.assertNotEqual(twin_tx.parents[0], tx['parents'][0])
        self.assertNotEqual(twin_tx.parents[0], tx['parents'][1])
        self.assertNotEqual(twin_tx.parents[1], tx['parents'][0])
        self.assertNotEqual(twin_tx.parents[1], tx['parents'][1])

        self.assertNotEqual(twin_tx.weight, tx['weight'])
        self.assertEqual(twin_tx.weight, 14.0)

        server.terminate()

    def test_twin_human(self):
        # Twin in human form
        params = ['--raw_tx', self.tx.get_struct().hex(), '--human']
        args = self.parser.parse_args(params)

        f = StringIO()
        with redirect_stdout(f):
            execute(args)

        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        human = output[0].replace("'", '"')
        tx_data = json.loads(human)

        self.assertTrue(isinstance(tx_data, dict))
        self.assertTrue('hash' in tx_data)
        self.assertTrue('timestamp' in tx_data)

        self.assertEqual(tx_data['parents'][0], self.tx.parents[1].hex())
        self.assertEqual(tx_data['parents'][1], self.tx.parents[0].hex())
        self.assertEqual(tx_data['weight'], self.tx.weight)

    def test_struct_error(self):
        # Struct error
        tx_hex = self.tx.get_struct().hex()
        params = ['--raw_tx', tx_hex + 'aa']
        args = self.parser.parse_args(params)

        f = StringIO()
        with redirect_stdout(f):
            execute(args)

        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        self.assertEqual('Error getting transaction from bytes', output[0])

    def test_parameter_error(self):
        # Parameter error
        args = self.parser.parse_args([])

        f = StringIO()
        with redirect_stdout(f):
            execute(args)

        # Transforming prints str in array
        output = f.getvalue().split('\n')
        # Last element is always empty string
        output.pop()

        self.assertEqual('The command expects raw_tx or hash and url as parameters', output[0])
