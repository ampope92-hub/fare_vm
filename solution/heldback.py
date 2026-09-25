"""Held-back images: programs that combine the rules, built for other validator generations."""
import random

from fvm_asm import Prog


def ints_for(rng, W):
    lo, hi = -(1 << (W - 1)), (1 << (W - 1)) - 1
    pool = [0, 1, -1, 2, -2, 3, -7, 7, 10, -10, lo, hi, lo + 1, hi - 1, W, W - 1, W + 1, -W,
            255, 256, -256, 1 << (W - 2), (1 << W) + 5, -(1 << W) - 3]
    return rng.choice(pool) if rng.random() < 0.6 else rng.randint(lo, hi)


def str_for(rng):
    kind = rng.random()
    if kind < 0.25:
        alphabet = b"0123456789"
        s = bytes(rng.choice(alphabet) for _ in range(rng.randint(1, 14)))
        pre = rng.choice([b"", b"", b"-", b"+", b" "])
        return pre + s
    if kind < 0.5:
        return bytes(rng.randint(0, 255) for _ in range(rng.randint(0, 9)))
    if kind < 0.75:
        return bytes(rng.choice(b"abz\\~ \x7f\x80\xc3\x00\x1f\x09Az") for _ in range(rng.randint(0, 12)))
    return rng.choice([b"", b"a", b"ab", b"abc", b"b", b"\xff", b"\x80a", b"a\x80", b"-", b"-0", b"00"])


class Fuzz:
    """Straight-line blocks, each one operation on chosen operands inside its own handler."""

    UN = ("NEG", "LEN", "CHR", "STR", "NUM", "PRINT")
    BIN = ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR", "SHL", "SHR", "USHR",
           "EQ", "LT", "ULT", "CAT", "BYTE")

    def __init__(self, rng, p):
        self.rng, self.p, self.n = rng, p, 0
        self.kcache = {}

    def push_int(self, v):
        r = self.rng.random()
        if r < 0.25:
            k = self.p.const(v)
            self.p.op("PUSHK", k)
        else:
            if r < 0.4:
                v += self.rng.choice([1, -1]) * (1 << self.p.W)  # PUSHI reduces
            self.p.op("PUSHI", v)

    def push_str(self, s):
        if len(s) > self.p.L:
            s = s[:self.p.L]
        k = self.p.const(s)
        self.p.op("PUSHK", k)

    def operand(self, want_int=True):
        rng = self.rng
        if (rng.random() < 0.85) == want_int:
            self.push_int(ints_for(rng, self.p.W))
        else:
            self.push_str(str_for(rng))

    def block(self):
        rng, p = self.rng, self.p
        t = f"b{self.n}"
        self.n += 1
        start = len(p.code)
        self.op_at = None
        r = rng.random()
        if r < 0.45:
            op = rng.choice(self.BIN)
            strish = op in ("EQ", "LT", "CAT", "BYTE")
            if op == "BYTE":
                self.push_str(str_for(rng))
                v = rng.choice([0, 1, 2, -1, 3, 8, 255]) if rng.random() < 0.7 else ints_for(rng, p.W)
                self.push_int(v)
            elif op in ("SHL", "SHR", "USHR"):
                self.operand(True)
                if op == "USHR":
                    self.push_int(rng.choice([0, 0, 0, 1, p.W - 1, p.W, -1]))
                else:
                    self.push_int(rng.choice([0, 0, 1, 3, p.W - 1, p.W, p.W + 1, -1, -p.W, 2 * p.W, 7]))
            else:
                self.operand(not strish or rng.random() < 0.5)
                self.operand(not strish or rng.random() < 0.5)
            self.op_at = len(p.code)
            p.op(op)
            p.op("PRINT")
        elif r < 0.7:
            op = rng.choice(self.UN)
            if op in ("LEN", "NUM"):
                self.operand(False)
            elif op == "CHR":
                self.push_int(rng.choice([0, 9, 65, 92, 127, 128, 255, 256, -1, 300]))
            else:
                self.operand(True)
            self.op_at = len(p.code)
            p.op(op)
            if op != "PRINT":
                p.op("PRINT")
        elif r < 0.82:
            self.operand(False)
            n = len(p.consts[-1]) if p.consts and isinstance(p.consts[-1], bytes) else 5
            self.push_int(rng.choice([0, 1, 2, -1, -2, -n, -n - 3, n, n + 2, ints_for(rng, p.W)]))
            self.push_int(rng.choice([0, 1, 2, 3, n, n + 5, -1, ints_for(rng, p.W)]))
            self.op_at = len(p.code)
            p.op("SLICE")
            p.op("PRINT")
        elif r < 0.9:
            self.operand(rng.random() < 0.5)
            self.op_at = len(p.code)
            p.op("THROW")
        else:
            self.operand(True)
            self.operand(rng.random() < 0.7)
            op = rng.choice(["SWAP", "DUP"])
            p.op(op)
            if op == "DUP":
                p.op("PRINT")
            p.op("PRINT")
            p.op("DUP")
            p.op("JZ", "z" + t)
            p.op("PRINT")
            p.op("JMP", "e" + t)
            p.label("z" + t)
            p.op("POP")
            p.label("e" + t)
        return self._close(t, start)

    def _close(self, t, start):
        p, rng = self.p, self.rng
        mode = rng.choice("AABBC")
        if mode == "C" and self.op_at is not None:
            # operands already on the stack when the handler is installed
            p.code.insert(self.op_at, ("TRY", "h" + t))
        elif mode == "B":
            # values pushed after the handler is installed, cut away if anything raises
            junk = rng.randint(1, 3)
            filler = [("PUSHI", ints_for(rng, p.W)) for _ in range(junk)]
            p.code[start:start] = [("TRY", "h" + t)] + filler
            for _ in range(junk):
                p.op("POP")
        else:
            p.code.insert(start, ("TRY", "h" + t))
        p.op("ENDTRY")
        p.op("JMP", "d" + t)
        p.label("h" + t)
        p.op("PRINT")
        p.label("d" + t)


def fuzz_image(seed, W, L, nblocks, in_call):
    rng = random.Random(seed)
    p = Prog(W=W, F=10 ** 7, S=48, D=6, L=L)
    p.func("main", 0, 0)
    fz = Fuzz(rng, p)
    if in_call:
        p.func("work", 2, 4)
        p.label("main")
        p.ops(f"PUSHI:{ints_for(rng, W)} PUSHI:{ints_for(rng, W)} CALL:work PRINT HALT")
        p.label("work")
        p.ops(f"PUSHI:{rng.randint(1000, 9999)} LOAD:0 PRINT LOAD:1 PRINT")
        for _ in range(nblocks):
            fz.block()
        p.ops("PRINT LOAD:0 LOAD:1 SUB RET")
    else:
        p.label("main")
        for _ in range(nblocks):
            fz.block()
        p.op("HALT")
    return p


def fare_image(seed, W, L):
    """Tap records: each byte is a tap; zone = byte mod k (floor), fares accumulate with a cap."""
    rng = random.Random(seed)
    p = Prog(W=W, F=10 ** 7, S=32, D=4, L=L)
    taps = bytes(rng.randint(0, 255) for _ in range(rng.randint(10, 18)))[:L]
    k = rng.choice([-7, 5, 6, -5, 9])
    mult = rng.choice([31, 37, 131, 1021])
    cap = ints_for(rng, W)
    p.func("main", 0, 5)  # 0 i, 1 fare, 2 receipt, 3 zone
    p.func("zone", 1, 1)
    kt = p.const(taps)
    ke = p.const(b"")
    ksep = p.const(rng.choice([b"/", b"\\", b"\x1f", b"|"]))
    p.label("main")
    p.ops(f"PUSHK:{ke} STORE:2 PUSHI:0 STORE:0 PUSHI:{rng.randint(-50, 50)} STORE:1")
    p.ops(f"loop: LOAD:0 PUSHK:{kt} LEN LT JZ:done")
    p.ops(f"PUSHK:{kt} LOAD:0 BYTE CALL:zone DUP STORE:3 PRINT")
    p.ops(f"LOAD:1 PUSHI:{mult} MUL LOAD:3 ADD STORE:1")
    p.ops(f"LOAD:1 PUSHI:{cap} ULT JNZ:under LOAD:1 PUSHI:{rng.choice([1, 3, 5])} SHR STORE:1 under:")
    p.ops(f"TRY:full LOAD:2 LOAD:3 CAT PUSHK:{ksep} CAT STORE:2 ENDTRY JMP:next")
    p.ops(f"full: PRINT LOAD:2 PRINT PUSHK:{ke} STORE:2")
    p.ops("next: LOAD:0 PUSHI:1 ADD STORE:0 JMP:loop")
    p.ops("done: LOAD:1 PRINT LOAD:2 PRINT LOAD:1 STR LEN PRINT HALT")
    p.label("zone")
    p.ops(f"LOAD:0 PUSHI:{k} MOD LOAD:0 PUSHI:{k} DIV ADD RET")
    return p


def digits_image(seed, W, D):
    """Recursive digit sum by floor division; frames run out at D; handlers at odd depths."""
    rng = random.Random(seed)
    p = Prog(W=W, F=10 ** 7, S=64, D=D, L=64)
    p.func("main", 0, 1)
    p.func("dsum", 2, 3)   # 0 n, 1 depth
    kz = p.const(b"deep")
    p.label("main")
    vals = [ints_for(rng, W) for _ in range(5)] + [rng.randint(-99999, 99999)]
    for i, v in enumerate(vals):
        p.ops(f"TRY:h{i} PUSHI:{v} PUSHI:0 CALL:dsum PRINT ENDTRY JMP:d{i} h{i}: PRINT d{i}:")
    p.ops("HALT")
    p.label("dsum")
    p.ops("LOAD:1 PUSHI:1 AND JZ:even TRY:caught even:")
    p.ops("LOAD:0 JZ:zero")
    p.ops("LOAD:0 PUSHI:10 DIV LOAD:1 PUSHI:1 ADD CALL:dsum LOAD:0 PUSHI:10 MOD ADD RET")
    p.ops("zero: PUSHI:0 RET")
    p.ops(f"caught: DUP PRINT PUSHI:{rng.choice([100, -100, 7])} LOAD:1 MUL SWAP PUSHK:{kz} EQ JNZ:skip RET skip: RET")
    return p


def sort_image(seed, L):
    """Five strings sorted by LT with a compare-exchange network; printed escaped."""
    rng = random.Random(seed)
    W = rng.choice([10, 20, 40])
    p = Prog(W=W, F=10 ** 6, S=16, D=3, L=L)
    words = [str_for(rng)[:L] for _ in range(5)]
    words[rng.randrange(5)] = words[0] + b"\x80"[:max(0, L - len(words[0]))]
    p.func("main", 0, 5)
    p.func("less", 2, 2)
    p.label("main")
    for i, w in enumerate(words):
        p.ops(f"PUSHK:{p.const(w)} STORE:{i}")
    net = [(0, 1), (3, 4), (2, 4), (2, 3), (0, 3), (0, 2), (1, 4), (1, 3), (1, 2)]
    for j, (a, b) in enumerate(net):
        p.ops(f"LOAD:{b} LOAD:{a} CALL:less JZ:k{j} LOAD:{a} LOAD:{b} STORE:{a} STORE:{b} k{j}:")
    for i in range(5):
        p.ops(f"LOAD:{i} PRINT")
    p.ops("LOAD:0 LOAD:4 EQ PRINT LOAD:1 LEN LOAD:2 LEN ULT PRINT HALT")
    p.label("less")
    p.ops("LOAD:0 LOAD:1 LT RET")
    return p


def hash_image(seed, W):
    """A rolling check value over a card number with shifts whose counts come from the data."""
    rng = random.Random(seed)
    p = Prog(W=W, F=10 ** 6, S=16, D=2, L=40)
    card = bytes(rng.choice(b"0123456789") for _ in range(rng.randint(8, 14)))
    p.func("main", 0, 3)
    kc = p.const(card)
    sh = rng.choice([W - 2, W, W + 3, 5])
    p.label("main")
    p.ops(f"PUSHI:{rng.randint(-1000, 1000)} STORE:1 PUSHI:0 STORE:0")
    p.ops(f"top: LOAD:0 PUSHK:{kc} LEN LT JZ:out")
    p.ops(f"PUSHK:{kc} LOAD:0 BYTE PUSHI:48 SUB STORE:2")
    p.ops(f"LOAD:1 PUSHI:9 LOAD:2 SUB USHR DUP PRINT LOAD:1 LOAD:2 PUSHI:{sh} ADD SHL XOR LOAD:2 XOR STORE:1")
    p.ops(f"LOAD:1 PRINT LOAD:1 PUSHI:{rng.choice([-3, 3, 97])} LOAD:2 SUB SHR PRINT")
    p.ops("LOAD:0 PUSHI:1 ADD STORE:0 JMP:top")
    p.ops(f"out: LOAD:1 PUSHI:0 ULT PRINT LOAD:1 PUSHI:0 LT PRINT LOAD:1 PUSHI:{rng.choice([97, -97, 10])} MOD PRINT HALT")
    return p


def fields_image(seed, W, L):
    """A comma separated field list split with BYTE and SLICE; each field read by NUM."""
    rng = random.Random(seed)
    p = Prog(W=W, F=10 ** 6, S=16, D=2, L=L)
    fields = []
    for _ in range(rng.randint(5, 9)):
        r = rng.random()
        if r < 0.5:
            fields.append(str(rng.randint(-10 ** 9, 10 ** 9)).encode())
        else:
            fields.append(rng.choice([b"", b"+4", b"007", b"-0", b"-", b"1e3", b" 5", b"99999999999999999999", b"-2147483649"]))
    line = b",".join(fields)[:L]
    p.func("main", 0, 4)   # 0 pos, 1 start, 2 sum
    kl = p.const(line)
    p.label("main")
    p.ops("PUSHI:0 STORE:0 PUSHI:0 STORE:1 PUSHI:0 STORE:2")
    p.ops(f"scan: LOAD:0 PUSHK:{kl} LEN EQ JNZ:field")
    p.ops(f"PUSHK:{kl} LOAD:0 BYTE PUSHI:44 EQ JNZ:field LOAD:0 PUSHI:1 ADD STORE:0 JMP:scan")
    p.ops(f"field: TRY:bad PUSHK:{kl} LOAD:1 LOAD:0 LOAD:1 SUB SLICE NUM DUP PRINT LOAD:2 ADD STORE:2 ENDTRY JMP:after")
    p.ops("bad: PRINT")
    p.ops(f"after: LOAD:0 PUSHK:{kl} LEN EQ JNZ:end LOAD:0 PUSHI:1 ADD DUP STORE:0 STORE:1 JMP:scan")
    p.ops("end: LOAD:2 PRINT LOAD:2 STR PRINT HALT")
    return p


def ledger_image(seed, W, L):
    """A narrow validator: a journal string doubled by CAT until it passes L, read back byte by
    byte in a loop whose body is longer than a W-bit branch offset can hold when reduced."""
    rng = random.Random(seed)
    p = Prog(W=W, F=10 ** 6, S=24, D=3, L=L)
    seedstr = bytes(rng.choice([0x80, 0xc8, 0xff, 0x41, 0x5c, 0x7e, 0x10, 0x90]) for _ in range(rng.randint(3, 7)))
    p.func("main", 0, 4)   # 0 journal, 1 i, 2 acc, 3 step
    ks = p.const(seedstr)
    p.label("main")
    p.ops(f"PUSHK:{ks} STORE:0 PUSHI:0 STORE:2")
    p.ops("grow: TRY:full LOAD:0 LOAD:0 CAT STORE:0 ENDTRY LOAD:0 LEN PRINT JMP:grow")
    p.ops("full: PRINT LOAD:0 LEN PRINT LOAD:0 LEN PUSHI:0 LT PRINT")
    step = rng.choice([7, 13, 29, 37])
    p.ops("PUSHI:0 STORE:1")
    p.ops("walk: LOAD:1 LOAD:0 LEN ULT JZ:end")
    p.ops("LOAD:0 LOAD:1 BYTE DUP LOAD:2 ADD STORE:2")
    # a long body of work so the backward branch needs a wide offset
    for j in range(rng.randint(14, 22)):
        p.ops(f"DUP PUSHI:{rng.randint(-60, 60)} {rng.choice(['ADD', 'SUB', 'XOR', 'MUL'])} LOAD:2 {rng.choice(['XOR', 'ADD'])} STORE:2")
    p.ops("PUSHI:0 LT JZ:pos LOAD:2 PRINT pos:")
    p.ops(f"LOAD:1 PUSHI:{step} ADD STORE:1 JMP:walk")
    p.ops("end: LOAD:2 PRINT LOAD:0 PUSHI:-5 PUSHI:5 SLICE PRINT HALT")
    return p


def pad_some(p, rng, frac=0.3):
    for i, it in enumerate(p.code):
        if it[0] not in ("label", "raw") and rng.random() < frac:
            p.pad[i] = rng.randint(1, 3)
    return p


def tight(p, rng):
    """Set the budget to the exact need, or a few ticks short of it."""
    import re

    from fvm_model import run
    p.F = 2 ** 32 - 1
    t = int(re.search(rb"ticks=(\d+)", run(p.image())).group(1))
    p.F = t - rng.choice([0, 0, 1, 2, 3, 5, 9, t // 3])
    return p


def wide_image(seed):
    """A generation with limits past one byte: 300 stack values, 150 frames, 300-byte strings,
    more than 64 constants and 16 functions, 18 nested handlers, ten-byte constants, entry not
    at offset 0."""
    rng = random.Random(seed)
    p = Prog(W=24, F=10 ** 6, S=300, D=150, L=300)
    for _ in range(70):
        p.const(ints_for(rng, 24))
    p.consts.append(("raw", b"\x00" + b"\xff" * 9 + b"\x01"))
    p.const(bytes(rng.choice(b"fare zone\\\x00\x9f~") for _ in range(300)))
    p.func("main", 0, 2)
    p.func("rec", 1, 1)
    for i in range(2, 20):
        p.func(f"f{i}", 0, 0)
    for i in range(2, 20):
        p.label(f"f{i}")
        p.ops(f"PUSHK:{rng.randrange(70)} PUSHI:{i} ADD RET")
    p.ops("rec: LOAD:0 PUSHI:1 ADD CALL:rec RET")
    p.label("main")
    p.ops("PUSHK:69 PRINT PUSHK:70 PRINT PUSHK:71 DUP PRINT LEN PRINT CALL:19 CALL:17 SUB PRINT")
    p.ops("TRY:hd PUSHI:5 CALL:rec hd: PRINT")
    p.ops(" ".join(f"TRY:h{k}" for k in range(1, 19)) + f" PUSHK:{rng.randrange(70)} THROW")
    for k in range(1, 19):
        p.ops(f"h{k}: PRINT PUSHI:{k} PRINT HALT")
    return p


def zero_budget_image(seed):
    """A tick budget of 0: the first instruction cannot be charged."""
    rng = random.Random(seed)
    p = Prog(W=40, F=0, S=8, D=2, L=20)
    p.const(ints_for(rng, 40))
    p.func("main", 0, 1)
    p.func("f", 0, 3)
    p.ops("f: PUSHK:0 RET")
    p.ops("main: CALL:f PRINT HALT")
    return p


def limits_image(seed):
    """A generation past the small fixed arrays: a budget with bit 31 set, more than 128
    constants, a string over 1024 bytes, more than 32 functions, a code section over 2048 bytes
    with the entry past it, a slot past 32, more than 64 frames and more than 128 values."""
    rng = random.Random(seed)
    p = Prog(W=20, F=0x80000000 + rng.randrange(1 << 30), S=140, D=70, L=1100)
    for _ in range(130):
        p.const(ints_for(rng, 20))
    p.const(bytes(rng.choice(b"tap zone\\\x00\x9f~") for _ in range(rng.randint(1030, 1100))))
    p.func("main", 0, 34)
    p.func("rec", 1, 1)
    for i in range(2, 34):
        p.func(f"f{i}", 0, 0, label="last" if i == 33 else "rec")
    p.raw(bytes(rng.randrange(0x51, 0x100) for _ in range(rng.randint(2049, 2200))))
    p.label("main")
    p.ops(f"PUSHI:{rng.randint(-99, 99)} STORE:33 LOAD:33 PRINT PUSHK:129 PRINT PUSHK:130 LEN PRINT")
    p.ops("CALL:33 PRINT PUSHI:1 CALL:rec PRINT")
    p.ops(" ".join(f"PUSHK:{rng.randrange(130)}" for _ in range(140)) + " HALT")
    p.ops("rec: LOAD:0 PUSHI:69 LT JZ:top LOAD:0 PUSHI:1 ADD CALL:rec RET top: LOAD:0 RET")
    p.ops(f"last: PUSHI:{rng.randint(1, 999)} RET")
    return p


def targets_image(seed):
    """Branch and handler offsets near 2^63: untaken branches and a dropped handler do nothing,
    then a raise two frames down lands on a handler target past 2^63 - 1."""
    rng = random.Random(seed)
    big = lambda: (1 << 63) - 1 - rng.randrange(16)
    p = Prog(W=27, F=10 ** 5, S=16, D=4, L=40)
    p.func("main", 0, 1)
    p.func("f", 1, 1)
    p.label("main")
    p.op("PUSHI", 0)
    p.op("JNZ", big())
    p.op("PUSHI", rng.randint(1, 50))
    p.op("JZ", big())
    p.op("TRY", big())
    p.ops(f"PUSHI:{rng.randint(-99, 99)} PRINT ENDTRY")
    p.op("TRY", -(1 << 63))
    p.ops("ENDTRY")
    p.op("TRY", big())
    p.ops(f"PUSHI:{rng.randint(1, 9)} CALL:f HALT")
    p.ops("f: LOAD:0 PUSHI:0 DIV RET")
    return p


def maxima_image(seed):
    """Each table and limit at its stated maximum at once: 65535 constants with a 65535-byte
    string among them, 65535 functions, 255 slots in the entry frame and 255 live frames."""
    rng = random.Random(seed)
    W = rng.choice([20, 24, 40])
    p = Prog(W=W, F=10 ** 6, S=65535, D=255, L=65535)
    sidx = rng.randrange(1000, 65000)
    for k in range(65535):
        p.const(bytes(rng.choice(b"fare\\\x01\xfe") for _ in range(65535)) if k == sidx else ints_for(rng, W))
    p.func("main", 0, 255)
    for i in range(1, 65534):
        p.func(f"g{i}", 0, 0, label="main")
    p.func("rec", 1, 1)
    p.label("main")
    p.ops(f"PUSHI:{rng.randint(-999, 999)} STORE:254 PUSHK:65534 PRINT PUSHK:{rng.randrange(65535)} PRINT")
    p.ops(f"PUSHK:{sidx} LEN PRINT PUSHK:{sidx} PUSHI:{rng.randrange(65535)} BYTE PRINT")
    p.ops("PUSHI:1 CALL:65534 PRINT LOAD:254 PRINT HALT")
    p.ops("rec: LOAD:0 PUSHI:254 LT JZ:top LOAD:0 PUSHI:1 ADD CALL:65534 RET top: LOAD:0 RET")
    return p


HELD_WIDTHS = [10, 13, 20, 24, 27, 40, 48]


def heldback(seed_base):
    out = {}
    for i in range(8):
        s = seed_base * 1000 + i
        rng = random.Random(s)
        W = HELD_WIDTHS[i % len(HELD_WIDTHS)]
        out[f"hb{i}_fuzz"] = fuzz_image(s, W, rng.choice([6, 11, 40, 255]), 40, in_call=bool(i % 2))
        out[f"hb{i}_fare"] = tight(fare_image(s + 1, rng.choice([10, 13, 20, 27]), rng.choice([12, 30, 80])), rng) if i % 3 == 0 else fare_image(s + 1, rng.choice([10, 13, 20, 27]), rng.choice([12, 30, 80]))
        out[f"hb{i}_digits"] = tight(digits_image(s + 2, rng.choice([13, 24, 40, 48]), rng.choice([4, 6, 9, 14])), rng)
        out[f"hb{i}_sort"] = sort_image(s + 3, rng.choice([4, 9, 20]))
        out[f"hb{i}_hash"] = tight(hash_image(s + 4, W), rng) if i % 2 else hash_image(s + 4, W)
        out[f"hb{i}_fields"] = fields_image(s + 5, rng.choice([10, 20, 27, 40]), rng.choice([20, 60]))
        out[f"hb{i}_ledger"] = ledger_image(s + 6, [8, 9][i % 2], rng.choice([300, 600, 1100]))
        if i % 2 == 0:
            pad_some(out[f"hb{i}_fuzz"], rng)
            pad_some(out[f"hb{i}_fields"], rng)
    out["hb8_wide"] = wide_image(seed_base * 1000 + 8)
    out["hb8_zero_budget"] = zero_budget_image(seed_base * 1000 + 9)
    out["hb9_limits"] = limits_image(seed_base * 1000 + 10)
    out["hb9_targets"] = targets_image(seed_base * 1000 + 11)
    out["hb10_maxima"] = maxima_image(seed_base * 1000 + 12)
    return {k: v.image() for k, v in out.items()}
