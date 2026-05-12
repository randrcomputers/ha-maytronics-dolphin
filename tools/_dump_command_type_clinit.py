"""Dump ConfigParamsRead$CommandType <clinit> from MyDolphin classes2.dex."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

from androguard.core.dex import DEX  # noqa: E402

DEX_PATH = Path(__file__).resolve().parents[2] / "_apk_mydolphin_extract" / "classes2.dex"
CMD = "Lcom/maytronics/mydolphin/model/data/ConfigParamsRead" + "$" + "CommandType;"


def main() -> None:
    d = DEX(DEX_PATH.read_bytes())
    for cls in d.get_classes():
        if cls.get_name() != CMD:
            continue
        print("===", cls.get_name())
        for m in cls.get_methods():
            if m.get_name() != "<clinit>" or not m.get_code():
                continue
            for ins in m.get_code().get_bc().get_instructions():
                print(ins.get_name(), ins.get_output())
        return
    print("not found", CMD, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
