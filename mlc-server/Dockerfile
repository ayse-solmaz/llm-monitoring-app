# syntax=docker/dockerfile:1
# CPU-only MLC-LLM spike — linux/amd64 (native on Intel, no GPU/emulation).
# Pinned wheels avoid libtvm / symbol errors seen with unpinned nightly builds.

FROM --platform=linux/amd64 python:3.11-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    git-lfs \
    libgomp1 \
    libx11-6 \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

WORKDIR /app

RUN pip install --upgrade pip && \
    pip install --pre -f https://mlc.ai/wheels --only-binary=:all: --no-deps \
        "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0" && \
    pip install "apache-tvm-ffi==0.1.10" && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install \
        pytest \
        cloudpickle \
        "ml_dtypes>=0.5.1" \
        numpy \
        packaging \
        psutil \
        scipy \
        tornado \
        typing_extensions \
        fastapi \
        uvicorn \
        transformers \
        sentencepiece \
        safetensors \
        tiktoken \
        shortuuid \
        requests \
        tqdm \
        prompt_toolkit \
        pandas \
        datasets \
        openai

ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/tvm_ffi/lib:/usr/local/lib/python3.11/site-packages/tvm/lib:/usr/local/lib/python3.11/site-packages/mlc_llm/lib

RUN git clone --depth 1 https://huggingface.co/mlc-ai/gemma-2b-it-q4f16_1-MLC /app/model && \
    cd /app/model && git lfs pull

RUN python -m mlc_llm compile /app/model --device cpu --quantization q4f16_1 --output /app/model/gemma-cpu.so


FROM --platform=linux/amd64 python:3.11-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgomp1 \
    libx11-6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Reuse builder site-packages (avoids a second long pip install).
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/model /app/model

ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/tvm_ffi/lib:/usr/local/lib/python3.11/site-packages/tvm/lib:/usr/local/lib/python3.11/site-packages/mlc_llm/lib

EXPOSE 8000

CMD ["python3", "-m", "mlc_llm", "serve", "/app/model", \
     "--model-lib", "/app/model/gemma-cpu.so", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--device", "cpu"]
