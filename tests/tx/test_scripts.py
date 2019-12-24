import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from hathor.crypto.util import get_address_from_public_key, get_hash160, get_public_key_bytes_compressed
from hathor.transaction.exceptions import (
    DataIndexError,
    EqualVerifyFailed,
    InvalidStackData,
    MissingStackItems,
    OracleChecksigFailed,
    OutOfData,
    ScriptError,
    TimeLocked,
    VerifyFailed,
)
from hathor.transaction.genesis import get_genesis_transactions
from hathor.transaction.scripts import (
    P2PKH,
    HathorScript,
    Opcode,
    ScriptExtras,
    get_data_value,
    op_checkdatasig,
    op_checkmultisig,
    op_checksig,
    op_data_greaterthan,
    op_data_match_interval,
    op_data_match_value,
    op_data_strequal,
    op_dup,
    op_equal,
    op_equalverify,
    op_find_p2pkh,
    op_greaterthan_timestamp,
    op_hash160,
    op_integer,
    op_pushdata,
    op_pushdata1,
    re_compile,
)
from hathor.wallet import HDWallet
from tests import unittest
from tests.utils import get_genesis_key


class BasicTransaction(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.genesis_blocks = [tx for tx in get_genesis_transactions(None) if tx.is_block]
        self.genesis_txs = [tx for tx in get_genesis_transactions(None) if not tx.is_block]

        # read genesis keys
        self.genesis_private_key = get_genesis_key()
        self.genesis_public_key = self.genesis_private_key.public_key()

    def test_data_pattern(self):
        # up to 75 bytes, no Opcode is needed
        s = HathorScript()
        re_match = re_compile('^DATA_75$')
        data = [0x00] * 75
        s.pushData(bytes(data))
        self.assertEqual(76, len(s.data))   # data_len + data
        match = re_match.search(s.data)
        self.assertIsNotNone(match)
        # test with PUSHDATA1 opcode. Should fail
        match = re_match.search(bytes(Opcode.OP_PUSHDATA1) + s.data)
        self.assertIsNone(match)

        # with more, use OP_PUSHDATA1
        s = HathorScript()
        re_match = re_compile('^DATA_76$')
        data = [0x00] * 76
        s.pushData(bytes(data))
        self.assertEqual(78, len(s.data))   # OP_PUSHDATA1 + data_len + data
        match = re_match.search(s.data)
        self.assertIsNotNone(match)
        # test without PUSHDATA1 opcode. Should fail
        match = re_match.search(s.data[1:])
        self.assertIsNone(match)

    def test_pushdata(self):
        stack = []
        random_bytes = b'a' * 50
        s = HathorScript()
        s.pushData(random_bytes)

        op_pushdata(0, s.data, stack)

        self.assertEqual(random_bytes, stack.pop())

        with self.assertRaises(OutOfData):
            op_pushdata(0, s.data[:-1], stack)

    def test_pushdata1(self):
        stack = []
        random_bytes = b'a' * 100
        s = HathorScript()
        s.pushData(random_bytes)

        op_pushdata1(0, s.data, stack)

        self.assertEqual(random_bytes, stack.pop())

        with self.assertRaises(OutOfData):
            op_pushdata1(0, s.data[:1], stack)
        with self.assertRaises(OutOfData):
            op_pushdata1(0, s.data[:-1], stack)

    def test_dup(self):
        with self.assertRaises(MissingStackItems):
            op_dup([], log=[], extras=None)

        stack = [1]
        op_dup(stack, log=[], extras=None)
        self.assertEqual(stack[-1], stack[-2])

    def test_equalverify(self):
        elem = b'a'
        with self.assertRaises(MissingStackItems):
            op_equalverify([elem], log=[], extras=None)

        # no exception should be raised
        op_equalverify([elem, elem], log=[], extras=None)

        with self.assertRaises(EqualVerifyFailed):
            op_equalverify([elem, b'aaaa'], log=[], extras=None)

    def test_checksig(self):
        with self.assertRaises(MissingStackItems):
            op_checksig([1], log=[], extras=None)

        block = self.genesis_blocks[0]

        from hathor.transaction import Transaction, TxInput, TxOutput
        txin = TxInput(tx_id=block.hash, index=0, data=b'')
        txout = TxOutput(value=block.outputs[0].value, script=b'')
        tx = Transaction(inputs=[txin], outputs=[txout])

        import hashlib
        data_to_sign = tx.get_sighash_all()
        hashed_data = hashlib.sha256(data_to_sign).digest()
        signature = self.genesis_private_key.sign(hashed_data, ec.ECDSA(hashes.SHA256()))
        pubkey_bytes = get_public_key_bytes_compressed(self.genesis_public_key)

        extras = ScriptExtras(tx=tx, txin=None, spent_tx=None)

        # wrong signature puts False (0) on stack
        stack = [b'aaaaaaaaa', pubkey_bytes]
        op_checksig(stack, log=[], extras=extras)
        self.assertEqual(0, stack.pop())

        stack = [signature, pubkey_bytes]
        op_checksig(stack, log=[], extras=extras)
        self.assertEqual(1, stack.pop())

    def test_hash160(self):
        with self.assertRaises(MissingStackItems):
            op_hash160([], log=[], extras=None)

        elem = b'aaaaaaaa'
        hash160 = get_hash160(elem)
        stack = [elem]
        op_hash160(stack, log=[], extras=None)
        self.assertEqual(hash160, stack.pop())

    def test_checkdatasig(self):
        with self.assertRaises(MissingStackItems):
            op_checkdatasig([1, 1], log=[], extras=None)

        data = b'some_random_data'
        signature = self.genesis_private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        pubkey_bytes = get_public_key_bytes_compressed(self.genesis_public_key)

        stack = [data, signature, pubkey_bytes]
        # no exception should be raised and data is left on stack
        op_checkdatasig(stack, log=[], extras=None)
        self.assertEqual(data, stack.pop())

        stack = [b'data_not_matching', signature, pubkey_bytes]
        with self.assertRaises(OracleChecksigFailed):
            op_checkdatasig(stack, log=[], extras=None)

    def test_get_data_value(self):
        value0 = b'value0'
        value1 = b'vvvalue1'
        value2 = b'vvvvvalue2'

        data = (bytes([len(value0)]) + value0 + bytes([len(value1)]) + value1 + bytes([len(value2)]) + value2)

        self.assertEqual(get_data_value(0, data), value0)
        self.assertEqual(get_data_value(1, data), value1)
        self.assertEqual(get_data_value(2, data), value2)

        with self.assertRaises(DataIndexError):
            get_data_value(5, data)

        with self.assertRaises(OutOfData):
            get_data_value(2, data[:-1])

    def test_data_strequal(self):
        with self.assertRaises(MissingStackItems):
            op_data_strequal([1, 1], log=[], extras=None)

        value0 = b'value0'
        value1 = b'vvvalue1'
        value2 = b'vvvvvalue2'

        data = (bytes([len(value0)]) + value0 + bytes([len(value1)]) + value1 + bytes([len(value2)]) + value2)

        stack = [data, 0, value0]
        op_data_strequal(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), data)

        stack = [data, 1, value0]
        with self.assertRaises(VerifyFailed):
            op_data_strequal(stack, log=[], extras=None)

        stack = [data, b'\x00', value0]
        with self.assertRaises(VerifyFailed):
            op_data_strequal(stack, log=[], extras=None)

    def test_data_greaterthan(self):
        with self.assertRaises(MissingStackItems):
            op_data_greaterthan([1, 1], log=[], extras=None)

        value0 = struct.pack('!I', 1000)
        value1 = struct.pack('!I', 1)

        data = (bytes([len(value0)]) + value0 + bytes([len(value1)]) + value1)

        stack = [data, 0, struct.pack('!I', 999)]
        op_data_greaterthan(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), data)

        stack = [data, 1, struct.pack('!I', 0)]
        op_data_greaterthan(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), data)

        with self.assertRaises(VerifyFailed):
            stack = [data, 1, struct.pack('!I', 1)]
            op_data_greaterthan(stack, log=[], extras=None)

        stack = [data, 1, b'not_an_int']
        with self.assertRaises(VerifyFailed):
            op_data_greaterthan(stack, log=[], extras=None)

        stack = [data, b'\x00', struct.pack('!I', 0)]
        with self.assertRaises(VerifyFailed):
            op_data_greaterthan(stack, log=[], extras=None)

    def test_data_match_interval(self):
        with self.assertRaises(MissingStackItems):
            op_data_match_interval([1, b'2'], log=[], extras=None)

        value0 = struct.pack('!I', 1000)
        data = (bytes([len(value0)]) + value0)

        stack = [data, 0, 'key1', struct.pack('!I', 1000), 'key2', struct.pack('!I', 1005), 'key3', bytes([2])]
        op_data_match_interval(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 'key1')
        self.assertEqual(len(stack), 0)

        stack = [data, 0, 'key1', struct.pack('!I', 100), 'key2', struct.pack('!I', 1005), 'key3', bytes([2])]
        op_data_match_interval(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 'key2')
        self.assertEqual(len(stack), 0)

        stack = [data, 0, 'key1', struct.pack('!I', 100), 'key2', struct.pack('!I', 900), 'key3', bytes([2])]
        op_data_match_interval(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 'key3')
        self.assertEqual(len(stack), 0)

        # missing 1 item on stack
        stack = [data, 0, struct.pack('!I', 100), 'key2', struct.pack('!I', 900), 'key3', bytes([2])]
        with self.assertRaises(MissingStackItems):
            op_data_match_interval(stack, log=[], extras=None)

        # value should be an integer
        stack = [data, 0, 'key1', struct.pack('!I', 100), 'key2', b'not_an_int', 'key3', bytes([2])]
        with self.assertRaises(VerifyFailed):
            op_data_match_interval(stack, log=[], extras=None)

    def test_data_match_value(self):
        with self.assertRaises(MissingStackItems):
            op_data_match_value([1, b'2'], log=[], extras=None)

        value0 = struct.pack('!I', 1000)
        data = (bytes([len(value0)]) + value0)

        stack = [data, 0, 'key1', struct.pack('!I', 1000), 'key2', struct.pack('!I', 1005), 'key3', bytes([2])]
        op_data_match_value(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 'key2')
        self.assertEqual(len(stack), 0)

        stack = [data, 0, 'key1', struct.pack('!I', 999), 'key2', struct.pack('!I', 1000), 'key3', bytes([2])]
        op_data_match_value(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 'key3')
        self.assertEqual(len(stack), 0)

        # missing 1 item on stack
        stack = [data, 0, 'key1', struct.pack('!I', 1000), 'key2', struct.pack('!I', 1000), bytes([2])]
        with self.assertRaises(MissingStackItems):
            op_data_match_value(stack, log=[], extras=None)

        # no value matches
        stack = [data, 0, 'key1', struct.pack('!I', 999), 'key2', struct.pack('!I', 1111), 'key3', bytes([2])]
        op_data_match_value(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 'key1')
        self.assertEqual(len(stack), 0)

        # value should be an integer
        stack = [data, 0, 'key1', struct.pack('!I', 100), 'key2', b'not_an_int', 'key3', bytes([2])]
        with self.assertRaises(VerifyFailed):
            op_data_match_value(stack, log=[], extras=None)

    def test_find_p2pkh(self):
        with self.assertRaises(MissingStackItems):
            op_find_p2pkh([], log=[], extras=None)

        addr1 = '15d14K5jMqsN2uwUEFqiPG5SoD7Vr1BfnH'
        addr2 = '1K35zJQeYrVzQAW7X3s7vbPKmngj5JXTBc'
        addr3 = '1MnHN3D41yaMN5WLLKPARRdF77USvPLDfy'

        import base58
        out1 = P2PKH.create_output_script(base58.b58decode(addr1))
        out2 = P2PKH.create_output_script(base58.b58decode(addr2))
        out3 = P2PKH.create_output_script(base58.b58decode(addr3))

        # read genesis keys
        genesis_address = get_address_from_public_key(self.genesis_public_key)
        out_genesis = P2PKH.create_output_script(genesis_address)

        from hathor.transaction import Transaction, TxOutput, TxInput
        spent_tx = Transaction(outputs=[TxOutput(1, b'nano_contract_code')])
        txin = TxInput(b'dont_care', 0, b'data')

        # try with just 1 output
        stack = [genesis_address]
        tx = Transaction(outputs=[TxOutput(1, out_genesis)])
        extras = ScriptExtras(tx=tx, txin=txin, spent_tx=spent_tx)
        op_find_p2pkh(stack, log=[], extras=extras)
        self.assertEqual(stack.pop(), 1)

        # several outputs and correct output among them
        stack = [genesis_address]
        tx = Transaction(outputs=[TxOutput(1, out1), TxOutput(1, out2), TxOutput(1, out_genesis), TxOutput(1, out3)])
        extras = ScriptExtras(tx=tx, txin=txin, spent_tx=spent_tx)
        op_find_p2pkh(stack, log=[], extras=extras)
        self.assertEqual(stack.pop(), 1)

        # several outputs without correct amount output
        stack = [genesis_address]
        tx = Transaction(outputs=[TxOutput(1, out1), TxOutput(1, out2), TxOutput(2, out_genesis), TxOutput(1, out3)])
        extras = ScriptExtras(tx=tx, txin=txin, spent_tx=spent_tx)
        with self.assertRaises(VerifyFailed):
            op_find_p2pkh(stack, log=[], extras=extras)

        # several outputs without correct address output
        stack = [genesis_address]
        tx = Transaction(outputs=[TxOutput(1, out1), TxOutput(1, out2), TxOutput(1, out3)])
        extras = ScriptExtras(tx=tx, txin=txin, spent_tx=spent_tx)
        with self.assertRaises(VerifyFailed):
            op_find_p2pkh(stack, log=[], extras=extras)

    def test_greaterthan_timestamp(self):
        with self.assertRaises(MissingStackItems):
            op_greaterthan_timestamp([], log=[], extras=None)

        timestamp = 1234567

        from hathor.transaction import Transaction
        tx = Transaction()

        stack = [struct.pack('!I', timestamp)]
        extras = ScriptExtras(tx=tx, txin=None, spent_tx=None)

        with self.assertRaises(TimeLocked):
            tx.timestamp = timestamp - 1
            op_greaterthan_timestamp(list(stack), log=[], extras=extras)

        with self.assertRaises(TimeLocked):
            tx.timestamp = timestamp
            op_greaterthan_timestamp(list(stack), log=[], extras=extras)

        tx.timestamp = timestamp + 1
        op_greaterthan_timestamp(stack, log=[], extras=extras)
        self.assertEqual(len(stack), 0)

    def test_checkmultisig(self):
        with self.assertRaises(MissingStackItems):
            op_checkmultisig([], log=[], extras=None)

        block = [x for x in get_genesis_transactions(None) if x.is_block][0]

        from hathor.transaction import Transaction, TxInput, TxOutput
        txin = TxInput(tx_id=block.hash, index=0, data=b'')
        txout = TxOutput(value=block.outputs[0].value, script=b'')
        tx = Transaction(inputs=[txin], outputs=[txout])

        data_to_sign = tx.get_sighash_all()
        extras = ScriptExtras(tx=tx, txin=None, spent_tx=None)

        wallet = HDWallet()
        wallet._manually_initialize()
        wallet.words = wallet.mnemonic.generate()
        wallet._manually_initialize()

        keys_count = 3
        keys = []

        for i in range(keys_count):
            privkey = list(wallet.keys.values())[i]
            keys.append({
                'privkey': privkey,
                'pubkey': privkey.sec(),
                'signature': wallet.get_input_aux_data(data_to_sign, privkey)[1]
            })

        wrong_privkey = list(wallet.keys.values())[3]
        wrong_key = {
            'privkey': wrong_privkey,
            'pubkey': wrong_privkey.sec(),
            'signature': wallet.get_input_aux_data(data_to_sign, wrong_privkey)[1]
        }

        # All signatures match
        stack = [
            keys[0]['signature'], keys[2]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        op_checkmultisig(stack, log=[], extras=extras)
        self.assertEqual(1, stack.pop())

        # New set of valid signatures
        stack = [
            keys[0]['signature'], keys[1]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        op_checkmultisig(stack, log=[], extras=extras)
        self.assertEqual(1, stack.pop())

        # Changing the signatures but they match
        stack = [
            keys[1]['signature'], keys[2]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        op_checkmultisig(stack, log=[], extras=extras)
        self.assertEqual(1, stack.pop())

        # Signatures are valid but in wrong order
        stack = [
            keys[1]['signature'], keys[0]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        op_checkmultisig(stack, log=[], extras=extras)
        self.assertEqual(0, stack.pop())

        # Adding wrong signature, so we get error
        stack = [
            keys[0]['signature'], wrong_key['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        op_checkmultisig(stack, log=[], extras=extras)
        self.assertEqual(0, stack.pop())

        # Adding same signature twice, so we get error
        stack = [
            keys[0]['signature'], keys[0]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        op_checkmultisig(stack, log=[], extras=extras)
        self.assertEqual(0, stack.pop())

        # Adding less signatures than required, so we get error
        stack = [keys[0]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3]
        with self.assertRaises(MissingStackItems):
            op_checkmultisig(stack, log=[], extras=extras)

        # Quantity of signatures is more than it should
        stack = [
            keys[0]['signature'], keys[1]['signature'], 3, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3
        ]
        with self.assertRaises(MissingStackItems):
            op_checkmultisig(stack, log=[], extras=extras)

        # Quantity of pubkeys is more than it should
        stack = [
            keys[0]['signature'], keys[1]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 4
        ]
        with self.assertRaises(InvalidStackData):
            op_checkmultisig(stack, log=[], extras=extras)

        # Exception pubkey_count should be integer
        stack = [
            keys[0]['signature'], keys[1]['signature'], 2, keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], '3'
        ]
        with self.assertRaises(InvalidStackData):
            op_checkmultisig(stack, log=[], extras=extras)

        # Exception not enough pub keys
        stack = [keys[0]['pubkey'], keys[1]['pubkey'], 3]
        with self.assertRaises(MissingStackItems):
            op_checkmultisig(stack, log=[], extras=extras)

        # Exception stack empty after pubkeys
        stack = [keys[0]['pubkey'], keys[1]['pubkey'], keys[2]['pubkey'], 3]
        with self.assertRaises(MissingStackItems):
            op_checkmultisig(stack, log=[], extras=extras)

    def test_equal(self):
        elem = b'a'
        with self.assertRaises(MissingStackItems):
            op_equal([elem], log=[], extras=None)

        # no exception should be raised
        stack = [elem, elem]
        op_equal(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 1)

        stack = [elem, b'aaaa']
        op_equal(stack, log=[], extras=None)
        self.assertEqual(stack.pop(), 0)

    def test_integer_opcode(self):
        # We have opcodes from OP_0 to OP_16
        for i in range(0, 17):
            stack = []
            op_integer(getattr(Opcode, 'OP_{}'.format(i)), stack, [], None)
            self.assertEqual(stack, [i])

        stack = []
        with self.assertRaises(ScriptError):
            op_integer(0, stack, [], None)

        with self.assertRaises(ScriptError):
            op_integer(0x61, stack, [], None)


if __name__ == '__main__':
    unittest.main()
