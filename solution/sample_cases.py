"""The sample conformance suite: one image per stated rule, each the hard case of that rule."""
from fvm_asm import Prog, uvar


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
    p.ops("PUSHK:0 PRINT LOAD:1 PRINT PUSHI:9 STORE:2 HALT")
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


# ---------------------------------------------------------------- limits and encodings
@case
def img_bad_magic_prefix():
    img = bytearray(_plain().image())
    img[0] = 0x47
    return bytes(img)


@case
def img_stack_limit_one():
    p = P(W=16, S=1)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:7 PRINT PUSHI:5 HALT")
    return p.image()


@case
def img_frame_limit_wide():
    p = P(W=16, D=200)
    p.func("main", 0, 0)
    p.func("rec", 1, 1)
    p.label("main")
    guarded(p, "PUSHI:1 CALL:rec", "a")
    p.ops("HALT")
    p.label("rec")
    p.ops("LOAD:0 PUSHI:1 ADD CALL:rec RET")
    return p.image()


@case
def img_string_256():
    p = P(W=16, L=256)
    p.func("main", 0, 0)
    p.const(b"fare" * 63 + b"cap!")
    p.label("main")
    p.ops("PUSHK:0 PRINT PUSHK:0 LEN PRINT HALT")
    return p.image()


@case
def img_many_constants():
    p = P(W=16)
    p.func("main", 0, 0)
    for i in range(65):
        p.const(3 * i + 1)
    p.label("main")
    p.ops("PUSHK:64 PRINT PUSHK:0 PRINT HALT")
    return p.image()


@case
def img_stack_limit_high_byte():
    p = P(W=16, S=256)
    p.func("main", 0, 0)
    p.label("main")
    p.ops(" ".join(f"PUSHI:{k % 90}" for k in range(1, 257)) + " PRINT PUSHI:5 DUP HALT")
    return p.image()


@case
def tick_budget_zero():
    p = P(W=8, F=0, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def img_string_257():
    p = P(W=16, L=257)
    p.func("main", 0, 0)
    p.const(b"zone" * 64 + b"!")
    p.label("main")
    p.ops("PUSHK:0 PRINT PUSHK:0 LEN PRINT HALT")
    return p.image()


@case
def img_many_functions():
    p = P(W=16)
    p.func("main", 0, 0)
    for i in range(1, 20):
        p.func(f"f{i}", 0, 0)
    p.label("main")
    p.ops("CALL:19 PRINT CALL:16 PRINT HALT")
    for i in range(1, 20):
        p.label(f"f{i}")
        p.ops(f"PUSHI:{10 * i} RET")
    return p.image()


@case
def img_varint_ten_bytes():
    p = P(W=16)
    p.func("main", 0, 0)
    p.consts.append(("raw", b"\x00" + uvar((1 << 63) + 2 * 12345)))   # ten bytes, 2^62 + 12345
    p.label("main")
    p.ops("PUSHK:0 PRINT HALT")
    return p.image()


@case
def img_zigzag_max():
    p = P(W=8)
    p.func("main", 0, 0)
    p.consts.append(("raw", b"\x00" + b"\xff" * 9 + b"\x01"))   # u = 2^64 - 1, value -2^63
    p.consts.append(("raw", b"\x00" + b"\xfd" + b"\xff" * 8 + b"\x01"))   # u = 2^64 - 3
    p.label("main")
    p.ops("PUSHK:0 PRINT PUSHK:1 PRINT HALT")
    return p.image()


@case
def stack_underflow_not_caught():
    p = P(W=16, S=2)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("TRY:h POP h: PUSHI:1 PRINT HALT")
    return p.image()


@case
def code_operand_ten_bytes_too_large():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:4 PRINT")
    p.raw(b"\x01" + b"\x80" * 9 + b"\x02")
    p.ops("PRINT HALT")
    return p.image()


@case
def raise_many_handlers():
    p = P(W=16)
    p.func("main", 0, 0)
    p.label("main")
    p.ops(" ".join(f"TRY:h{k}" for k in range(1, 18)) + " PUSHI:0 THROW")
    for k in range(1, 18):
        p.ops(f"h{k}: PRINT PUSHI:{k} PRINT HALT")
    return p.image()


@case
def img_entry_offset_nonzero():
    p = P(W=16)
    p.func("main", 0, 0)
    p.ops("HALT main: PUSHI:6 PRINT HALT")
    return p.image()


@case
def call_depth_keeps_arguments():
    p = P(W=16, D=1)
    p.func("main", 0, 0)
    p.func("f", 1, 1)
    p.label("main")
    p.ops("PUSHI:42 TRY:h CALL:f HALT h: PRINT PRINT HALT")
    p.label("f")
    p.ops("HALT")
    return p.image()


# ---------------------------------------------------------------- round 3: capacities and exact targets
@case
def img_budget_high_bit():
    p = P(W=8, F=0x80000000, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("HALT")
    return p.image()


@case
def img_large_tables():
    p = P(W=16, L=1025)
    for i in range(129):
        p.const(i)
    p.const(b"a" * 1025)
    p.func("main", 0, 0)
    for i in range(1, 33):
        p.func(f"f{i}", 0, 0, label="f32" if i == 32 else "main")
    p.raw(b"\xff" * 2048)   # never fetched: the entry is at 2048
    p.label("main")
    p.ops("PUSHK:128 PRINT PUSHK:129 LEN PRINT CALL:32 PRINT HALT f32: PUSHI:32 RET")
    return p.image()


@case
def run_large_limits():
    p = P(W=16, S=129, D=65)
    p.func("main", 0, 33)
    p.func("rec", 1, 1)
    p.label("main")
    p.ops("LOAD:32 PRINT PUSHI:1 CALL:rec PRINT " + "PUSHI:0 " * 129 + "HALT")
    p.ops("rec: LOAD:0 PUSHI:64 LT JZ:top LOAD:0 PUSHI:1 ADD CALL:rec RET top: LOAD:0 RET")
    return p.image()


@case
def img_constant_body_short():
    return bytes.fromhex("46564d0208000000000100010100010101")


@case
def str_chr_limit_zero():
    p = P(W=8, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:65 CHR HALT")
    return p.image()


@case
def code_load_index():
    p = P(W=8, F=10, S=2, D=1, L=0)
    p.func("main", 0, 1)
    p.label("main")
    p.ops("LOAD:1 HALT")
    return p.image()


@case
def tick_print_denied():
    p = P(W=8, F=1, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHI:1 PRINT HALT")
    return p.image()


@case
def branch_target_exact():
    p = P(W=8, F=10, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.op("JMP", (1 << 63) - 1)
    p.ops("HALT")
    return p.image()


@case
def branch_target_exact_near():
    p = P(W=8, F=2, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.op("JMP", (1 << 63) - 10)
    return p.image()


@case
def handler_target_exact():
    p = P(W=8, F=10, S=2, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.op("TRY", (1 << 63) - 3)
    p.ops("PUSHI:7 THROW")
    return p.image()


# ---------------------------------------------------------------- round 4: each header quantity at its stated maximum
@case
def img_stack_max():
    p = P(W=8, F=65536, S=65535, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.raw(b"\x01\x00" * 65535)   # 65535 x PUSHI 0
    p.ops("HALT")
    return p.image()


@case
def run_frames_max():
    p = P(W=16, D=255)
    p.func("main", 0, 0)
    p.func("rec", 1, 1)
    p.label("main")
    guarded(p, "PUSHI:1 CALL:rec", "a")
    p.ops("HALT rec: LOAD:0 PUSHI:1 ADD CALL:rec RET")
    return p.image()


@case
def img_string_max():
    p = P(W=32, S=2, D=1, L=65535)
    p.const(b"a" * 65534 + b"z")
    p.func("main", 0, 0)
    p.label("main")
    p.ops("PUSHK:0 LEN PRINT PUSHK:0 PUSHI:65534 BYTE PRINT HALT")
    return p.image()


def many_consts(k):
    p = P(W=16, S=1, D=1, L=0)
    for _ in range(k - 1):
        p.const(0)
    p.const(7)
    p.func("main", 0, 0)
    p.label("main")
    p.ops(f"PUSHK:{k - 1} PRINT HALT")
    return p.image()


def many_funcs(n):
    p = P(W=16, S=1, D=2, L=0)
    p.func("main", 0, 0)
    for i in range(1, n - 1):
        p.func(f"g{i}", 0, 0, label="main")
    p.func("f", 0, 0)
    p.label("main")
    p.ops(f"CALL:{n - 1} PRINT HALT f: PUSHI:7 RET")
    return p.image()


def big_code(c):
    p = P(W=16, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.raw(b"\xff" * (c - 4))     # never fetched: the entry is in the last four bytes
    p.label("main")
    p.ops("PUSHI:5 PRINT HALT")
    img = p.image()
    assert len(p.assemble_code()) == c
    return img


@case
def img_consts_max():
    return many_consts(65535)


@case
def img_funcs_max():
    return many_funcs(65535)


@case
def img_code_max():
    return big_code(1 << 20)


@case
def run_slots_max():
    p = P(W=16, S=1, D=1, L=0)
    p.func("main", 0, 255)
    p.label("main")
    p.ops("LOAD:254 PRINT PUSHI:9 STORE:254 LOAD:254 PRINT HALT")
    return p.image()


@case
def img_consts_over():
    return many_consts(65536)


@case
def img_funcs_over():
    return many_funcs(65536)


@case
def img_code_over():
    return big_code((1 << 20) + 1)


# ---------------------------------------------------------------- round 5: advisory boundary cases
@case
def img_varint_ten_bytes_redundant():
    p = P(W=8, F=1, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("HALT")
    img = p.image()
    assert img[14] == 0x00                         # K = 0, written in ten bytes below
    return img[:14] + b"\x80" * 9 + b"\x00" + img[15:]


@case
def cmp_ult_string_left():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"ab")
    p.label("main")
    guarded(p, "PUSHK:0 PUSHI:1 ULT PRINT", "a")
    p.ops("HALT")
    return p.image()


@case
def raise_jnz_on_string():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"1")
    p.label("main")
    guarded(p, "PUSHK:0 JNZ:d_a PUSHI:7 PRINT", "a")
    p.ops("HALT")
    return p.image()


# ---------------------------------------------------------------- round 6: middle magic bytes, SLICE's eighth byte
@case
def bad_magic_second_byte():
    img = bytearray(_plain().image())
    img[1] = 0x58
    return bytes(img)


@case
def bad_magic_third_byte():
    img = bytearray(_plain().image())
    img[2] = 0x4E
    return bytes(img)


@case
def tick_slice_whole_eight():
    p = P(W=16)
    p.func("main", 0, 0)
    p.const(b"abcdefgh")
    p.label("main")
    p.ops("PUSHK:0 PUSHI:0 PUSHI:8 SLICE PRINT HALT")
    return p.image()


# ---------------------------------------------------------------- round 7: error names past L, zero budget after decode
@case
def str_error_name_past_limit():
    p = P(W=16, L=2)
    p.func("main", 0, 0)
    p.label("main")
    guarded(p, "PUSHI:1 PUSHI:0 DIV PRINT", "a")
    p.ops("TRY:n PUSHI:1 PUSHI:0 DIV ENDTRY n: PUSHI:0 PUSHI:7")
    guarded(p, "SLICE PRINT", "s")
    p.ops("HALT")
    return p.image()


@case
def tick_budget_zero_bad_opcode():
    p = P(W=8, F=0, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.raw(b"\x07")
    return p.image()


# ---------------------------------------------------------------- round 8: a FUEL fault with a handler installed
@case
def tick_fuel_skips_handler():
    p = P(W=8, F=1, S=2, D=1, L=8)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("TRY:h HALT h: PRINT HALT")
    return p.image()


# ---------------------------------------------------------------- round 10: 33 handlers, no fixed depth below that
@case
def try_thirty_three_handlers():
    """33 TRY instructions, each 3 bytes (opcode + a two-byte LEB128 displacement, redundant
    wherever the value alone would fit one byte), all targeting the final HALT. THROW then
    raises past all of them to the innermost. No visible image before this one shows a handler
    stack past a small fixed size, so an interpreter capped at 32 entries reads this image wrong."""
    p = P(W=8, F=1000, S=2, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    code = bytearray()
    for i in range(33):
        s = 99 - 3 * i
        u = 2 * s
        code += bytes([0x38, (u & 0x7F) | 0x80, (u >> 7) & 0x7F])
    code += bytes([0x01, 0x0E])  # PUSHI 7
    code += bytes([0x3A])        # THROW
    code += bytes([0x00])        # HALT
    p.raw(bytes(code))
    return p.image()


# ---------------------------------------------------------------- round 11: past every header field's own maximum
@case
def try_seventy_thousand_handlers():
    """70,000 TRY instructions, each the two bytes 38 00 (TRY with a zero displacement), never
    unwound and never thrown into, then HALT. 70,000 is past 65535, the largest maximum any
    header field states (S, L, K and N), so no plausible fixed handler-stack array holds it
    either; the sheet's own bound on the handler stack is the code, not a number. Ticks: one
    per TRY plus one for HALT; the operand stack never moves."""
    p = P(W=8, F=70001, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.raw(b"\x38\x00" * 70000 + b"\x00")
    return p.image()


# ---------------------------------------------------------------- round 12: past the array cap, thrown into
@case
def try_65537_handlers_innermost_marked():
    """65,537 TRY handlers, one past a 65,536-entry array. The first 65,536 all target a HALT
    that never prints; the last one installed (the innermost) targets a distinct address that
    prints the thrown value and halts. A THROW then must reach that innermost handler, so an
    interpreter that caps the handler array at 65,536 entries and silently drops the last
    install answers with the other, unmarked HALT instead."""
    p = P(W=8, S=2, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    for _ in range(65536):
        p.op("TRY", "other")
    p.op("TRY", "marker")
    p.op("PUSHI", 7)
    p.op("THROW")
    p.label("other")
    p.op("HALT")
    p.label("marker")
    p.op("PRINT")
    p.op("HALT")
    p.F = ticks_needed(p)
    return p.image()


# ---------------------------------------------------------------- round 12: the stated maximum tick budget
@case
def tick_budget_max_unsigned():
    """F at the top of its stated range, the unsigned 32-bit value 0xffffffff, on a run that
    only needs one tick. Nothing on the sheet bounds F below that, so an image at the exact
    maximum has to run, not fault."""
    p = P(W=8, F=0xFFFFFFFF, S=1, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.ops("HALT")
    return p.image()


# ---------------------------------------------------------------- round 13: the series closes at the
# sheet's own maximum: FVM2.txt:23-24 bounds code at 1,048,576 bytes and a TRY is at least two bytes
# (opcode plus a one-byte LEB128 displacement), so no image can install more handlers than the code
# leaves room for once a value has to be pushed, thrown and caught. 524,285 TRY instructions (each
# "38 00", displacement 0, never thrown into) plus one more TRY targeting the closing block, PUSHI 7,
# THROW, PRINT, HALT: 524,286 installs total, code padded with one redundant LEB128 byte on the PUSHI
# operand to sit at exactly 1,048,576 bytes, the sheet's own code maximum. No fixed-size handler array,
# whatever its capacity, can ever hold more than this image installs.
@case
def try_max_code_handlers():
    from fvm_asm import padded, svar

    n = 524285
    code = bytearray()
    code += bytes([0x01]) + padded(svar(7), 1)   # PUSHI 7, padded to 3 bytes
    code += b"\x38\x00" * (n - 1)                 # n - 1 self-targeting TRY, 2 bytes each
    code += bytes([0x38, 0x02])                   # last TRY -> the block below (s = 1)
    code += bytes([0x3A])                          # THROW
    code += bytes([0x50])                          # PRINT
    code += bytes([0x00])                          # HALT
    assert len(code) == 1048576
    p = P(W=8, S=2, D=1, L=0)
    p.func("main", 0, 0)
    p.label("main")
    p.raw(bytes(code))
    p.F = ticks_needed(p)
    return p.image()


# ---------------------------------------------------------------- round 13: PUSHK index masked to W
@case
def img_pushk_index_not_masked():
    """W=8 and 257 constants, indices 0 and 256 holding different values. PUSHK 256 is a legal,
    in-range uvarint index (Length(Consts) = 257): an interpreter that masks every decoded operand
    to the word width would select constant 0 instead, since 256 and 255 = 0."""
    p = P(W=8)
    p.func("main", 0, 0)
    p.const(1)
    for _ in range(255):
        p.const(0)
    p.const(42)
    p.label("main")
    p.ops("PUSHK:256 PRINT HALT")
    return p.image()


# ---------------------------------------------------------------- round 13: EOF inside the function table
@case
def bad_functions_truncated():
    """A valid 14-byte header, K=0, N=1, and then only the entry function's offset uvarint before
    EOF: no P, no V, no code. Section 1 requires the one-line -- bad image transcript for data
    missing after N is declared; this is the hard case the sample corpus was missing."""
    h = _plain().image()[:14]
    return h + b"\x00" + b"\x01" + b"\x00"


# ---------------------------------------------------------------- round 13: PARSE on an empty string, L=0
@case
def num_empty_string_parse():
    """NUM on an empty string constant with L=0: the grammar needs one or more digits, so this
    raises PARSE, and PARSE is raised as its full name whatever L is (section 2), not clipped by
    the string limit that bounds ordinary string values."""
    p = P(W=8, L=0)
    p.func("main", 0, 0)
    p.const(b"")
    p.label("main")
    guarded(p, "PUSHK:0 NUM", "e")
    p.ops("HALT")
    return p.image()


# ---------------------------------------------------------------- round 14: unknown opcode under an
# installed handler must still fault CODE, not be delivered to the handler
@case
def code_unknown_opcode_under_handler():
    """A handler is installed (TRY +2, targeting the PRINT below) before the fetch that hits an
    unassigned opcode. Section 5 makes an unknown opcode a CODE fault, and CODE is a terminal
    fault, not a raise: it must stop the run at the point of the bad fetch, never unwind into a
    handler that happens to be on the stack. An interpreter whose opcode dispatch default falls
    through the same path as THROW instead prints 'CODE' and halts."""
    p = P(W=8, F=10, S=2, D=1, L=8)
    p.func("main", 0, 0)
    p.label("main")
    p.raw(bytes.fromhex("3802075000"))  # TRY +2; unknown 07; PRINT; HALT
    return p.image()


# ---------------------------------------------------------------- round 16: an empty image is a
# short image too, and the permitted P=255 parameter-count endpoint
@case
def bad_empty_image():
    """A zero-byte file. Section 1 makes a short image (any length under the 14-byte header)
    produce exactly '-- bad image', with no exception for the shortest case of all. The nearest
    shipped fixture, bad_short_header, is 13 bytes and already has the full four-byte magic; a
    parser that reads the magic before checking the file length passes that case and this one is
    the one the suite was missing."""
    return b""


@case
def call_param_count_max():
    """S=255, D=2. Function 0 (P=0) pushes the 255 arguments 0..254 in order and calls function 1
    (P=V=255), which loads slot 254 (the last argument, 254) and returns it; the caller prints it.
    P and V both go up to 255 (section 1); the shipped call_argument_slots case only reaches P=3
    and run_slots_max only reaches V=255 with P=0, so a parser that caps the parameter count below
    the sheet's own maximum was never exercised at the endpoint itself."""
    p = P(S=255, D=2)
    p.func("main", 0, 0)
    p.func("f", 255, 255)
    p.label("main")
    p.ops(" ".join(f"PUSHI:{i}" for i in range(255)))
    p.ops("CALL:f PRINT HALT")
    p.label("f")
    p.ops("LOAD:254 RET")
    return p.image()
