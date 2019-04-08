# Mining Hathor

Unlike traditional cryptocurrencies, Hathor does not rely on blocks to include transactions on the network. However, we do use blocks for securing the DAG. You can read more about this [here](#add-link).

## Mining algorithm

Hathor uses classic Proof-of-Work (PoW) consensus, with the same algorithm as Bitcoin for mining blocks: sha256d. The `d` in the end stands for double, meaning that sha256 is done twice. In other words, sha256(sha256(data)).

## Software

Hathor nodes implement a customized [Stratum Protocol](https://en.bitcoin.it/wiki/Stratum_mining_protocol) server that enable miners to request jobs and receive updates. For further details of our customization, see [this document](TODO stratum RFC).

> **_NOTE:_**  Node owners can choose if they wish to run the stratum server or not. When connecting your miner to a node, make sure they have Stratum support enabled.

We have working forks of cpuminer and ccminer compatible with Hathor. For both, you need the hostname and port of a stratum server and a Hathor address to send the reward when you find a new block.

TODO add hathor address to cpuminer and ccminer command, possibly `-u {address}`

### cpuminer

Repo: TODO add link

Basic use is
```
./minerd -a sha256d -o stratum+tcp://{hostname}:{port}
```

You can choose the number of threads used by cpuminer with `-t`. If you omit this parameter, it will start as many threads as the number of cores in your machine.
```
./minerd -a sha256d -o stratum+tcp://{hostname}:{port} -t {num_threads}
```

Run `./minerd --help` to see all options.

### ccminer

Repo: TODO add link

Very similar to cpuminer. Basic use is
```
./ccminer -a sha256d -o stratum+tcp://{hostname}:{port}
```

Run `./ccminer --help` to see all options.

## Docker images

We've created Docker images to facilitate running our mining software.

## cpuminer

Docker hub: TODO add link

```
docker run TODO_CPUMINER_REPO -a sha256d -o stratum+tcp://{hostname}:{port}
```

## ccminer

Docker hub: TODO add link

> **_NOTE:_**  To enable GPU access in your containers, you need to run [nvidia-docker](https://github.com/NVIDIA/nvidia-docker) instead of the regular docker. Also make sure you have NVIDIA drivers installed in your machine. Read more information [here](https://github.com/nvidia/nvidia-docker/wiki/Installation-(version-2.0)).

```
docker run TODO_CPUMINER_REPO -a sha256d -o stratum+tcp://{hostname}:{port}
```
