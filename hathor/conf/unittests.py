from hathor.conf.settings import HathorSettings

SETTINGS = HathorSettings(
    P2PKH_VERSION_BYTE=b'\x28',
    MULTISIG_VERSION_BYTE=b'\x64',
    NETWORK_NAME='unittests',
    BLOCKS_PER_HALVING=2 * 60,
    MIN_BLOCK_WEIGHT=1,
    MIN_TX_WEIGHT=1,
    MIN_SHARE_WEIGHT=1,
)
