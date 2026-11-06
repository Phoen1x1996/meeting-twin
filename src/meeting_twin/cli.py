"""Command line for importing the owner's recordings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meeting_twin.audio import TimingError, parse_timing
from meeting_twin.ingest import IngestRefused, import_clip
from meeting_twin.providers import (
    AsrClient,
    ElevenLabsVoiceCloneClient,
    LlmClient,
    MissingEnvError,
    ProviderError,
)


def main(argv: list[str] | None = None, *, asr=None, llm=None, voice=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _import(args, asr=asr, llm=llm, voice=voice)
    except (IngestRefused, MissingEnvError, ProviderError, TimingError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meeting-twin")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("import", help="Import owner speech ranges from a clip")
    command.add_argument("clip", type=Path, help="Wav clip that contains the owner")
    command.add_argument(
        "--timing",
        type=Path,
        default=None,
        help="Timing file of owner speech ranges, in seconds",
    )
    command.add_argument("--recordings-dir", type=Path, default=Path("recordings"))
    command.add_argument("--data-dir", type=Path, default=Path("data"))
    return parser


def _import(args, *, asr, llm, voice) -> int:
    if args.timing is None or not args.timing.is_file():
        raise IngestRefused("refusing to store clip: timing file is required")
    ranges = parse_timing(args.timing.read_text(encoding="utf-8"))
    if not ranges:
        raise IngestRefused("refusing to store clip: timing file has no owner speech ranges")

    asr = asr if asr is not None else AsrClient()
    llm = llm if llm is not None else LlmClient()
    voice = voice if voice is not None else ElevenLabsVoiceCloneClient()
    result = import_clip(
        args.clip,
        args.timing,
        recordings_dir=args.recordings_dir,
        data_dir=args.data_dir,
        asr=asr,
        llm=llm,
        voice=voice,
    )
    print(f"imported {len(result.recordings)} owner range(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
