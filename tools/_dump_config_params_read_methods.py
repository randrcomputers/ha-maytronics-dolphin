"""Dump ``ConfigParamsRead`` bytecode (no ``AnalyzeDex`` — avoids huge stderr on Windows PS).

Run: ``python tools/_dump_config_params_read_methods.py``

Requires ``_apk_mydolphin_extract/classes2.dex`` at repo root (same as other ``_dump_*.py``).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

try:
    from loguru import logger as _loguru_logger

    _loguru_logger.remove()
    _loguru_logger.add(sys.stderr, level="ERROR")
except ImportError:
    pass

from androguard.core.dex import DEX  # noqa: E402

DEX_PATH = Path(__file__).resolve().parents[2] / "_apk_mydolphin_extract" / "classes2.dex"
TARGET = "Lcom/maytronics/mydolphin/model/data/ConfigParamsRead;"
METHODS = ("getBytes", "getAckDataLength", "getAck")
GET_ACK_MAX_INS = 120


def main() -> None:
    if not DEX_PATH.is_file():
        print("missing dex:", DEX_PATH, file=sys.stderr)
        sys.exit(1)
    d = DEX(DEX_PATH.read_bytes())
    cls = d.get_class(TARGET)
    if cls is None:
        print("class not found:", TARGET, file=sys.stderr)
        sys.exit(1)
    for name in METHODS:
        print("===", TARGET, "::", name)
        found = False
        for m in cls.get_methods():
            if m.get_name() != name:
                continue
            found = True
            code = m.get_code()
            if not code:
                print("(no code)")
                break
            ins_list = list(code.get_bc().get_instructions())
            limit = len(ins_list) if name != "getAck" else min(len(ins_list), GET_ACK_MAX_INS)
            for ins in ins_list[:limit]:
                print(ins.get_name(), ins.get_output())
            if name == "getAck" and len(ins_list) > GET_ACK_MAX_INS:
                print(f"... ({len(ins_list) - GET_ACK_MAX_INS} more instructions)")
            break
        if not found:
            print("(method not on outer class — may be inherited)", file=sys.stderr)
    print("done")


if __name__ == "__main__":
    main()
