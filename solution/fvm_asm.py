"""A small assembler for FVM-2 images (used only to write the suites)."""
from fvm_model import OPERAND, OPS

CODE = {v: k for k, v in OPS.items()}


def uvar(u):
    assert u >= 0
    out = bytearray()
    while True:
        b = u & 0x7F
        u >>= 7
        if u:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def svar(s):
    return uvar(2 * s if s >= 0 else -2 * s - 1)


def padded(enc, extra):
    """The same value with `extra` redundant zero groups (still at most 10 bytes)."""
    extra = min(extra, 10 - len(enc))
    if extra <= 0:
        return enc
    return enc[:-1] + bytes([enc[-1] | 0x80]) + b"\x80" * (extra - 1) + b"\x00"


class Prog:
    def __init__(self, W=32, F=10000, S=64, D=16, L=255):
        self.W, self.F, self.S, self.D, self.L = W, F, S, D, L
        self.consts = []          # (kind, value) or raw bytes
        self.funcs = []           # (label, P, V)
        self.code = []            # items
        self.fname = {}
        self.pad = {}             # code item index -> redundant groups on its operand

    def const(self, v):
        self.consts.append(v)
        return len(self.consts) - 1

    def func(self, name, P=0, V=0, label=None):
        self.fname[name] = len(self.funcs)
        self.funcs.append((label or name, P, V))
        return self.fname[name]

    def label(self, name):
        self.code.append(("label", name))

    def op(self, name, arg=None):
        self.code.append((name, arg))

    def raw(self, b):
        self.code.append(("raw", bytes(b)))

    def ops(self, text):
        """Space/newline separated mnemonics; 'NAME:arg'; 'label:' defines a label."""
        for tok in text.split():
            if tok.endswith(":") and tok[:-1] not in CODE:
                self.label(tok[:-1])
            elif ":" in tok:
                n, a = tok.split(":", 1)
                try:
                    a = int(a)
                except ValueError:
                    pass
                self.op(n, a)
            else:
                self.op(tok)

    def assemble_code(self):
        sizes = {}
        for _ in range(50):
            addr = 0
            labels = {}
            for i, it in enumerate(self.code):
                if it[0] == "label":
                    labels[it[1]] = addr
                elif it[0] == "raw":
                    addr += len(it[1])
                else:
                    addr += sizes.get(i, 1 + (0 if OPERAND.get(it[0]) is None else 1))
            out = bytearray()
            newsizes = {}
            for i, it in enumerate(self.code):
                if it[0] == "label":
                    continue
                if it[0] == "raw":
                    out += it[1]
                    continue
                name, arg = it
                b = bytearray([CODE[name]])
                kind = OPERAND.get(name)
                if kind is None:
                    assert arg is None, it
                elif name in ("JMP", "JZ", "JNZ", "TRY") and isinstance(arg, str):
                    here = len(out)
                    sz = sizes.get(i, 2)
                    target = labels[arg]
                    b += padded(svar(target - (here + sz)), self.pad.get(i, 0))
                elif name == "CALL" and isinstance(arg, str):
                    b += padded(uvar(self.fname[arg]), self.pad.get(i, 0))
                elif kind == "u":
                    b += padded(uvar(arg), self.pad.get(i, 0))
                else:
                    b += padded(svar(arg), self.pad.get(i, 0))
                newsizes[i] = len(b)
                out += b
            if newsizes == sizes:
                self.labels = labels
                return bytes(out)
            sizes = newsizes
        raise RuntimeError("no fixpoint")

    def image(self, header=None, trailer=b""):
        code = self.assemble_code()
        h = bytearray(b"FVM\x02")
        h.append(self.W)
        h += self.F.to_bytes(4, "little")
        h += self.S.to_bytes(2, "little")
        h.append(self.D)
        h += self.L.to_bytes(2, "little")
        if header is not None:
            h = bytearray(header)
        body = bytearray(uvar(len(self.consts)))
        for c in self.consts:
            if isinstance(c, int):
                body += b"\x00" + svar(c)
            elif isinstance(c, (bytes, bytearray)):
                body += b"\x01" + uvar(len(c)) + bytes(c)
            else:  # ("raw", bytes)
                body += c[1]
        body += uvar(len(self.funcs))
        for lab, P, V in self.funcs:
            body += uvar(self.labels[lab]) + bytes([P, V])
        body += uvar(len(code)) + code
        return bytes(h + body) + trailer
