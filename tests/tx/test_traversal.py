from math import inf

from hathor.transaction.storage.traversal import BFSWalk, DFSWalk
from tests import unittest
from tests.utils import add_new_blocks, add_new_transactions, add_new_tx


class _BaseTraversalTestCase:
    class _TraversalTestCase(unittest.TestCase):
        def setUp(self):
            super().setUp()

            self.manager = self.create_peer(network='testnet')

            self.hashes_before = set()
            for genesis in self.manager.tx_storage.get_all_genesis():
                self.hashes_before.add(genesis.hash)

            self.blocks_before = add_new_blocks(self.manager, 30)
            self.txs_before = add_new_transactions(self.manager, 5)
            for block in self.blocks_before:
                self.hashes_before.add(block.hash)
            for tx in self.txs_before:
                self.hashes_before.add(tx.hash)

            address = self.get_address(0)
            self.root_tx = add_new_tx(self.manager, address=address, value=100)

            self.blocks_after = add_new_blocks(self.manager, 3)
            self.txs_after = add_new_transactions(self.manager, 5)
            self.blocks_after.extend(add_new_blocks(self.manager, 3))

            self.hashes_after = set()
            for block in self.blocks_after:
                self.hashes_after.add(block.hash)
            for tx in self.txs_after:
                self.hashes_after.add(tx.hash)

        def _run_lr(self, walk, skip_root=True):
            raise NotImplementedError

        def _run_rl(self, walk):
            raise NotImplementedError

        def gen_walk(self, **kwargs):
            raise NotImplementedError

        def test_left_to_right(self):
            walk = self.gen_walk(is_dag_verifications=True, is_left_to_right=True)
            seen_v = self._run_lr(walk)
            self.assertEqual(len(seen_v.intersection(self.hashes_before)), 0)
            self.assertTrue(seen_v.issubset(self.hashes_after))

            walk = self.gen_walk(is_dag_funds=True, is_left_to_right=True)
            seen_f = self._run_lr(walk)
            self.assertEqual(len(seen_f.intersection(self.hashes_before)), 0)
            self.assertTrue(seen_f.issubset(self.hashes_after))

            walk = self.gen_walk(is_dag_verifications=True, is_dag_funds=True, is_left_to_right=True)
            seen_vf = self._run_lr(walk)
            self.assertEqual(len(seen_vf.intersection(self.hashes_before)), 0)
            self.assertTrue(seen_vf.issubset(self.hashes_after))

            self.assertNotEqual(seen_v, seen_f)
            self.assertTrue(seen_v.union(seen_f).issubset(seen_vf))

        def test_right_to_left(self):
            walk = self.gen_walk(is_dag_verifications=True, is_left_to_right=False)
            seen_v = self._run_rl(walk)
            self.assertEqual(len(seen_v.intersection(self.hashes_after)), 0)
            self.assertTrue(seen_v.issubset(self.hashes_before))

            walk = self.gen_walk(is_dag_funds=True, is_left_to_right=False)
            seen_f = self._run_rl(walk)
            self.assertEqual(len(seen_f.intersection(self.hashes_after)), 0)
            self.assertTrue(seen_f.issubset(self.hashes_before))

            walk = self.gen_walk(is_dag_verifications=True, is_dag_funds=True, is_left_to_right=False)
            seen_vf = self._run_rl(walk)
            self.assertEqual(len(seen_vf.intersection(self.hashes_after)), 0)
            self.assertTrue(seen_vf.issubset(self.hashes_before))

            self.assertNotEqual(seen_v, seen_f)
            self.assertTrue(seen_v.union(seen_f).issubset(seen_vf))


class BFSWalkTestCase(_BaseTraversalTestCase._TraversalTestCase):
    def gen_walk(self, **kwargs):
        return BFSWalk(self.manager.tx_storage, **kwargs)

    def _run_lr(self, walk, skip_root=True):
        seen = set()
        last_timestamp = 0
        for tx in walk.run(self.root_tx, skip_root=skip_root):
            seen.add(tx.hash)
            self.assertGreaterEqual(tx.timestamp, last_timestamp)
            last_timestamp = tx.timestamp
        return seen

    def _run_rl(self, walk):
        seen = set()
        last_timestamp = inf
        for tx in walk.run(self.root_tx, skip_root=True):
            seen.add(tx.hash)
            self.assertLessEqual(tx.timestamp, last_timestamp)
            last_timestamp = tx.timestamp
        return seen


class DFSWalkTestCase(_BaseTraversalTestCase._TraversalTestCase):
    def gen_walk(self, **kwargs):
        return DFSWalk(self.manager.tx_storage, **kwargs)

    def _run_lr(self, walk, skip_root=True):
        seen = set()
        for tx in walk.run(self.root_tx, skip_root=skip_root):
            seen.add(tx.hash)
        return seen

    def _run_rl(self, walk):
        seen = set()
        for tx in walk.run(self.root_tx, skip_root=True):
            seen.add(tx.hash)
        return seen


if __name__ == '__main__':
    unittest.main()
