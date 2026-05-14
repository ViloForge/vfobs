# vfobs-sdk-python

Typed Python SDK for the [vfobs](https://github.com/viloforge/vfobs)
v1 API. Per NFR5 (SDK-as-boundary), this is the **only** sanctioned
way for in-tree consumers (vafi controllers, vfobs CLI, future
operator tools) to talk to vfobs — raw HTTP clients are not allowed.

Released atomically with the service in v1; see the parent repo for
release lifecycle. If decoupling is ever needed, this subdirectory
lifts out cleanly via `git filter-repo`.

## Install (dev)

```bash
pip install -e '.[dev]'
```
