"""L2：单文件语义。

由 SceneDoc 得到节点全路径、根列表、外部资源编号表、连接和引用边。
标出 instance / instance_placeholder / 继承场景上看不全的子树。
引用边带上原文 span。这一层不说对错。
不 import os、pathlib、sqlite3，不读磁盘。

契约见 codebase_index/NEXT_STEP.md 第 3 节。纯函数，不碰文件系统。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codeindex.scene.lexer import Span, Value
from codeindex.scene.model import SceneDoc, Section

__all__ = [
    "ExtRes",
    "SubRes",
    "SceneNode",
    "Connection",
    "Ref",
    "SceneModel",
    "resolve",
]


@dataclass
class ExtRes:
    id: str
    type: str | None
    uid: str | None
    ref_path: str | None
    span: Span


@dataclass
class SubRes:
    id: str
    type: str | None
    span: Span


@dataclass
class SceneNode:
    node_path: str
    name: str
    type: str | None
    parent: str | None
    span: Span
    heading_span: Span
    has_instance: bool = False
    has_instance_placeholder: bool = False
    has_script: bool = False


@dataclass
class Connection:
    signal: str | None
    from_path: str | None
    to_path: str | None
    method: str | None
    span: Span


@dataclass
class Ref:
    """一条引用边。kind 的取值见 NEXT_STEP 第 3 节的表。"""

    kind: str
    value: str
    span: Span
    node_path: str | None = None


@dataclass
class SceneModel:
    path: str
    doc_kind: str
    format: int | None
    uid: str | None
    script_class: str | None
    ext: dict[str, ExtRes] = field(default_factory=dict)
    sub: dict[str, SubRes] = field(default_factory=dict)
    nodes: list[SceneNode] = field(default_factory=list)
    node_by_path: dict[str, SceneNode] = field(default_factory=dict)
    root_paths: list[str] = field(default_factory=list)
    conns: list[Connection] = field(default_factory=list)
    editables: list[str] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)
    unresolved_subtrees: list[str] = field(default_factory=list)
    is_inherited: bool = False


# ---------------------------------------------------------------------------
# 值解码
# ---------------------------------------------------------------------------


def _decode_str(raw: str) -> str:
    """去掉 raw 字符串两侧的引号。不处理转义（引用边只需要原文 id）。"""
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1]
    return raw


def _attr_str(attrs: dict[str, Value], key: str) -> str | None:
    v = attrs.get(key)
    if v is None or v.kind != "str":
        return None
    return _decode_str(v.raw)


def _call_id(v: Value) -> str | None:
    """ExtResource( 3 ) / ExtResource("1_7bt6s") 的 id。int 或 str 参数都接受。"""
    if v.kind != "call" or not v.items:
        return None
    arg = v.items[0]
    if arg.kind == "int":
        return arg.raw
    if arg.kind == "str":
        return _decode_str(arg.raw)
    return None


# ---------------------------------------------------------------------------
# 引用边收集
# ---------------------------------------------------------------------------


def _walk_value(v: Value, node_path: str | None, refs: list[Ref]) -> None:
    """递归遍历一个 Value，把 ExtResource / SubResource / NodePath 字面量记成引用边。"""
    if v.kind == "call":
        if v.name == "ExtResource":
            rid = _call_id(v)
            if rid is not None:
                refs.append(Ref(kind="ext_use", value=rid, span=v.span, node_path=node_path))
        elif v.name == "SubResource":
            rid = _call_id(v)
            if rid is not None:
                refs.append(Ref(kind="sub_use", value=rid, span=v.span, node_path=node_path))
        elif v.name == "NodePath":
            if v.items and v.items[0].kind == "str":
                refs.append(
                    Ref(
                        kind="nodepath",
                        value=_decode_str(v.items[0].raw),
                        span=v.span,
                        node_path=node_path,
                    )
                )
        for item in v.items:
            _walk_value(item, node_path, refs)
    elif v.kind == "nodepath":
        refs.append(Ref(kind="nodepath", value=_decode_str(v.raw[1:]), span=v.span, node_path=node_path))
    elif v.kind == "array" or v.kind == "typed_array":
        for item in v.items:
            _walk_value(item, node_path, refs)
    elif v.kind == "dict":
        for k, val in v.pairs:
            _walk_value(k, node_path, refs)
            _walk_value(val, node_path, refs)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def resolve(doc: SceneDoc) -> SceneModel:
    """由 SceneDoc 推出单文件语义模型。纯函数，不读磁盘。"""
    model = SceneModel(
        path=doc.path,
        doc_kind=doc.doc_kind,
        format=doc.format,
        uid=doc.uid,
        script_class=doc.script_class,
    )

    for sec in doc.sections:
        if sec.kind == "ext_resource":
            _add_ext(sec, model)
        elif sec.kind == "sub_resource":
            _add_sub(sec, model)
        elif sec.kind == "node":
            _add_node(sec, model)
        elif sec.kind == "connection":
            _add_conn(sec, model)
        elif sec.kind == "editable":
            _add_editable(sec, model)
        elif sec.kind == "gd_resource" and sec.attrs.get("script_class"):
            model.refs.append(
                Ref(
                    kind="script_class",
                    value=_decode_str(sec.attrs["script_class"].raw),
                    span=sec.attrs["script_class"].span,
                )
            )

    # 实例子树弃权前缀
    for node in model.nodes:
        if node.has_instance or node.has_instance_placeholder:
            model.unresolved_subtrees.append(node.node_path)
    if model.is_inherited and "." not in model.unresolved_subtrees:
        model.unresolved_subtrees.append(".")

    return model


def _add_ext(sec: Section, model: SceneModel) -> None:
    rid = _attr_str(sec.attrs, "id")
    if rid is None:
        # Godot 3 整数 id
        v = sec.attrs.get("id")
        rid = v.raw if v is not None and v.kind == "int" else None
    if rid is None:
        return
    ref_path = _attr_str(sec.attrs, "path")
    ext = ExtRes(
        id=rid,
        type=_attr_str(sec.attrs, "type"),
        uid=_attr_str(sec.attrs, "uid"),
        ref_path=ref_path,
        span=sec.heading_span,
    )
    model.ext[rid] = ext
    if ext.type is not None:
        model.refs.append(
            Ref(kind="res_type", value=ext.type, span=sec.attrs["type"].span)
        )
    if ref_path is not None:
        model.refs.append(
            Ref(kind="ext_path", value=ref_path, span=sec.attrs["path"].span)
        )


def _add_sub(sec: Section, model: SceneModel) -> None:
    rid = _attr_str(sec.attrs, "id")
    if rid is None:
        v = sec.attrs.get("id")
        rid = v.raw if v is not None and v.kind == "int" else None
    if rid is None:
        return
    sub = SubRes(
        id=rid,
        type=_attr_str(sec.attrs, "type"),
        span=sec.heading_span,
    )
    model.sub[rid] = sub
    if sub.type is not None:
        model.refs.append(
            Ref(kind="res_type", value=sub.type, span=sec.attrs["type"].span)
        )
    # sub_resource 的 props 里也可能有 ExtResource / SubResource 引用
    for _k, v in sec.props:
        _walk_value(v, None, model.refs)


def _add_node(sec: Section, model: SceneModel) -> None:
    name = _attr_str(sec.attrs, "name")
    if name is None:
        return
    parent = _attr_str(sec.attrs, "parent")
    if parent is None:
        node_path = name if not model.root_paths else name
        model.root_paths.append(node_path)
    else:
        node_path = name if parent == "." else parent + "/" + name

    has_instance = "instance" in sec.attrs
    has_placeholder = "instance_placeholder" in sec.attrs
    node = SceneNode(
        node_path=node_path,
        name=name,
        type=_attr_str(sec.attrs, "type"),
        parent=parent,
        span=sec.span,
        heading_span=sec.heading_span,
        has_instance=has_instance,
        has_instance_placeholder=has_placeholder,
    )
    model.nodes.append(node)
    model.node_by_path[node_path] = node

    # 根节点带 instance → 继承场景
    if parent is None and has_instance:
        model.is_inherited = True

    # node_type 引用边
    if node.type is not None:
        model.refs.append(
            Ref(kind="node_type", value=node.type, span=sec.attrs["type"].span, node_path=node_path)
        )

    # instance 引用边
    if has_instance:
        inst = sec.attrs["instance"]
        rid = _call_id(inst)
        if rid is not None:
            model.refs.append(
                Ref(kind="instance", value=rid, span=inst.span, node_path=node_path)
            )
            _walk_value(inst, node_path, model.refs)

    # groups
    groups = sec.attrs.get("groups")
    if groups is not None and groups.kind == "array":
        for item in groups.items:
            if item.kind == "str":
                model.refs.append(
                    Ref(kind="group", value=_decode_str(item.raw), span=item.span, node_path=node_path)
                )

    # 属性
    has_script = False
    for k, v in sec.props:
        if k == "script" and v.kind == "call" and v.name == "ExtResource":
            has_script = True
            rid = _call_id(v)
            if rid is not None:
                model.refs.append(
                    Ref(kind="script_ref", value=rid, span=v.span, node_path=node_path)
                )
        _walk_value(v, node_path, model.refs)
    node.has_script = has_script

    # prop_key：挂了脚本的节点，属性键全部入库
    if has_script:
        for k, v in sec.props:
            if k == "script":
                continue
            model.refs.append(
                Ref(kind="prop_key", value=k, span=v.span, node_path=node_path)
            )


def _add_conn(sec: Section, model: SceneModel) -> None:
    conn = Connection(
        signal=_attr_str(sec.attrs, "signal"),
        from_path=_attr_str(sec.attrs, "from"),
        to_path=_attr_str(sec.attrs, "to"),
        method=_attr_str(sec.attrs, "method"),
        span=sec.heading_span,
    )
    model.conns.append(conn)
    if conn.method is not None:
        model.refs.append(
            Ref(kind="conn_method", value=conn.method, span=sec.attrs["method"].span)
        )
    if conn.signal is not None:
        model.refs.append(
            Ref(kind="conn_signal", value=conn.signal, span=sec.attrs["signal"].span)
        )


def _add_editable(sec: Section, model: SceneModel) -> None:
    path = _attr_str(sec.attrs, "path")
    if path is not None:
        model.editables.append(path)
