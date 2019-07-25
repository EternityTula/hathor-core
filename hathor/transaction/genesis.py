from typing import List, Optional

from hathor.conf import HathorSettings
from hathor.transaction import BaseTransaction, Block, Transaction, TxOutput
from hathor.transaction.storage import TransactionStorage

settings = HathorSettings()

GENESIS_OUTPUTS = [
    TxOutput(settings.GENESIS_TOKENS, settings.GENESIS_OUTPUT_SCRIPT),
]

BLOCK_GENESIS = Block(
    hash=bytes.fromhex('000007bd6da157b1b9fc119cc07c0a5248457acb6e5e0a4146ad86a2b2f5049f'),
    data=b'',
    nonce=1653984,
    timestamp=1560920000,
    weight=settings.MIN_BLOCK_WEIGHT,
    outputs=GENESIS_OUTPUTS,
)

TX_GENESIS1 = Transaction(
    hash=bytes.fromhex('00039c16436678585e2344e64d3a0a38ba6a20fcd2d3f57844f8530acff34755'),
    nonce=8932,
    timestamp=1560920001,
    weight=settings.MIN_TX_WEIGHT,
)

TX_GENESIS2 = Transaction(
    hash=bytes.fromhex('0001dbb0739130b719f7c4d2c77700eda5bc1895018056819e4395bbc5ffb59d'),
    nonce=8949,
    timestamp=1560920002,
    weight=settings.MIN_TX_WEIGHT,
)

GENESIS = [BLOCK_GENESIS, TX_GENESIS1, TX_GENESIS2]


def _get_genesis_hash() -> bytes:
    import hashlib
    h = hashlib.sha256()
    for tx in GENESIS:
        tx_hash = tx.hash
        assert tx_hash is not None
        h.update(tx_hash)
    return h.digest()


GENESIS_HASH = _get_genesis_hash()


def get_genesis_transactions(tx_storage: Optional[TransactionStorage]) -> List[BaseTransaction]:
    genesis = []
    for tx in GENESIS:
        tx2 = tx.clone()
        tx2.storage = tx_storage
        genesis.append(tx2)
    return genesis
