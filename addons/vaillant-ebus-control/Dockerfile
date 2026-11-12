# syntax=docker/dockerfile:1
# Source of truth: build/ebusd-source.lock (must match SHA below, CI checks this).
FROM alpine:3.24 AS ebusd-build
RUN apk add --no-cache ca-certificates git cmake ninja g++ musl-dev mosquitto-dev openssl-dev
ARG EBUSD_COMMIT=38db2d28bd5622cadb6078c1662c6f7da5cef891
RUN git clone https://github.com/Alec-99/ebusd.git /src/ebusd \
    && cd /src/ebusd \
    && git checkout --detach "${EBUSD_COMMIT}" \
    && test "$(git rev-parse HEAD)" = "${EBUSD_COMMIT}" \
    && test "$(cat VERSION)" = '26.1'
RUN cmake -S /src/ebusd -B /build -G Ninja -Dknx=OFF -Dcontrib=OFF -Dmqtt=ON -Dssl=ON -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --target ebusd --parallel 2 \
    && /build/src/ebusd/ebusd -V

FROM ghcr.io/home-assistant/base:3.24
RUN apk add --no-cache python3 py3-pip libstdc++ mosquitto-libs openssl ca-certificates \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir paho-mqtt==2.1.0
ENV PATH="/opt/venv/bin:${PATH}" PYTHONPATH="/opt/vaillant"
COPY --from=ebusd-build /build/src/ebusd/ebusd /usr/local/bin/ebusd
COPY --from=ebusd-build /src/ebusd/LICENSE /usr/share/licenses/ebusd/LICENSE
COPY app/ /opt/vaillant/
COPY webui/ /opt/vaillant/webui/
COPY rootfs/ /
RUN chmod +x /etc/s6-overlay/s6-rc.d/ebusd/run /etc/s6-overlay/s6-rc.d/vaillant-controller/run /etc/s6-overlay/s6-rc.d/vaillant-webui/run
ARG BUILD_VERSION=0.2.0
ARG BUILD_ARCH=amd64
LABEL io.hass.type="app" io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}"
