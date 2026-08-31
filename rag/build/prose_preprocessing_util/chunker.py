"""IR → ProseChunk 装箱（纯函数，不写盘、不调 embedding 模型）。

协议：``rag/vault/tier_b_prose/CHUNKING.md`` §8 / §11。
落盘由 ``chunk_prose.py`` 负责；向量由 ``embed_prose.py`` 负责。

默认策略（第一次跑、``strategy_id=default``）
--------------------------------------------
``mode=heading``，``chunk_size=0``，``overlap=0``：
按 ``heading_path`` 装箱，**不按固定长度切**。代码必须和紧邻前文说明绑在
同一 bundle 里，只有 embedding 文本（标题前缀 + body）超过 ``max_tokens``
才允许拆。

装箱算法
--------
1. 跳过 ``type=heading``（标题已在 ``heading_path`` 里）。
2. 同一文档内按 ``heading_path`` 分组；不同小节互不装箱。
3. 组内打 bundle：连续 prose 累积，遇到 ``code`` 则「前文 + 该 code」成一捆；
   末尾残留 prose 单独一捆（``code_attach=preceding``）。
4. 按 bundle 贪心装箱。软目标 ``target_tokens=360``：能装就尽量装，**未到
   硬上限不主动切**；过短尾块若并入上一块仍 ≤ ``max_tokens`` 则合并。
   硬上限 ``max_tokens=480``（给 bge-small 的 512 留余量）。
5. 单捆超限：先只切 prose，整段 code 跟最后一块能放下的说明走；仍超限才按
   顶层 ``func`` / ``static func`` / ``class`` / ``enum`` 切代码
   （``code_split=function``）。禁止从函数体中间切开。单个函数仍超 480：
   整函数单独成块并 warning。
6. ``overlap>0`` 且同小节多块时，后一块正文前缀叠前一块末尾 overlap 个
   token 的 **prose**；遇到 code 边界停止，不把代码拆进 overlap。
7. ``mode=fixed`` 且 ``chunk_size>0``：只对纯 prose bundle 开窗；含 code 的
   bundle 仍走上面的原子路径。

Token 计数（重要）
-----------------
生产路径（``chunk_prose.py``）用 ``bge.bge_token_count``：与
``BAAI/bge-small-en-v1.5`` 同一套 WordPiece。本模块的
``approx_token_count`` 只给单测注入，禁止当作默认生产计数器。
详见 CHUNKING.md §11。
"""

from __future__ import annotations

import json
import re
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from rag.retriever.schemas import ProseChunk
from rag.version_codec import version_to_code

from .ir import ProseBlock, ProseDocument, read_ir

TokenCounter = Callable[[str], int]

DEFAULT_STRATEGY_ID = "default"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
EMBED_HARD_CAP = 512
TARGET_TOKENS = 360
MAX_TOKENS = 480

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_TOKEN_RE = re.compile(r"\w+|[^\s\w]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_CODE_BOUNDARY_RE = re.compile(
    r"^(?:static\s+)?func\s+|^class\s+|^class_name\s+|^enum\s+"
)


@dataclass(frozen=True)
class ChunkConfig:
    """切块可调参数。默认值 = 第一次跑的 default 策略，由 CLI 原样写入 manifest.json。

    字段与 ``chunk_prose.py`` 的命令行参数一一对应：

    - mode: ``heading``（按小节装箱）或 ``fixed``（纯 prose 再按 chunk_size 开窗）。
    - chunk_size: 固定窗 token 数；0 = 关闭。仅 ``fixed`` 模式有效。
    - overlap: 相邻 chunk 重叠的 prose token；0 = 不 overlap。
    - max_tokens: embedding 文本硬上限（heading 前缀 + body），默认 480。
    - target_tokens: 软目标，默认 360；未到 max_tokens 不主动切。
    - min_chars_official / min_chars_community: 过短 body 丢弃（官方 20 / 社区 80）。
    - code_attach: 目前只有 ``preceding``——代码绑紧邻前文。
    - code_split: 目前只有 ``function``——超限按函数/类边界切。
    """

    mode: str = "heading"  # heading | fixed
    chunk_size: int = 0  # 0 = no fixed window
    overlap: int = 0
    max_tokens: int = MAX_TOKENS
    target_tokens: int = TARGET_TOKENS
    min_chars_official: int = 20
    min_chars_community: int = 80
    code_attach: str = "preceding"
    code_split: str = "function"

    def to_manifest(self, *, strategy_id: str, chunk_count: int) -> dict:
        payload = asdict(self)
        payload.update(
            {
                "strategy_id": strategy_id,
                "chunk_count": chunk_count,
                "embedding_model": EMBEDDING_MODEL,
                "tokenizer": EMBEDDING_MODEL,
            }
        )
        return payload


@dataclass
class _Bundle:
    prose: list[str]
    code: str | None = None


def approx_token_count(text: str) -> int:
    """正则近似 token 数，**仅供单测**。生产请用 ``bge.bge_token_count``。

    规则：连续 ``\\w`` 算 1 个 token，其余非空白字符各算 1 个。
    这不是 bge WordPiece；不要在 ``chunk_prose.py`` 里当默认计数器。
    """
    if not text.strip():
        return 0
    return max(1, len(_TOKEN_RE.findall(text)))


def embedding_text(heading_path: list[str], body: str) -> str:
    """送进 embedding 模型的文本：标题路径用 `` > `` 拼接，空两行再接下 body。

    ``ProseChunk.text`` 只存 body；前缀只在计数和 embed 时临时拼上。
    """
    if heading_path:
        return " > ".join(heading_path) + "\n\n" + body
    return body


def min_body_chars(source: str, config: ChunkConfig) -> int:
    if source == "community_prose":
        return config.min_chars_community
    return config.min_chars_official


def related_symbols(body: str, match_tokens: list[str]) -> list[str]:
    found: list[str] = []
    for match in _BACKTICK_RE.findall(body):
        tok = match.strip()
        if tok and tok not in found:
            found.append(tok)
    for tok in match_tokens:
        if tok and tok not in found:
            found.append(tok)
    return found


def lift_prose_jsonl(path: Path) -> list[ProseDocument]:
    """Lift type-A ``*.prose.jsonl`` into degenerate ProseDocuments (§3.6)."""
    docs: list[ProseDocument] = []
    seen: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        heading_path = list(rec.get("heading_path") or [])
        source_file = str(rec.get("source_file") or path.name)
        source = str(rec.get("source") or "official_prose")
        path_key = "/".join(heading_path)
        doc_id = f"legacy_prose_jsonl/{source_file}#{path_key}"
        if doc_id in seen:
            seen[doc_id] += 1
            doc_id = f"{doc_id}#{seen[doc_id]}"
        else:
            seen[doc_id] = 1
        text = str(rec.get("text") or "")
        docs.append(
            ProseDocument(
                schema_version=1,
                doc_id=doc_id,
                source=source,
                source_file=source_file,
                source_url=None,
                source_type="legacy_prose_jsonl",
                since_version=rec.get("since_version"),
                confidence="verified",
                title=None,
                keep=True,
                match_tokens=[],
                blocks=[
                    ProseBlock(
                        block_id="b0001",
                        type="paragraph",
                        text=text,
                        heading_path=heading_path,
                    )
                ],
            )
        )
    return docs


def load_ir_documents(ir_dir: Path) -> list[ProseDocument]:
    """Recursively read ``ir/<bucket>/*.ir.json`` where ``keep=true``."""
    docs: list[ProseDocument] = []
    if not ir_dir.is_dir():
        return docs
    for path in sorted(ir_dir.rglob("*.ir.json")):
        doc = read_ir(path)
        if doc.keep:
            docs.append(doc)
    return docs


def type_a_paths(tier_b_dir: Path) -> list[Path]:
    type_a_dir = tier_b_dir / "_raw" / "official_upgrading_guide"
    paths: list[Path] = []
    if type_a_dir.is_dir():
        paths.extend(sorted(type_a_dir.glob("*.prose.jsonl")))
    paths.extend(sorted(tier_b_dir.glob("*.prose.jsonl")))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        if path.name in seen:
            continue
        seen.add(path.name)
        unique.append(path)
    return unique


def _body(parts: list[tuple[str, str]]) -> str:
    return "\n\n".join(text for _, text in parts if text.strip())


def _tok(
    heading_path: list[str],
    parts: list[tuple[str, str]],
    counter: TokenCounter,
) -> int:
    return counter(embedding_text(heading_path, _body(parts)))


def _make_bundles(blocks: list[ProseBlock], code_attach: str) -> list[_Bundle]:
    bundles: list[_Bundle] = []
    prose_acc: list[str] = []
    for block in blocks:
        piece = block.text.strip()
        if not piece:
            continue
        if block.type == "code" and code_attach == "preceding":
            bundles.append(_Bundle(prose=list(prose_acc), code=piece))
            prose_acc = []
        else:
            prose_acc.append(piece)
    if prose_acc:
        bundles.append(_Bundle(prose=prose_acc, code=None))
    return bundles


def _bundle_parts(bundle: _Bundle) -> list[tuple[str, str]]:
    parts = [("prose", p) for p in bundle.prose if p.strip()]
    if bundle.code and bundle.code.strip():
        parts.append(("code", bundle.code.strip()))
    return parts


def split_code_at_functions(text: str) -> list[str]:
    """Split GDScript (or similar) on top-level func/class/enum boundaries."""
    lines = text.split("\n")
    starts: list[int] = []
    for i, line in enumerate(lines):
        if line[:1] in {" ", "\t"}:
            continue
        if _CODE_BOUNDARY_RE.match(line):
            starts.append(i)
    if not starts:
        return [text.strip()] if text.strip() else []
    units: list[str] = []
    if starts[0] != 0:
        preamble = "\n".join(lines[: starts[0]]).rstrip()
        if preamble.strip():
            units.append(preamble)
    for j, start in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        unit = "\n".join(lines[start:end]).rstrip()
        if unit.strip():
            units.append(unit)
    return units


def _hard_split_prose(
    heading_path: list[str],
    text: str,
    counter: TokenCounter,
    max_tokens: int,
) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    units: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if counter(embedding_text(heading_path, para)) <= max_tokens:
            units.append(para)
            continue
        for sent in _SENTENCE_RE.split(para):
            sent = sent.strip()
            if not sent:
                continue
            if counter(embedding_text(heading_path, sent)) <= max_tokens:
                units.append(sent)
                continue
            units.extend(_split_chars(heading_path, sent, counter, max_tokens))

    out: list[str] = []
    current: list[str] = []

    def fits(parts: list[str]) -> bool:
        return counter(embedding_text(heading_path, "\n\n".join(parts))) <= max_tokens

    for unit in units:
        cand = current + [unit]
        if fits(cand):
            current.append(unit)
        else:
            if current:
                out.append("\n\n".join(current))
            current = [unit]
    if current:
        out.append("\n\n".join(current))
    return [p for p in out if p.strip()]


def _split_chars(
    heading_path: list[str],
    text: str,
    counter: TokenCounter,
    max_tokens: int,
) -> list[str]:
    out: list[str] = []
    remaining = text
    while remaining:
        lo, hi = 1, len(remaining)
        best = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if counter(embedding_text(heading_path, remaining[:mid])) <= max_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        piece = remaining[:best].strip()
        if piece:
            out.append(piece)
        remaining = remaining[best:]
        if best == 0:
            break
    return out


def _split_code(
    heading_path: list[str],
    code: str,
    counter: TokenCounter,
    max_tokens: int,
    code_split: str,
) -> list[list[tuple[str, str]]]:
    units = split_code_at_functions(code) if code_split == "function" else [code]
    if not units:
        return []
    out: list[list[tuple[str, str]]] = []
    for unit in units:
        n = counter(embedding_text(heading_path, unit))
        if n <= max_tokens:
            out.append([("code", unit)])
            continue
        warnings.warn(
            f"single function/class exceeds max_tokens={max_tokens} "
            f"(got {n}); keeping intact to avoid mid-function splits",
            stacklevel=2,
        )
        out.append([("code", unit)])
    return out


def _split_bundle(
    heading_path: list[str],
    bundle: _Bundle,
    counter: TokenCounter,
    config: ChunkConfig,
) -> list[list[tuple[str, str]]]:
    """Split an oversized bundle: prose first, keep code attached to the tail."""
    max_tokens = config.max_tokens
    prose_units: list[str] = []
    if bundle.prose:
        prose_units = _hard_split_prose(
            heading_path, "\n\n".join(bundle.prose), counter, max_tokens
        )
    if not bundle.code:
        return [[("prose", p)] for p in prose_units]

    result: list[list[tuple[str, str]]] = []
    remaining = list(prose_units)
    code = bundle.code.strip()
    while remaining:
        trial = [("prose", p) for p in remaining] + [("code", code)]
        if _tok(heading_path, trial, counter) <= max_tokens:
            result.append(trial)
            return result
        result.append([("prose", remaining.pop(0))])

    code_n = counter(embedding_text(heading_path, code))
    if code_n <= max_tokens:
        result.append([("code", code)])
        return result
    result.extend(
        _split_code(heading_path, code, counter, max_tokens, config.code_split)
    )
    return result


def _take_prefix(
    heading_path: list[str],
    text: str,
    n_tokens: int,
    counter: TokenCounter,
    max_tokens: int,
) -> tuple[str, str]:
    if not text:
        return "", ""
    lo, hi = 1, len(text)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        body = text[:mid]
        if (
            counter(body) <= n_tokens
            and counter(embedding_text(heading_path, body)) <= max_tokens
        ):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    prefix = text[:best]
    rest = text[best:]
    if not prefix.strip() and rest:
        # Guarantee forward progress.
        prefix, rest = rest[:1], rest[1:]
    return prefix, rest


def _take_suffix(text: str, n_tokens: int, counter: TokenCounter) -> str:
    if n_tokens <= 0 or not text:
        return ""
    lo, hi = 0, len(text)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        suffix = text[len(text) - mid :] if mid else ""
        if not suffix or counter(suffix) <= n_tokens:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return text[len(text) - best :] if best else ""


def _window_prose(
    heading_path: list[str],
    prose: list[str],
    config: ChunkConfig,
    counter: TokenCounter,
) -> list[list[tuple[str, str]]]:
    text = "\n\n".join(p for p in prose if p.strip()).strip()
    if not text:
        return []
    size = config.chunk_size
    overlap = config.overlap if config.overlap < size else 0
    windows: list[list[tuple[str, str]]] = []
    rest = text
    while rest.strip():
        before = rest
        prefix, leftover = _take_prefix(
            heading_path, rest, size, counter, config.max_tokens
        )
        if not prefix.strip():
            break
        windows.append([("prose", prefix.strip())])
        if not leftover.strip():
            break
        tail = _take_suffix(prefix, overlap, counter) if overlap else ""
        rest = (tail + leftover) if tail else leftover
        if len(rest) >= len(before):
            rest = leftover
            if not rest.strip() or rest == before:
                break
    return windows


def _trailing_prose_overlap(
    parts: list[tuple[str, str]],
    n_tokens: int,
    counter: TokenCounter,
) -> str:
    """Overlap from the trailing prose only; stop at a code boundary."""
    if n_tokens <= 0 or not parts:
        return ""
    trailing: list[str] = []
    for kind, text in reversed(parts):
        if kind == "code":
            break
        trailing.append(text)
    if not trailing:
        return ""
    prose = "\n\n".join(reversed(trailing))
    return _take_suffix(prose, n_tokens, counter)


def _apply_overlap(
    packed: list[list[tuple[str, str]]],
    overlap: int,
    counter: TokenCounter,
) -> list[list[tuple[str, str]]]:
    if overlap <= 0 or len(packed) < 2:
        return packed
    out: list[list[tuple[str, str]]] = [packed[0]]
    for i in range(1, len(packed)):
        tail = _trailing_prose_overlap(packed[i - 1], overlap, counter)
        nxt = list(packed[i])
        if tail.strip():
            nxt = [("prose", tail.strip())] + nxt
        out.append(nxt)
    return out


def _merge_undersized(
    heading_path: list[str],
    packed: list[list[tuple[str, str]]],
    counter: TokenCounter,
    target_tokens: int,
    max_tokens: int,
) -> list[list[tuple[str, str]]]:
    if len(packed) < 2 or target_tokens <= 0:
        return packed
    prev, last = packed[-2], packed[-1]
    last_n = _tok(heading_path, last, counter)
    combined_n = _tok(heading_path, prev + last, counter)
    if last_n < target_tokens and combined_n <= max_tokens:
        packed[-2] = prev + last
        packed.pop()
    return packed


def _peel_into_current(
    heading_path: list[str],
    current: list[tuple[str, str]],
    bundle: _Bundle,
    counter: TokenCounter,
    max_tokens: int,
) -> _Bundle:
    """Move leading prose into ``current`` while it still fits under max_tokens."""
    prose = list(bundle.prose)
    while prose:
        trial = current + [("prose", prose[0])]
        if _tok(heading_path, trial, counter) <= max_tokens:
            current.append(("prose", prose.pop(0)))
            continue
        pieces = _hard_split_prose(heading_path, prose[0], counter, max_tokens)
        if not pieces:
            break
        if _tok(heading_path, current + [("prose", pieces[0])], counter) <= max_tokens:
            current.append(("prose", pieces[0]))
            rest = "\n\n".join(pieces[1:])
            prose = ([rest] if rest.strip() else []) + prose[1:]
            continue
        break
    return _Bundle(prose=prose, code=bundle.code)


def _pack_group(
    heading_path: list[str],
    blocks: list[ProseBlock],
    counter: TokenCounter,
    config: ChunkConfig,
) -> list[tuple[list[str], str]]:
    bundles = _make_bundles(blocks, config.code_attach)
    packed: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []

    def flush() -> None:
        if current:
            packed.append(list(current))
            current.clear()

    for bundle in bundles:
        if (
            config.mode == "fixed"
            and config.chunk_size > 0
            and bundle.code is None
        ):
            flush()
            packed.extend(_window_prose(heading_path, bundle.prose, config, counter))
            continue

        parts = _bundle_parts(bundle)
        if not parts:
            continue
        if current and _tok(heading_path, current + parts, counter) <= config.max_tokens:
            current.extend(parts)
            continue
        if current:
            leftover = _peel_into_current(
                heading_path, current, bundle, counter, config.max_tokens
            )
            flush()
            bundle = leftover
            parts = _bundle_parts(bundle)
            if not parts:
                continue
        if _tok(heading_path, parts, counter) <= config.max_tokens:
            current.extend(parts)
            continue
        for piece in _split_bundle(heading_path, bundle, counter, config):
            if current and _tok(heading_path, current + piece, counter) > config.max_tokens:
                flush()
            if _tok(heading_path, piece, counter) <= config.max_tokens:
                current.extend(piece)
            else:
                flush()
                packed.append(piece)

    flush()
    packed = _merge_undersized(
        heading_path, packed, counter, config.target_tokens, config.max_tokens
    )
    packed = _apply_overlap(packed, config.overlap, counter)
    return [(heading_path, _body(parts)) for parts in packed if _body(parts).strip()]


def _chunk_one(
    doc: ProseDocument,
    counter: TokenCounter,
    config: ChunkConfig,
) -> list[ProseChunk]:
    stream = [b for b in doc.blocks if b.type != "heading"]
    groups: list[tuple[tuple[str, ...], list[ProseBlock]]] = []
    for block in stream:
        key = tuple(block.heading_path)
        if not groups or groups[-1][0] != key:
            groups.append((key, [block]))
        else:
            groups[-1][1].append(block)

    packed: list[tuple[list[str], str]] = []
    for heading, blocks in groups:
        packed.extend(_pack_group(list(heading), blocks, counter, config))

    floor = min_body_chars(doc.source, config)
    chunks: list[ProseChunk] = []
    n = 0
    for heading_path, body in packed:
        if len(body.strip()) < floor:
            continue
        n += 1
        chunks.append(
            ProseChunk(
                id=f"{doc.doc_id}::c{n:04d}",
                text=body,
                heading_path=heading_path,
                since_version=doc.since_version,
                since_version_code=version_to_code(doc.since_version),
                related_symbols=related_symbols(body, doc.match_tokens),
                source=doc.source,
                source_file=doc.source_file,
                source_url=doc.source_url,
            )
        )
    return chunks


def chunk_documents(
    docs: list[ProseDocument],
    *,
    config: ChunkConfig | None = None,
    token_counter: TokenCounter | None = None,
    target_tokens: int | None = None,
    max_tokens: int | None = None,
    overlap: int | None = None,
    mode: str | None = None,
    chunk_size: int | None = None,
) -> list[ProseChunk]:
    """把 ``ProseDocument`` 列表装箱成 ``ProseChunk``。

    ``token_counter`` 可注入。单测应传入 ``approx_token_count`` 或按空格
    数词的假计数器，避免加载 ONNX。``chunk_prose.py`` 必须传入
    ``bge_token_count``。未传入时默认 ``approx_token_count``（只为不拖垮 pytest）。
    """
    cfg = config or ChunkConfig()
    updates: dict = {}
    if target_tokens is not None:
        updates["target_tokens"] = target_tokens
    if max_tokens is not None:
        updates["max_tokens"] = max_tokens
    if overlap is not None:
        updates["overlap"] = overlap
    if mode is not None:
        updates["mode"] = mode
    if chunk_size is not None:
        updates["chunk_size"] = chunk_size
    if updates:
        cfg = ChunkConfig(**{**asdict(cfg), **updates})
    counter = token_counter or approx_token_count
    chunks: list[ProseChunk] = []
    for doc in docs:
        if not doc.keep:
            continue
        chunks.extend(_chunk_one(doc, counter, cfg))
    return chunks
