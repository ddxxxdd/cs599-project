"""Check whether the configured chat and embedding models are reachable."""

from __future__ import annotations

import json
import os

os.environ.setdefault("LOG_LEVEL", "WARNING")

from aliyun_oss_rag.model_checks import check_models


def main() -> int:
    result = check_models()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["llm"]["available"] and result["embedding"]["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
