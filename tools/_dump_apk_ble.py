"""One-off APK dex dump (run from repo). PowerShell mangles $ in -c strings."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

from androguard.core.dex import DEX  # noqa: E402

DEX_PATH = Path(__file__).resolve().parents[2] / "_apk_mydolphin_extract" / "classes2.dex"
# Inner class name: ConfigParamsRead + dollar + "1"
INNER_1 = "Lcom/maytronics/mydolphin/model/data/ConfigParamsRead" + "$" + "1;"


def main() -> None:
    d = DEX(DEX_PATH.read_bytes())
    for cls in d.get_classes():
        if cls.get_name() != INNER_1:
            continue
        print("===", cls.get_name(), "methods:", [m.get_name() for m in cls.get_methods()])
        for m in cls.get_methods():
            if m.get_name() != "<clinit>" or not m.get_code():
                continue
            for ins in m.get_code().get_bc().get_instructions():
                print(ins.get_name(), ins.get_output())
        return
    print("class not found", INNER_1, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
