import random
import shutil
import tempfile
import time

import numpy.random
from twisted.internet import reactor
from twisted.internet.task import Clock
from twisted.trial import unittest

from hathor.manager import HathorManager, TestMode
from hathor.p2p.peer_id import PeerId
from hathor.wallet import Wallet


class TestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdirs = []
        self.clock = Clock()
        self.clock.advance(time.time())
        # before patching genesis, validate the original ones are correct
        self._validate_real_genesis()
        self._patch_genesis_block()

    def _patch_genesis_block(self):
        """ Updates the genesis block so we can easily spend the outputs during tests. When we make any
        changes to tx structure that impacts the hash, we also must change it here (the nonce and hash).
        The steps for updating it are:
        1. use the genesis block (block = hathor.transaction.genesis.GENESIS[0])
        2. update the output script to use the one as bellow
        3. mine block again: block.start_mining(update_time=False)
        4. update hash: block.update_hash()
        5. replace block nonce and hash on this function with the new ones
        """
        import hathor.transaction.genesis
        from hathor.transaction import Block, Transaction
        block = hathor.transaction.genesis.GENESIS[0]
        self.assertIsInstance(block, Block)
        block.outputs[0].script = bytes.fromhex('76a914fd05059b6006249543b82f36876a17c73fd2267b88ac')
        block.resolve(update_time=False)
        block.nonce = 0
        block.update_hash()
        self.assertEqual(block.hash_hex, '6b338deb966e95471786e79b1c731638695e8ed0712736ed9b0ae83710f466fb')
        tx1 = hathor.transaction.genesis.GENESIS[1]
        self.assertIsInstance(tx1, Transaction)
        tx1.nonce = 0
        tx1.update_hash()
        self.assertEqual(tx1.hash_hex, '2a20321121a1dd805b75cf956673a840175076352742f52b7341a31a13404ea9')
        tx2 = hathor.transaction.genesis.GENESIS[2]
        self.assertIsInstance(tx2, Transaction)
        tx2.nonce = 5
        tx2.update_hash()
        self.assertEqual(tx2.hash_hex, '08b1a77129b2755a2dbdd4ea74a09b3bd3fa6c3b5c1abbbe95d5f69751928ed3')

    def tearDown(self):
        self.clean_tmpdirs()

    def _validate_real_genesis(self):
        import hathor.transaction.genesis
        for tx in hathor.transaction.genesis.GENESIS:
            self.assertEqual(tx.hash, tx.calculate_hash())
            tx.verify_without_storage()

    def _create_test_wallet(self):
        """ Generate a Wallet with a number of keypairs for testing
            :rtype: Wallet
        """
        tmpdir = tempfile.mkdtemp(dir='/tmp/')
        self.tmpdirs.append(tmpdir)

        wallet = Wallet(directory=tmpdir)
        wallet.unlock(b'MYPASS')
        wallet.generate_keys(count=20)
        wallet.lock()
        return wallet

    def create_peer(self, network, peer_id=None, wallet=None, tx_storage=None, unlock_wallet=True, wallet_index=False):
        if peer_id is None:
            peer_id = PeerId()
        if not wallet:
            wallet = self._create_test_wallet()
            if unlock_wallet:
                wallet.unlock(b'MYPASS')
        manager = HathorManager(
            self.clock,
            peer_id=peer_id,
            network=network,
            wallet=wallet,
            tx_storage=tx_storage,
            wallet_index=wallet_index
        )
        manager.avg_time_between_blocks = 0.0001
        manager.test_mode = TestMode.TEST_ALL_WEIGHT
        manager.start()
        self.run_to_completion()
        return manager

    def run_to_completion(self):
        """ This will advance the test's clock until all calls scheduled are done.
        """
        for call in self.clock.getDelayedCalls():
            amount = call.getTime() - self.clock.seconds()
            self.clock.advance(amount)

    def set_random_seed(self, seed=None):
        if seed is None:
            seed = numpy.random.randint(2**32)
        self.random_seed = seed
        random.seed(self.random_seed)
        numpy.random.seed(self.random_seed)

    def assertTipsEqual(self, manager1, manager2):
        s1 = set(manager1.tx_storage.get_all_tips())
        s2 = set(manager2.tx_storage.get_all_tips())
        self.assertEqual(s1, s2)

        s1 = set(manager1.tx_storage.get_tx_tips())
        s2 = set(manager2.tx_storage.get_tx_tips())
        self.assertEqual(s1, s2)

    def assertTipsNotEqual(self, manager1, manager2):
        s1 = set(manager1.tx_storage.get_all_tips())
        s2 = set(manager2.tx_storage.get_all_tips())
        self.assertNotEqual(s1, s2)

    def clean_tmpdirs(self):
        for tmpdir in self.tmpdirs:
            shutil.rmtree(tmpdir)

    def clean_pending(self, required_to_quiesce=True):
        """
        This handy method cleans all pending tasks from the reactor.

        When writing a unit test, consider the following question:

            Is the code that you are testing required to release control once it
            has done its job, so that it is impossible for it to later come around
            (with a delayed reactor task) and do anything further?

        If so, then trial will usefully test that for you -- if the code under
        test leaves any pending tasks on the reactor then trial will fail it.

        On the other hand, some code is *not* required to release control -- some
        code is allowed to continuously maintain control by rescheduling reactor
        tasks in order to do ongoing work.  Trial will incorrectly require that
        code to clean up all its tasks from the reactor.

        Most people think that such code should be amended to have an optional
        "shutdown" operation that releases all control, but on the contrary it is
        good design for some code to *not* have a shutdown operation, but instead
        to have a "crash-only" design in which it recovers from crash on startup.

        If the code under test is of the "long-running" kind, which is *not*
        required to shutdown cleanly in order to pass tests, then you can simply
        call testutil.clean_pending() at the end of the unit test, and trial will
        be satisfied.

        Copy from: https://github.com/zooko/pyutil/blob/master/pyutil/testutil.py#L68
        """
        pending = reactor.getDelayedCalls()
        active = bool(pending)
        for p in pending:
            if p.active():
                p.cancel()
            else:
                print('WEIRDNESS! pending timed call not active!')
        if required_to_quiesce and active:
            self.fail('Reactor was still active when it was required to be quiescent.')

    def get_address(self, index: int) -> str:
        """ Generate a fixed HD Wallet and return an address
        """
        from hathor.wallet import HDWallet
        words = ('bind daring above film health blush during tiny neck slight clown salmon '
                 'wine brown good setup later omit jaguar tourist rescue flip pet salute')

        hd = HDWallet(words=words)
        hd._manually_initialize()

        if index >= hd.gap_limit:
            return None

        return list(hd.keys.keys())[index]
