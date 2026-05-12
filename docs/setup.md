# Quick Start Guide

Get your Nerve Local Communication Hub up and running in less than two minutes.

---

## Installation

Install the official Nerve package directly from PyPI:

```bash
pip install alenia-nerve
```

Note: On modern Linux distributions enforcing PEP 668 (externally managed environments, such as Ubuntu 24.04+ or Linux Mint 22+), append the `--break-system-packages` flag to register the global command safely:

```bash
pip install alenia-nerve --break-system-packages
```

---

## Starting the Hub

Once installed, spawn the Nerve communication broker globally from any terminal shell:

```bash
nerve start
```

### Console Output
You will see the Alenia Studios purple banner and the active routing socket:

```text
 _   _  _____ ______ _   _ _____ 
| \ | ||  ___|| ___ \ | | |  ___|
|  \| || |__  | |_/ / | | | |__  
| . ` ||  __| |    /| | | |  __| 
| |\  || |___ | |\ \ \_/ /| |___ 
\_| \_/\____/ \_| \_|\___/\____/ 
   Local Communication Engine v1.2.0

[NERVE CLI] Initializing Nerve Hub...
[NERVE] Hub active via Unix Socket at /tmp/nerve.sock
```

---

## Debugging with Verbose Mode

To audit raw JSON packages routing between your assets tools, start the server in detailed logging mode:

```bash
nerve start --verbose
```
(or simply use the `-v` flag).
