# Enable Security

By default, disco accepts unsigned broadcast messages from any node. With security enabled, each node signs its announcements with HMAC-SHA256. Nodes only accept messages from peers whose public keys appear in their trusted list.

## Generate a key pair on each node

On each node that will participate in signed messaging:

```bash
sudo disco key generate /etc/disco/keys.json
```

Output:

```
Keys generated and saved to /etc/disco/keys.json
Public Key: a1b2c3d4...   (64 hex chars)
Private Key: e5f6a7b8...  (64 hex chars)

Share the public key with peers you want to trust.
Keep the private key secret!
```

Copy the public key — you need to distribute it to all other nodes.

## Exchange public keys

On each node, add the public key of every other node it should trust:

```bash
sudo disco key add-trusted <peer-public-key> /etc/disco/keys.json
```

Repeat for each peer. To check the current trust list:

```bash
disco key show /etc/disco/keys.json
```

## Enable security in the config

In `/etc/disco/config.yaml` on each node:

```yaml
security:
  enabled: true
  key_path: /etc/disco/keys.json
  require_signed: true
```

Setting `require_signed: true` drops any unsigned or unverifiable message. Set it to `false` during a rolling migration — nodes will accept both signed and unsigned messages.

## Restart the daemon

```bash
sudo systemctl restart disco-daemon
```

## Verify

Watch live broadcast messages and confirm they carry a `[verified]` tag:

```bash
disco listen --key-file /etc/disco/keys.json
```

Messages from trusted peers appear with `[verified]`. Messages from nodes not in the trust list appear with `[signed]` (present but unverifiable with your keys) or with no tag (unsigned).

To drop unsigned messages at the listener level for testing:

```bash
disco listen --key-file /etc/disco/keys.json --require-signed
```

## Replay protection

Messages include a timestamp. The daemon rejects messages with a timestamp more than 5 minutes old, which prevents replaying captured announcements.
