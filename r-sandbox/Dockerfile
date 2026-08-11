FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Python (for FastAPI server only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages uv

# R runtime + pre-compiled CRAN packages via apt (instant install, no compilation).
# This is the key difference vs installing from CRAN source which compiles C/C++.
RUN apt-get update && apt-get install -y --no-install-recommends \
    r-base r-base-core r-base-dev \
    r-cran-tidyverse r-cran-ggplot2 r-cran-dplyr \
    r-cran-survival r-cran-survminer \
    r-cran-jsonlite r-cran-httr r-cran-data.table \
    r-cran-readr r-cran-stringr r-cran-xml2 \
    r-cran-plotly r-cran-rcpp \
    libcurl4-openssl-dev libssl-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Only a few packages need CRAN source install (not available via apt).
# These are small/pure-R and compile fast.
RUN R -e 'install.packages(c("aws.s3", "circlize", "pheatmap"), repos="https://cloud.r-project.org/")'


WORKDIR /app
COPY requirements.txt ./
RUN uv pip install --system --break-system-packages --no-cache -r requirements.txt
COPY server.py r_helpers.R ./

RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 10001 runner

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "server.py"]
