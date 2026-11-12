# syntax=docker/dockerfile:1
# Reproducible **isolated** ebusd source-build smoke test.
# Build from repository root:
#   docker build -f build/ebusd/Dockerfile -t vaillant-ebusd-source-test .
# No eBUS adapter is configured here, and the default command prints the version.
# This is not yet a Home Assistant add-on and does not start the heating controller.

FROM alpine:3.22 AS ebusd-build
RUN apk add --no-cache \
      ca-certificates git cmake ninja g++ musl-dev \
      mosquitto-dev openssl-dev

COPY build/ebusd-source.lock /usr/local/share/ebusd-source.lock
RUN set -eu; \
    . /usr/local/share/ebusd-source.lock; \
    test -n "$EBUSD_COMMIT"; \
    git clone --no-checkout "$EBUSD_REPO" /src/ebusd; \
    git -C /src/ebusd checkout --detach "$EBUSD_COMMIT"; \
    test "$(git -C /src/ebusd rev-parse HEAD)" = "$EBUSD_COMMIT"; \
    test "$(cat /src/ebusd/VERSION)" = "$EBUSD_SOURCE_VERSION"

RUN cmake -S /src/ebusd -B /build/ebusd -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr \
      -Dknx=OFF -Dmqtt=ON -Dssl=ON \
 && cmake --build /build/ebusd --parallel 2 \
 && cmake --install /build/ebusd \
 && /usr/bin/ebusd -V

FROM alpine:3.22 AS ebusd-smoke
RUN apk add --no-cache ca-certificates libstdc++ mosquitto-libs openssl
COPY --from=ebusd-build /usr/bin/ebusd /usr/bin/ebusd
COPY --from=ebusd-build /etc/ebusd/ /etc/ebusd/
COPY --from=ebusd-build /src/ebusd/LICENSE /usr/share/licenses/ebusd/LICENSE
COPY build/ebusd-source.lock /usr/local/share/ebusd-source.lock
ENTRYPOINT ["/usr/bin/ebusd"]
CMD ["-V"]
