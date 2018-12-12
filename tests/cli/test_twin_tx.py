from tests import unittest
from tests.utils import add_new_blocks, add_new_transactions
from twisted.internet.task import Clock
from hathor.transaction import Transaction

from hathor.cli.twin_tx import create_parser, execute

import time
import ast

from io import StringIO
from contextlib import redirect_stdout


class TwinTxTest(unittest.TestCase):
    def setUp(self):
        super().setUp()

        self.clock = Clock()
        self.clock.advance(time.time())
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

        self.manager.propagate_tx(twin_tx)

        # Validate they are twins
        meta = self.tx.get_metadata()
        self.assertEqual(meta.twins, set([twin_tx.hash]))

    def test_twin_different_weight(self):
        # Twin different weight
        params = ['--raw_tx', self.tx.get_struct().hex(), '--weight', '4']
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

        self.assertNotEqual(twin_tx.weight, self.tx.weight)
        self.assertEqual(twin_tx.weight, 4.0)

        self.manager.propagate_tx(twin_tx)

        # Validate they are twins
        meta = self.tx.get_metadata()
        self.assertEqual(meta.twins, set([twin_tx.hash]))

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

        tx_data = ast.literal_eval(output[0])

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
