# Pinned ebusd source build

The combined Home Assistant app builds an ebusd binary from a **fixed public Git commit**, declared in `build/ebusd-source.lock`. The standalone smoke-test Dockerfile in this directory validates this source build without connecting to a heating system.

```sh
docker build -f build/ebusd/Dockerfile -t vaillant-ebusd-source-test .
docker run --rm --network none vaillant-ebusd-source-test
```

This does not validate physical device compatibility. See [licensing and upstream attribution](../../docs/LICENSES.md).
