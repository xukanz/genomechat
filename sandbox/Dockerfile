FROM ubuntu:24.04

# Minimal setup - Python runtime + data analysis dependencies
ENV DEBIAN_FRONTEND=noninteractive
ENV MPLBACKEND=Agg
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     ca-certificates curl \
     python3 python3-pip \
     libfreetype6 \
     libpng16-16 \
     libjpeg-turbo8 \
     fonts-dejavu-core \
     fontconfig \
  && rm -rf /var/lib/apt/lists/*

# Install uv via pip (avoids SSL issues with corporate proxies)
RUN pip3 install --no-cache-dir --break-system-packages uv

# App setup
WORKDIR /app

# Copy requirements and install with uv (much faster than pip)
COPY requirements.txt ./
RUN uv pip install --system --break-system-packages --no-cache -r requirements.txt

COPY server.py s3_helpers.py ./

# Install gosu for user switching
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
  && rm -rf /var/lib/apt/lists/*

# Non-root runtime user
RUN useradd -m -u 10001 runner

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "server.py"]

