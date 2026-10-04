#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按键级测试 stroke 方案：ctypes 直连 librime，逐键输入并打印候选。

不依赖任何 Rime 前端，可在 CI 或本机验证方案行为。需要系统装有
librime.so.1（Debian: librime1t64）及 /usr/share/rime-data（含
default.yaml 与 luna_pinyin，用于反查依赖）。

用法:
    tools/test_candidates.py <user_dir> <按键串1> [按键串2 ...]

user_dir 放 stroke.schema.yaml、stroke.dict.yaml 及如下 default.custom.yaml:
    patch:
      schema_list:
        - schema: stroke

示例:
    tools/test_candidates.py /tmp/rime-user p ph phshzpn
"""
import sys
import ctypes
from ctypes import (Structure, c_int, c_char_p, c_void_p, POINTER, byref,
                    sizeof, c_size_t, CFUNCTYPE)


class RimeTraits(Structure):
    _fields_ = [
        ("data_size", c_int),
        ("shared_data_dir", c_char_p),
        ("user_data_dir", c_char_p),
        ("distribution_name", c_char_p),
        ("distribution_code_name", c_char_p),
        ("distribution_version", c_char_p),
        ("app_name", c_char_p),
        ("modules", POINTER(c_char_p)),
        ("min_log_level", c_int),
        ("log_dir", c_char_p),
        ("prebuilt_data_dir", c_char_p),
        ("staging_dir", c_char_p),
    ]


class RimeComposition(Structure):
    _fields_ = [("length", c_int), ("cursor_pos", c_int),
                ("sel_start", c_int), ("sel_end", c_int),
                ("preedit", c_char_p)]


class RimeCandidate(Structure):
    _fields_ = [("text", c_char_p), ("comment", c_char_p),
                ("reserved", c_void_p)]


class RimeMenu(Structure):
    _fields_ = [("page_size", c_int), ("page_no", c_int),
                ("is_last_page", c_int), ("highlighted_candidate_index", c_int),
                ("num_candidates", c_int),
                ("candidates", POINTER(RimeCandidate)),
                ("select_keys", c_char_p)]


class RimeContext(Structure):
    _fields_ = [("data_size", c_int), ("composition", RimeComposition),
                ("menu", RimeMenu), ("commit_text_preview", c_char_p),
                ("select_labels", POINTER(c_char_p))]


class RimeCommit(Structure):
    _fields_ = [("data_size", c_int), ("text", c_char_p)]


# 字段顺序与 librime 1.13.1 rime_api.h 一致（开头是 data_size 整型，
# 之后才是函数指针）；只给要调用的 API 配签名，其余用占位指针
_F = CFUNCTYPE


class RimeApi(Structure):
    _fields_ = [
        ("data_size", c_int),                              # 0
        ("setup", _F(None, POINTER(RimeTraits))),          # 1
        ("set_notification_handler", c_void_p),            # 2
        ("initialize", _F(None, POINTER(RimeTraits))),     # 3
        ("finalize", c_void_p),                            # 4
        ("start_maintenance", _F(c_int, c_int)),           # 5
        ("is_maintenance_mode", c_void_p),                 # 6
        ("join_maintenance_thread", _F(None)),             # 7
        ("deployer_initialize", c_void_p),                 # 8
        ("prebuild", c_void_p),                            # 9
        ("deploy", c_void_p),                              # 10
        ("deploy_schema", c_void_p),                       # 11
        ("deploy_config_file", c_void_p),                  # 12
        ("sync_user_data", c_void_p),                      # 13
        ("create_session", _F(c_size_t)),                  # 14
        ("find_session", c_void_p),                        # 15
        ("destroy_session", _F(c_int, c_size_t)),          # 16
        ("cleanup_stale_sessions", c_void_p),              # 17
        ("cleanup_all_sessions", c_void_p),                # 18
        ("process_key", _F(c_int, c_size_t, c_int, c_int)),  # 19
        ("commit_composition", c_void_p),                  # 20
        ("clear_composition", _F(None, c_size_t)),         # 21
        ("get_commit", _F(c_int, c_size_t, POINTER(RimeCommit))),  # 22
        ("free_commit", c_void_p),                         # 23
        ("get_context", _F(c_int, c_size_t, POINTER(RimeContext))),  # 24
        ("free_context", _F(c_int, POINTER(RimeContext))),  # 25
        ("get_status", c_void_p),                          # 26
        ("free_status", c_void_p),                         # 27
        ("set_option", c_void_p),                          # 28
        ("get_option", c_void_p),                          # 29
        ("set_property", c_void_p),                        # 30
        ("get_property", c_void_p),                        # 31
        ("get_schema_list", c_void_p),                     # 32
        ("free_schema_list", c_void_p),                    # 33
        ("get_current_schema", c_void_p),                  # 34
        ("select_schema", _F(c_int, c_size_t, c_char_p)),  # 35
    ]


def init(user_dir):
    lib = ctypes.CDLL("librime.so.1")
    lib.rime_get_api.restype = POINTER(RimeApi)
    api = lib.rime_get_api().contents
    t = RimeTraits()
    t.data_size = sizeof(RimeTraits) - sizeof(c_int)
    t.shared_data_dir = b"/usr/share/rime-data"
    t.user_data_dir = user_dir.encode()
    t.distribution_name = b"rime-stroke-test"
    t.distribution_code_name = b"rime-stroke-test"
    t.distribution_version = b"0.1"
    t.app_name = b"rime.rime-stroke-test"
    t.min_log_level = 2
    t.log_dir = b""
    api.setup(byref(t))
    api.initialize(byref(t))
    api.start_maintenance(True)
    api.join_maintenance_thread()
    return api


def show(api, sid, typed):
    ctx = RimeContext()
    ctx.data_size = sizeof(RimeContext) - sizeof(c_int)
    if not api.get_context(sid, byref(ctx)):
        print(f"  [{typed}] <no context>")
        return
    m = ctx.menu
    n = m.num_candidates
    if n == 0:
        print(f"  [{typed}] <无候选>")
    else:
        texts = [m.candidates[i].text.decode() for i in range(min(n, 10))]
        print(f"  [{typed}] {n}个候选: " + " ".join(texts))
    api.free_context(byref(ctx))


def run(api, keys, label=None):
    sid = api.create_session()
    api.select_schema(sid, b"stroke")
    typed = ""
    for ch in keys:
        api.process_key(sid, ord(ch), 0)
        typed += ch
        show(api, sid, typed)
    api.clear_composition(sid)
    api.destroy_session(sid)


def main():
    user_dir, sequences = sys.argv[1], sys.argv[2:]
    api = init(user_dir)
    for keys in sequences:
        run(api, keys)


if __name__ == "__main__":
    main()
