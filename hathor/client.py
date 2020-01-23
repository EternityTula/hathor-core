from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import urljoin

import requests

from hathor.transaction import Block

# TODO: make this client async with twisted, instead of using `requests`


class IHathorClient(ABC):
    @abstractmethod
    def version(self) -> Tuple[int, int, int]:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_block_template(self, address: Optional[str] = None, merged_mining: bool = False) -> Block:
        raise NotImplementedError

    @abstractmethod
    def submit_block(self, block: Block) -> bool:
        raise NotImplementedError


class HathorClient(IHathorClient):
    def __init__(self, server_url, api_version='v1a'):
        server_url = server_url.rstrip('/') + '/'
        if not (server_url.startswith('http://') or server_url.startswith('https://')):
            server_url = 'http://' + server_url
        self.base_url = urljoin(server_url, api_version).rstrip('/') + '/'

    def _get_url(self, url: str) -> str:
        return urljoin(self.base_url, url.lstrip('/'))

    def version(self) -> Tuple[int, int, int]:
        data = requests.get(self._get_url('version')).json()
        ver = data['version']
        major, minor, patch = ver.split('.')
        return (int(major), int(minor), int(patch))

    def status(self) -> Dict[str, Any]:
        return requests.get(self._get_url('status')).json()

    def get_block_template(self, address: Optional[str] = None, merged_mining: bool = False) -> Block:
        from hathor.transaction.resources.mining import Capabilities
        from hathor.transaction.base_transaction import BaseTransaction

        params: Dict[str, Any] = {}
        if address is not None:
            params['address'] = address
        caps: Set[Capabilities] = set()
        if merged_mining:
            caps.add(Capabilities.MERGED_MINING)
        if caps:
            params['capabilities'] = [c.value for c in caps]

        data = requests.get(self._get_url('get_block_template'), params=params).json()
        block = BaseTransaction.create_from_dict(data)
        assert isinstance(block, Block)
        return block

    def submit_block(self, block: Block) -> bool:
        data = {
            'hexdata': bytes(block).hex(),
        }
        return requests.post(self._get_url('submit_block'), json=data).json()['result']
