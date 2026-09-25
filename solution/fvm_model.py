"""Python model of the FVM-2 fare machine, used to write the expected transcripts.

run(image_bytes) -> transcript bytes. Follows /app/spec/FVM2.txt exactly.
"""


class BadImage(Exception):
    pass


class Fault(Exception):
    def __init__(self, kind, at):
        self.kind = kind
        self.at = at


class Raise(Exception):
    def __init__(self, value):
        self.value = value


def reduce(v, w):
    m = 1 << w
    v %= m
    if v >= m >> 1:
        v -= m
    return v


class Reader:
    def __init__(self, data, pos=0, end=None):
        self.d = data
        self.p = pos
        self.end = len(data) if end is None else end

    def byte(self):
        if self.p >= self.end:
            raise EOFError
        b = self.d[self.p]
        self.p += 1
        return b

    def uvarint(self):
        v = 0
        for i in range(10):
            b = self.byte()
            v |= (b & 0x7F) << (7 * i)
            if not b & 0x80:
                if v >= 1 << 64:
                    raise ValueError("varint too large")
                return v
        raise ValueError("varint too long")

    def svarint(self):
        u = self.uvarint()
        if u & 1:
            return -((u + 1) >> 1)
        return u >> 1


def decimal(v):
    return str(v).encode()


def render(v):
    if isinstance(v, int):
        return decimal(v)
    out = bytearray()
    for b in v:
        if b == 0x5C:
            out += b"\\\\"
        elif 0x20 <= b <= 0x7E:
            out.append(b)
        else:
            out += b"\\x%02x" % b
    return bytes(out)


OPS = {
    0x00: "HALT", 0x01: "PUSHI", 0x02: "PUSHK", 0x03: "POP", 0x04: "DUP", 0x05: "SWAP",
    0x06: "PICK", 0x08: "LOAD", 0x09: "STORE",
    0x10: "ADD", 0x11: "SUB", 0x12: "MUL", 0x13: "DIV", 0x14: "MOD", 0x15: "NEG",
    0x16: "AND", 0x17: "OR", 0x18: "XOR", 0x19: "SHL", 0x1A: "SHR", 0x1B: "USHR",
    0x20: "EQ", 0x21: "LT", 0x22: "ULT",
    0x28: "JMP", 0x29: "JZ", 0x2A: "JNZ",
    0x30: "CALL", 0x31: "RET",
    0x38: "TRY", 0x39: "ENDTRY", 0x3A: "THROW",
    0x40: "CAT", 0x41: "LEN", 0x42: "SLICE", 0x43: "BYTE", 0x44: "CHR", 0x45: "STR", 0x46: "NUM",
    0x50: "PRINT",
}
OPERAND = {"PUSHI": "s", "PUSHK": "u", "PICK": "u", "LOAD": "u", "STORE": "u",
           "JMP": "s", "JZ": "s", "JNZ": "s", "CALL": "u", "TRY": "s"}


def load(img):
    if len(img) < 14 or img[0:4] != b"FVM\x02":
        raise BadImage
    W = img[4]
    F = int.from_bytes(img[5:9], "little")
    S = int.from_bytes(img[9:11], "little")
    D = img[11]
    L = int.from_bytes(img[12:14], "little")
    if not (8 <= W <= 48) or S < 1 or D < 1:
        raise BadImage
    r = Reader(img, 14)
    try:
        K = r.uvarint()
        if K > 65535:
            raise BadImage
        consts = []
        for _ in range(K):
            tag = r.byte()
            if tag == 0:
                consts.append(reduce(r.svarint(), W))
            elif tag == 1:
                n = r.uvarint()
                if n > L:
                    raise BadImage
                if r.p + n > len(img):
                    raise BadImage
                consts.append(bytes(img[r.p:r.p + n]))
                r.p += n
            else:
                raise BadImage
        N = r.uvarint()
        if not 1 <= N <= 65535:
            raise BadImage
        funcs = []
        for _ in range(N):
            off = r.uvarint()
            P = r.byte()
            V = r.byte()
            if P > V:
                raise BadImage
            funcs.append((off, P, V))
        C = r.uvarint()
        if not 1 <= C <= 1 << 20:
            raise BadImage
        if r.p + C != len(img):
            raise BadImage
        code = bytes(img[r.p:r.p + C])
    except (EOFError, ValueError):
        raise BadImage
    for off, P, V in funcs:
        if off >= C:
            raise BadImage
    if funcs[0][1] != 0:
        raise BadImage
    return {"W": W, "F": F, "S": S, "D": D, "L": L, "consts": consts, "funcs": funcs, "code": code}


class Frame:
    __slots__ = ("base", "locals", "ret")

    def __init__(self, nloc, base, ret):
        self.locals = [0] * nloc
        self.base = base
        self.ret = ret


def run(img):
    try:
        m = load(img)
    except BadImage:
        return b"-- bad image\n"
    W, F, S, D, L = m["W"], m["F"], m["S"], m["D"], m["L"]
    consts, funcs, code = m["consts"], m["funcs"], m["code"]
    C = len(code)
    out = bytearray()
    stack = []
    frames = [Frame(funcs[0][2], 0, None)]
    handlers = []  # (target, stack size, frame index)
    pc = funcs[0][0]
    used = 0

    def red(v):
        return reduce(v, W)

    def isint(v):
        return isinstance(v, int)

    while True:
        at = pc
        try:
            # 1. decode
            if not (0 <= pc < C):
                raise Fault("CODE", at)
            rd = Reader(code, pc)
            op = rd.byte()
            name = OPS.get(op)
            if name is None:
                raise Fault("CODE", at)
            arg = None
            try:
                kind = OPERAND.get(name)
                if kind == "u":
                    arg = rd.uvarint()
                elif kind == "s":
                    arg = rd.svarint()
            except (EOFError, ValueError):
                raise Fault("CODE", at)
            nxt = rd.p
            fr = frames[-1]
            avail = len(stack) - fr.base

            # 2. index checks
            if name == "PUSHK" and arg >= len(consts):
                raise Fault("CODE", at)
            if name in ("LOAD", "STORE") and arg >= len(fr.locals):
                raise Fault("CODE", at)
            if name == "CALL" and arg >= len(funcs):
                raise Fault("CODE", at)
            if name == "RET" and len(frames) == 1:
                raise Fault("CODE", at)
            if name == "ENDTRY" and (not handlers or handlers[-1][2] != len(frames) - 1):
                raise Fault("CODE", at)

            # 3. underflow
            npop = {"POP": 1, "DUP": 1, "SWAP": 2, "STORE": 1, "NEG": 1, "JZ": 1, "JNZ": 1,
                    "RET": 1, "THROW": 1, "LEN": 1, "CHR": 1, "STR": 1, "NUM": 1, "PRINT": 1,
                    "SLICE": 3, "BYTE": 2, "CAT": 2, "EQ": 2, "LT": 2, "ULT": 2}.get(name, 0)
            if name in ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR", "SHL", "SHR", "USHR"):
                npop = 2
            if name == "PICK":
                npop = arg + 1
            if name == "CALL":
                npop = funcs[arg][1]
            if avail < npop:
                raise Fault("STACK", at)

            # 4. compute
            cost = 1
            raised = None
            pops = npop if name not in ("DUP", "PICK") else 0
            pushes = []
            newpc = nxt
            printed = None
            try:
                if name == "HALT":
                    pass
                elif name == "PUSHI":
                    pushes = [red(arg)]
                elif name == "PUSHK":
                    pushes = [consts[arg]]
                elif name == "POP":
                    pass
                elif name == "DUP":
                    pushes = [stack[-1]]
                elif name == "SWAP":
                    pushes = [stack[-1], stack[-2]]
                elif name == "PICK":
                    pushes = [stack[-1 - arg]]
                elif name == "LOAD":
                    pushes = [fr.locals[arg]]
                elif name == "STORE":
                    pass
                elif name in ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR",
                              "SHL", "SHR", "USHR", "ULT"):
                    a, b = stack[-2], stack[-1]
                    if not (isint(a) and isint(b)):
                        raise Raise(b"TYPE")
                    if name == "ADD":
                        r = a + b
                    elif name == "SUB":
                        r = a - b
                    elif name == "MUL":
                        r = a * b
                    elif name in ("DIV", "MOD"):
                        if b == 0:
                            raise Raise(b"DIVZERO")
                        q = a // b
                        r = q if name == "DIV" else a - b * q
                    elif name == "AND":
                        r = a & b
                    elif name == "OR":
                        r = a | b
                    elif name == "XOR":
                        r = a ^ b
                    elif name == "ULT":
                        r = 1 if (a % (1 << W)) < (b % (1 << W)) else 0
                    else:
                        cnt = b % (1 << W)
                        if name == "SHL":
                            r = 0 if cnt >= W else a << cnt
                        elif name == "SHR":
                            r = (-1 if a < 0 else 0) if cnt >= W else a >> cnt
                        else:
                            r = 0 if cnt >= W else (a % (1 << W)) >> cnt
                    pushes = [red(r)]
                elif name == "NEG":
                    a = stack[-1]
                    if not isint(a):
                        raise Raise(b"TYPE")
                    pushes = [red(-a)]
                elif name == "EQ":
                    a, b = stack[-2], stack[-1]
                    pushes = [1 if (type(a) is type(b) and a == b) else 0]
                elif name == "LT":
                    a, b = stack[-2], stack[-1]
                    if type(a) is not type(b):
                        raise Raise(b"TYPE")
                    pushes = [1 if a < b else 0]
                elif name == "JMP":
                    newpc = nxt + arg
                elif name in ("JZ", "JNZ"):
                    v = stack[-1]
                    if not isint(v):
                        raise Raise(b"TYPE")
                    if (v == 0) == (name == "JZ"):
                        newpc = nxt + arg
                elif name == "CALL":
                    off, P, V = funcs[arg]
                    lim = D
                    if len(frames) >= lim:
                        raise Raise(b"DEPTH")
                    cost = 1 + V
                elif name == "RET" or name in ("TRY", "ENDTRY"):
                    pass
                elif name == "THROW":
                    raise Raise(stack[-1])
                elif name == "CAT":
                    a, b = stack[-2], stack[-1]
                    s = (decimal(a) if isint(a) else a) + (decimal(b) if isint(b) else b)
                    if len(s) > L:
                        raise Raise(b"LIMIT")
                    pushes = [s]
                    cost = 1 + len(s) // 8
                elif name == "LEN":
                    a = stack[-1]
                    if isint(a):
                        raise Raise(b"TYPE")
                    pushes = [red(len(a))]
                elif name == "SLICE":
                    x, s, c = stack[-3], stack[-2], stack[-1]
                    if isint(x) or not isint(s) or not isint(c):
                        raise Raise(b"TYPE")
                    n = len(x)
                    if s < 0:
                        s += n
                    s = min(max(s, 0), n)
                    if c < 0:
                        raise Raise(b"RANGE")
                    r = x[s:min(n, s + c)]
                    pushes = [r]
                    cost = 1 + len(r) // 8
                elif name == "BYTE":
                    x, i = stack[-2], stack[-1]
                    if isint(x) or not isint(i):
                        raise Raise(b"TYPE")
                    if i < 0 or i >= len(x):
                        raise Raise(b"RANGE")
                    pushes = [red(x[i])]
                elif name == "CHR":
                    a = stack[-1]
                    if not isint(a):
                        raise Raise(b"TYPE")
                    if not (0 <= a <= 255):
                        raise Raise(b"RANGE")
                    if L < 1:
                        raise Raise(b"LIMIT")
                    pushes = [bytes([a])]
                elif name == "STR":
                    a = stack[-1]
                    if not isint(a):
                        raise Raise(b"TYPE")
                    s = decimal(a)
                    if len(s) > L:
                        raise Raise(b"LIMIT")
                    pushes = [s]
                    cost = 1 + len(s) // 8
                elif name == "NUM":
                    a = stack[-1]
                    if isint(a):
                        raise Raise(b"TYPE")
                    neg = a[:1] == b"-"
                    t = a[1:] if neg else a
                    if not t or any(not (0x30 <= ch <= 0x39) for ch in t):
                        raise Raise(b"PARSE")
                    v = int(t)
                    pushes = [red(-v if neg else v)]
                elif name == "PRINT":
                    printed = render(stack[-1])
                    cost = 1 + len(printed) // 8
            except Raise as e:
                raised = e.value
                cost = 1

            # 5. overflow
            if raised is None and name not in ("CALL", "RET") and len(stack) - pops + len(pushes) > S:
                raise Fault("STACK", at)

            # 6. ticks
            budget = F
            if used + cost > budget:
                raise Fault("FUEL", at)
            used += cost

            # 7. commit
            if raised is not None:
                if name != "CALL":
                    del stack[len(stack) - pops:]
                if not handlers:
                    out += b"-- error " + render(raised) + b" at=%d ticks=%d\n" % (at, used)
                    return bytes(out)
                target, depth, fidx = handlers.pop()
                del frames[fidx + 1:]
                del stack[depth:]
                if len(stack) >= S:
                    raise Fault("STACK", at)
                stack.append(raised)
                pc = target
                continue
            if name == "HALT":
                out += b"-- halt ticks=%d stack=%d\n" % (used, len(stack))
                return bytes(out)
            if name == "STORE":
                fr.locals[arg] = stack[-1]
            if name == "CALL":
                off, P, V = funcs[arg]
                args = stack[len(stack) - P:] if P else []
                del stack[len(stack) - P:]
                nf = Frame(V, len(stack), nxt)
                nf.locals[:P] = args
                frames.append(nf)
                pc = off
                continue
            if name == "RET":
                v = stack[-1]
                del stack[fr.base:]
                while handlers and handlers[-1][2] == len(frames) - 1:
                    handlers.pop()
                frames.pop()
                stack.append(v)
                pc = fr.ret
                continue
            if name == "TRY":
                handlers.append((nxt + arg, len(stack), len(frames) - 1))
            if name == "ENDTRY":
                handlers.pop()
            if pops:
                del stack[len(stack) - pops:]
            stack.extend(pushes)
            if printed is not None:
                out += printed + b"\n"
            pc = newpc
        except Fault as f:
            out += b"-- fault %s at=%d ticks=%d\n" % (f.kind.encode(), f.at, used)
            return bytes(out)
