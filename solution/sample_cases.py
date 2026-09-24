"""The sample conformance suite: one image per stated rule, each the hard case of that rule."""
from fvm_asm import Prog


def P(**kw):
    kw.setdefault("F", 100000)
    kw.setdefault("S", 64)
    kw.setdefault("D", 16)
    kw.setdefault("L", 255)
    kw.setdefault("W", 32)
    return Prog(**kw)


def guarded(p, body, tag):
    """body inside TRY; on a raise print the raised value."""
    p.ops(f"TRY:h_{tag} {body} ENDTRY JMP:d_{tag} h_{tag}: PRINT d_{tag}:")


CASES = {}


def case(fn):
    CASES[fn.__name__] = fn
    return fn


# ---------------------------------------------------------------- image layout
@case
def img_redundant_varints():
    p = P(W=16)
    p.func("main", 0, 1)
    p.consts.append(("raw", b"\x00" + b"\x8a\x80\x80\x00"))  # svarint 5, redundant groups
    p.label("main")
    p.ops("PUSHK:0 PRINT")
    p.raw(b"\x01\x95\x80\x00")  # PUSHI -11, redundant
    p.ops("PRINT")
    p.raw(b"\x08\x80\x00")      # LOAD 0, redundant
    p.ops("PRINT HALT")
    return p.image()


def _plain():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PRINT HALT")
    return p


@case
def bad_magic():
    img = bytearray(_plain().image())
    img[3] = 0x01
    return bytes(img)


@case
def bad_width():
    p = _plain()
    p.W = 49
    return p.image()


@case
def bad_trailing_byte():
    return _plain().image(trailer=b"\x00")


@case
def bad_varint_too_large():
    p = P(W=16)
    p.func("main", 0, 0)
    p.consts.append(("raw", b"\x00" + b"\xff" * 9 + b"\x02"))
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def bad_string_past_limit():
    p = P(W=16, L=4)
    p.func("main", 0, 0)
    p.consts.append(("raw", b"\x01\x05abcde"))
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def bad_entry_params():
    p = P(W=16)
    p.func("main", 1, 1)
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def bad_offset_past_code():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 0, label="end")
    p.label("main")
    p.ops("HALT")
    p.label("end")
    return p.image()


@case
def bad_params_over_slots():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 3, 2, label="main")
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def bad_width_low():
    p = _plain()
    p.W = 7
    return p.image()


@case
def bad_stack_zero():
    p = _plain()
    p.S = 0
    return p.image()


@case
def bad_frames_zero():
    p = _plain()
    p.D = 0
    return p.image()


@case
def bad_short_header():
    return _plain().image()[:13]


@case
def bad_unknown_tag():
    p = P(W=16)
    p.func("main", 0, 0)
    p.consts.append(("raw", b"\x02\x01"))
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def bad_no_functions():
    img = _plain().image()
    # rebuild with a function count of 0: header, K=0, N=0, then the code
    code = b"\x01\x02\x50\x00"
    return img[:14] + b"\x00" + b"\x00" + bytes([len(code)]) + code


@case
def bad_code_missing():
    return _plain().image()[:-1]


@case
def bad_varint_too_long():
    p = P(W=16)
    p.func("main", 0, 0)
    p.consts.append(("raw", b"\x00" + b"\x80" * 10 + b"\x00"))
    p.label("main")
    p.ops("HALT")
    return p.image()


# ---------------------------------------------------------------- integers
@case
def int_reduce_w16():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(70000)
    p.label("main")
    p.ops("PUSHI:30000 PUSHI:30000 ADD PRINT PUSHI:70000 PRINT PUSHK:0 PRINT "
          "PUSHI:300 PUSHI:300 MUL PRINT PUSHI:-32768 PUSHI:1 SUB PRINT HALT")
    return p.image()


@case
def int_floor_div_mod():
    p = P(W=32)
    p.func("main", 0, 0)
    p.label("main")
    for a, b in [(-7, 2), (7, -2), (-7, -2), (7, 2), (-8, 2), (-1, 5)]:
        p.ops(f"PUSHI:{a} PUSHI:{b} DIV PRINT PUSHI:{a} PUSHI:{b} MOD PRINT")
    p.ops("HALT")
    return p.image()


@case
def int_min_over_minus_one():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:-32768 PUSHI:-1 DIV PRINT PUSHI:-32768 PUSHI:-1 MOD PRINT "
          "PUSHI:-32768 NEG PRINT PUSHI:-32768 PUSHI:-1 MUL PRINT HALT")
    return p.image()


@case
def int_divzero_uncaught():
    p = P(W=32)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:5 PRINT PUSHI:9 PUSHI:0 MOD PRINT HALT")
    return p.image()


@case
def int_bitwise_negative():
    p = P(W=12)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:-6 PUSHI:13 AND PRINT PUSHI:-6 PUSHI:13 OR PRINT PUSHI:-6 PUSHI:-13 XOR PRINT "
          "PUSHI:2047 PUSHI:-2048 XOR PRINT HALT")
    return p.image()


@case
def shift_large_counts():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:3 PUSHI:16 SHL PRINT PUSHI:3 PUSHI:17 SHL PRINT PUSHI:-5 PUSHI:20 SHR PRINT "
          "PUSHI:5 PUSHI:16 SHR PRINT PUSHI:-5 PUSHI:16 USHR PRINT PUSHI:1 PUSHI:-1 SHL PRINT "
          "PUSHI:-1 PUSHI:-16 SHR PRINT PUSHI:3 PUSHI:15 SHL PRINT HALT")
    return p.image()


@case
def shift_unsigned_right():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:-1 PUSHI:0 USHR PRINT PUSHI:-1 PUSHI:1 USHR PRINT PUSHI:-32768 PUSHI:15 USHR PRINT "
          "PUSHI:-4 PUSHI:0 USHR PRINT PUSHI:-9 PUSHI:2 SHR PRINT HALT")
    return p.image()


@case
def cmp_unsigned():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:-1 PUSHI:1 ULT PRINT PUSHI:1 PUSHI:-1 ULT PRINT PUSHI:-1 PUSHI:1 LT PRINT "
          "PUSHI:-32768 PUSHI:32767 ULT PRINT PUSHI:4 PUSHI:4 ULT PRINT HALT")
    return p.image()


@case
def cmp_eq_mixed_types():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"5")
    p.const(b"")
    p.label("main")
    p.ops("PUSHK:0 PUSHI:5 EQ PRINT PUSHI:0 PUSHK:1 EQ PRINT PUSHK:0 PUSHK:0 EQ PRINT "
          "PUSHI:65541 PUSHI:5 EQ PRINT HALT")
    return p.image()


@case
def cmp_lt_strings():
    p = P(W=16)
    p.func("main", 0, 0)
    for s in [b"a", b"\x80", b"ab", b"abc", b"", b"b\x00", b"b"]:
        p.const(s)
    p.label("main")
    for i, j in [(0, 1), (1, 0), (2, 3), (3, 2), (4, 0), (5, 6), (6, 5), (2, 2)]:
        p.ops(f"PUSHK:{i} PUSHK:{j} LT PRINT")
    p.ops("HALT")
    return p.image()


@case
def cmp_lt_mixed_raises():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"7")
    p.label("main")
    p.ops("PUSHI:1 PUSHK:0 PUSHI:9 LT PRINT PRINT HALT")
    return p.image()


# ---------------------------------------------------------------- strings
@case
def str_cat_integers():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"ab")
    p.label("main")
    p.ops("PUSHI:12 PUSHK:0 CAT PRINT PUSHK:0 PUSHI:-40 CAT PRINT PUSHI:-5 PUSHI:-6 CAT PRINT "
          "PUSHI:0 PUSHI:0 CAT PUSHI:1 ADD PRINT HALT")
    return p.image()


@case
def str_cat_limit():
    p = P(W=16, L=6)
    p.func("main", 0, 0)
    p.const(b"abc")
    p.label("main")
    p.ops("PUSHK:0 PUSHK:0 CAT PRINT")
    guarded(p, "PUSHK:0 PUSHI:1234 CAT PRINT", "a")
    p.ops("HALT")
    return p.image()


@case
def str_slice_rules():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"validator")
    p.label("main")
    for s, c in [(2, 3), (-3, 2), (-20, 4), (7, 10), (9, 1), (40, 2), (3, 0)]:
        p.ops(f"PUSHK:0 PUSHI:{s} PUSHI:{c} SLICE PRINT")
    guarded(p, "PUSHK:0 PUSHI:1 PUSHI:-1 SLICE PRINT", "a")
    p.ops("HALT")
    return p.image()


@case
def str_byte_and_len_reduce():
    p = P(W=8, L=300)
    p.func("main", 0, 0)
    p.const(b"\xc8\x7f\x80")
    p.const(b"x" * 200)
    p.label("main")
    p.ops("PUSHK:0 PUSHI:0 BYTE PRINT PUSHK:0 PUSHI:1 BYTE PRINT PUSHK:0 PUSHI:2 BYTE PRINT "
          "PUSHK:1 LEN PRINT PUSHK:1 LEN PUSHI:0 LT PRINT")
    guarded(p, "PUSHK:0 PUSHI:3 BYTE PRINT", "a")
    guarded(p, "PUSHK:0 PUSHI:-1 BYTE PRINT", "b")
    p.ops("HALT")
    return p.image()


@case
def str_chr_range():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:0 CHR PRINT PUSHI:255 CHR PRINT PUSHI:65 CHR PRINT")
    guarded(p, "PUSHI:256 CHR PRINT", "a")
    guarded(p, "PUSHI:-1 CHR PRINT", "b")
    p.ops("HALT")
    return p.image()


@case
def str_str_limit():
    p = P(W=16, L=4)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:9999 STR PRINT PUSHI:-999 STR PRINT")
    guarded(p, "PUSHI:-1234 STR PRINT", "a")
    guarded(p, "PUSHI:10000 STR PRINT", "b")
    p.ops("HALT")
    return p.image()


@case
def str_num_parse():
    p = P(W=16)
    p.func("main", 0, 0)
    good = [b"007", b"-0", b"65537", b"-32769", b"123456789012345678901234567890"]
    bad = [b"+5", b"", b"-", b"12a", b" 1", b"1-"]
    for s in good + bad:
        p.const(s)
    p.label("main")
    for i in range(len(good)):
        p.ops(f"PUSHK:{i} NUM PRINT")
    for j in range(len(bad)):
        guarded(p, f"PUSHK:{len(good) + j} NUM PRINT", f"n{j}")
    p.ops("HALT")
    return p.image()


@case
def str_print_escapes():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"a\\b ~\x7f\x1f\x00\xff\"'\n")
    p.const(b"")
    p.label("main")
    p.ops("PUSHK:0 PRINT PUSHK:1 PRINT PUSHI:-0 PRINT HALT")
    return p.image()


@case
def str_type_errors():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"ab")
    p.label("main")
    guarded(p, "PUSHK:0 PUSHI:1 ADD PRINT", "a")
    guarded(p, "PUSHI:5 LEN PRINT", "b")
    guarded(p, "PUSHI:3 PUSHI:0 PUSHI:1 SLICE PRINT", "c")
    guarded(p, "PUSHK:0 NEG PRINT", "d")
    guarded(p, "PUSHK:0 JZ:d_d", "e")
    guarded(p, "PUSHK:0 PUSHI:-1 CHR PRINT", "f")
    guarded(p, "PUSHI:1 PUSHK:0 ULT PRINT", "g")
    p.ops("HALT")
    return p.image()


# ---------------------------------------------------------------- stack
@case
def stack_overflow_fault():
    p = P(W=16, S=3)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PUSHI:2 PUSHI:3 PRINT PUSHI:4 DUP DUP PRINT HALT")
    return p.image()


@case
def stack_frame_base():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 1, 1)
    p.label("main")
    p.ops("PUSHI:7 PUSHI:8 PUSHI:9 CALL:f PRINT HALT")
    p.label("f")
    p.ops("POP POP HALT")
    return p.image()


@case
def stack_pick():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 1, 1)
    p.label("main")
    p.ops("PUSHI:10 PUSHI:20 PUSHI:30 PICK:0 PRINT PICK:2 PRINT PUSHI:5 CALL:f PRINT HALT")
    p.label("f")
    p.ops("PUSHI:1 PICK:0 PRINT PICK:1 PRINT RET")
    return p.image()


@case
def stack_swap_order():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:10 PUSHI:3 SWAP SUB PRINT PUSHI:10 PUSHI:3 SWAP DIV PRINT HALT")
    return p.image()


# ---------------------------------------------------------------- calls
@case
def call_argument_slots():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 3, 5)
    p.label("main")
    p.ops("PUSHI:1 PUSHI:2 PUSHI:3 CALL:f PRINT HALT")
    p.label("f")
    p.ops("LOAD:0 PRINT LOAD:2 PRINT LOAD:4 PRINT LOAD:0 PUSHI:100 MUL LOAD:1 PUSHI:10 MUL ADD LOAD:2 ADD RET")
    return p.image()


@case
def call_depth_limit():
    p = P(W=16, D=4)
    p.func("main", 0, 0)
    p.func("rec", 1, 1)
    p.label("main")
    guarded(p, "PUSHI:1 CALL:rec PRINT", "a")
    p.ops("HALT")
    p.label("rec")
    p.ops("LOAD:0 PRINT LOAD:0 PUSHI:1 ADD CALL:rec RET")
    return p.image()


@case
def call_ret_cleans_stack():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 CALL:f PRINT PRINT HALT")
    p.label("f")
    p.ops("PUSHI:5 PUSHI:6 PUSHI:7 PUSHI:8 RET")
    return p.image()


@case
def call_ret_drops_handlers():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 0)
    p.const(b"outer")
    p.label("main")
    p.ops("TRY:hm CALL:f PRINT PUSHI:3 THROW HALT hm: PRINT PUSHI:4 THROW")
    p.label("f")
    p.ops("TRY:hf PUSHI:9 RET hf: PUSHK:0 PRINT PUSHI:0 RET")
    return p.image()


@case
def call_ret_in_entry():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PRINT PUSHI:2 RET")
    return p.image()


# ---------------------------------------------------------------- handlers
@case
def raise_cuts_stack():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 TRY:h PUSHI:2 PUSHI:3 PUSHI:4 PUSHI:0 DIV h: PRINT PRINT PUSHI:77 HALT")
    return p.image()


@case
def raise_across_frames():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 1)
    p.func("g", 0, 0)
    p.const(b"card blocked")
    p.label("main")
    p.ops("PUSHI:5 TRY:h CALL:f PRINT HALT h: PRINT PUSHI:6 PRINT HALT")
    p.label("f")
    p.ops("PUSHI:9 PUSHI:9 CALL:g RET")
    p.label("g")
    p.ops("PUSHI:1 PUSHK:0 THROW")
    return p.image()


@case
def raise_handler_no_room():
    p = P(W=16, S=2, D=1)
    p.func("main", 0, 0)
    p.func("f", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PUSHI:2 TRY:h CALL:f h: PRINT HALT")
    p.label("f")
    p.ops("PUSHI:0 RET")
    return p.image()


@case
def raise_pops_operands():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:7 PUSHI:0 TRY:h DIV h: PRINT PUSHI:5 TRY:g THROW g: PRINT HALT")
    return p.image()


@case
def raise_stack_below_record():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PUSHI:2 PUSHI:3 TRY:h POP POP PUSHI:0 NEG PUSHI:0 DIV h: PRINT PRINT HALT")
    return p.image()


@case
def raise_endtry_none():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("TRY:h ENDTRY PUSHI:1 PRINT ENDTRY h: HALT")
    return p.image()


@case
def raise_nested_handlers():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("TRY:outer TRY:inner PUSHI:1 THROW inner: PRINT PUSHI:2 THROW outer: PRINT "
          "PUSHI:3 THROW")
    return p.image()


@case
def raise_endtry_other_frame():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 0)
    p.label("main")
    p.ops("TRY:h CALL:f HALT h: HALT")
    p.label("f")
    p.ops("PUSHI:1 PRINT ENDTRY PUSHI:0 RET")
    return p.image()


@case
def raise_uncaught_string():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"bad\\zone\x07")
    p.label("main")
    p.ops("PUSHI:1 PRINT PUSHK:0 THROW")
    return p.image()


@case
def raise_jz_on_string():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"0")
    p.label("main")
    p.ops("PUSHI:0 JZ:a PUSHI:111 PRINT a: PUSHK:0 JZ:b PUSHI:222 PRINT b: HALT")
    return p.image()


# ---------------------------------------------------------------- ticks
def ticks_needed(p):
    import re

    from fvm_model import run
    keep = p.F
    p.F = 2 ** 32 - 1
    t = int(re.search(rb"ticks=(\d+)", run(p.image())).group(1))
    p.F = keep
    return t


def _count_prog(delta):
    p = P(W=16)
    p.func("main", 0, 1)
    p.label("main")
    p.ops("top: LOAD:0 PRINT LOAD:0 PUSHI:1 ADD DUP STORE:0 PUSHI:3 LT JNZ:top HALT")
    p.F = ticks_needed(p) + delta
    return p


@case
def tick_budget_exact():
    return _count_prog(0).image()   # exactly enough


@case
def tick_budget_short():
    return _count_prog(-1).image()


@case
def tick_print_escaped_cost():
    p = P(W=16, F=6)
    p.func("main", 0, 0)
    p.const(b"\x01\x02\x03\x04")   # written as 16 bytes -> PRINT costs 3
    p.label("main")
    p.ops("PUSHK:0 PRINT PUSHI:1 PRINT HALT")
    return p.image()


@case
def tick_cat_whole_eights():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"abcdefg")   # 7
    p.label("main")
    p.ops("PUSHK:0 PUSHI:1 CAT PUSHK:0 PUSHI:12 CAT CAT DUP PRINT PUSHK:0 PUSHK:0 CAT PRINT HALT")
    return p.image()


@case
def tick_call_cost():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 6)
    p.label("main")
    p.ops("CALL:f PRINT CALL:f PRINT HALT")
    p.label("f")
    p.ops("PUSHI:4 RET")
    return p.image()


@case
def tick_raise_costs_one():
    p = P(W=16, D=1, F=5)
    p.func("main", 0, 0)
    p.func("f", 0, 9)
    p.label("main")
    p.ops("TRY:h CALL:f h: PRINT HALT")
    p.label("f")
    p.ops("PUSHI:0 RET")
    return p.image()


# ---------------------------------------------------------------- code faults
@case
def code_branch_exact():
    p = P(W=8)
    p.func("main", 0, 0)
    p.label("main")
    p.op("JMP", "far")
    p.ops("PUSHI:1 PRINT HALT")
    for _ in range(100):
        p.ops("PUSHI:2 PRINT")
    p.ops("far: PUSHI:3 PRINT HALT")
    return p.image()


@case
def code_jump_outside():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PRINT JMP:40 HALT")
    return p.image()


@case
def code_unknown_opcode():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PUSHI:0 JZ:x")
    p.raw(b"\x07")
    p.ops("x: PRINT")
    p.raw(b"\x07")
    return p.image()


@case
def code_truncated_operand():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:5 PRINT")
    p.raw(b"\x01\x80")
    return p.image()


@case
def code_index_ranges():
    p = P(W=16)
    p.func("main", 0, 2)
    p.const(1)
    p.label("main")
    p.ops("PUSHK:0 PRINT LOAD:1 PRINT STORE:2")
    return p.image()


@case
def code_operand_too_long():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:4 PRINT")
    p.raw(b"\x01" + b"\x80" * 10 + b"\x00")
    p.ops("PRINT HALT")
    return p.image()


@case
def code_pushk_index():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"k0")
    p.const(b"k1")
    p.label("main")
    p.ops("PUSHK:1 PRINT PUSHK:2 PRINT HALT")
    return p.image()


@case
def code_call_index():
    p = P(W=16)
    p.func("main", 0, 0)
    p.func("f", 0, 0)
    p.label("main")
    p.ops("CALL:1 PRINT CALL:2 PRINT HALT")
    p.label("f")
    p.ops("PUSHI:8 RET")
    return p.image()


@case
def str_types_first():
    p = P(W=16, L=0)
    p.func("main", 0, 0)
    p.const(b"")
    p.label("main")
    guarded(p, "PUSHI:3 PUSHI:0 PUSHI:-1 SLICE PRINT", "a")
    guarded(p, "PUSHI:3 PUSHI:-1 BYTE PRINT", "b")
    guarded(p, "PUSHK:0 CHR PRINT", "c")
    guarded(p, "PUSHI:65 CHR PRINT", "d")
    guarded(p, "PUSHI:300 CHR PRINT", "e")
    p.ops("HALT")
    return p.image()


@case
def order_index_before_stack():
    p = P(W=16)
    p.func("main", 0, 1)
    p.label("main")
    p.ops("PUSHI:3 STORE:0 LOAD:0 PRINT STORE:5")
    return p.image()


@case
def order_stack_before_depth():
    p = P(W=16, D=1)
    p.func("main", 0, 0)
    p.func("f", 2, 2)
    p.label("main")
    p.ops("TRY:h PUSHI:1 CALL:f HALT h: PRINT HALT")
    p.label("f")
    p.ops("HALT")
    return p.image()


@case
def order_room_before_ticks():
    p = P(W=16, S=2, F=2)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:5 PUSHI:6 DUP HALT")
    return p.image()


@case
def order_raise_needs_tick():
    p = P(W=16, F=2)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PUSHI:0 DIV HALT")
    return p.image()
