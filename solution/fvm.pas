program fvm;
{ FVM-2 interpreter for the back-office replay. Reads one image, runs it, writes the
  transcript to standard output. Integers are kept sign-extended in an Int64 and reduced to
  the image's word width after every operation; products wrap in 64 bits first, which is
  still exact modulo 2^W because W is at most 48. }

{$mode objfpc}{$H+}
{$Q-}{$R-}

uses
  SysUtils, Classes;

type
  TKind = (vkInt, vkStr);
  TValue = record
    Kind: TKind;
    I: Int64;
    S: RawByteString;
  end;
  TFunc = record
    Offset: QWord;
    P, V: Integer;
  end;
  TFrame = record
    Slots: array of TValue;
    Base: Integer;
    Ret: Int64;
  end;
  THandler = record
    Target: Int64;
    Far: Boolean;                { Target is past 2^63 - 1, held as its unsigned bits }
    Depth: Integer;
    Frame: Integer;
  end;

  EBadImage = class(Exception);
  EFault = class(Exception)
  public
    Kind: string;
    At: Int64;
    constructor Make(const AKind: string; AAt: Int64);
  end;
  ERaise = class(Exception)
  public
    Value: TValue;
    constructor Make(const AValue: TValue);
  end;
  EDecode = class(Exception);

constructor EFault.Make(const AKind: string; AAt: Int64);
begin
  inherited Create(AKind);
  Kind := AKind;
  At := AAt;
end;

constructor ERaise.Make(const AValue: TValue);
begin
  inherited Create('raise');
  Value := AValue;
end;

var
  Img: array of Byte;
  W: Integer;
  F: Int64;
  SLim, DLim, LLim: Integer;
  Consts: array of TValue;
  Funcs: array of TFunc;
  Code: array of Byte;
  CodeLen: Int64;
  Mask, Half: QWord;
  OutBuf: RawByteString;

function IntVal(x: Int64): TValue;
begin
  Result.Kind := vkInt;
  Result.I := x;
  Result.S := '';
end;

function StrVal(const x: RawByteString): TValue;
begin
  Result.Kind := vkStr;
  Result.I := 0;
  Result.S := x;
end;

function Red(x: Int64): Int64;
var
  u: QWord;
begin
  u := QWord(x) and Mask;
  if u >= Half then
    Result := Int64(u) - Int64(Mask) - 1
  else
    Result := Int64(u);
end;

{ ---- varints over a byte array, from position p (advanced), limited to lim }
function UVar(const buf: array of Byte; var p: Int64; lim: Int64): QWord;
var
  i: Integer;
  b: Byte;
begin
  Result := 0;
  for i := 0 to 9 do
  begin
    if p >= lim then
      raise EDecode.Create('short');
    b := buf[p];
    Inc(p);
    if i = 9 then
    begin
      if b > 1 then
        raise EDecode.Create('too large or too long');
      Result := Result or (QWord(b) shl 63);
      Exit;
    end;
    Result := Result or (QWord(b and $7F) shl (7 * i));
    if (b and $80) = 0 then
      Exit;
  end;
end;

function SVar(const buf: array of Byte; var p: Int64; lim: Int64): Int64;
var
  u: QWord;
begin
  u := UVar(buf, p, lim);
  if (u and 1) = 0 then
    Result := Int64(u shr 1)
  else
    Result := -Int64(u shr 1) - 1;
end;

function Render(const v: TValue): RawByteString;
const
  Hex: array[0..15] of Char = '0123456789abcdef';
var
  i: Integer;
  b: Byte;
begin
  if v.Kind = vkInt then
    Exit(IntToStr(v.I));
  Result := '';
  for i := 1 to Length(v.S) do
  begin
    b := Byte(v.S[i]);
    if b = $5C then
      Result := Result + '\\'
    else if (b >= $20) and (b <= $7E) then
      Result := Result + Chr(b)
    else
      Result := Result + '\x' + Hex[b shr 4] + Hex[b and 15];
  end;
end;

function CompareBytes(const a, b: RawByteString): Integer;
var
  i, n: Integer;
begin
  n := Length(a);
  if Length(b) < n then
    n := Length(b);
  for i := 1 to n do
    if Byte(a[i]) <> Byte(b[i]) then
      Exit(Integer(Byte(a[i])) - Integer(Byte(b[i])));
  Result := Length(a) - Length(b);
end;

procedure LoadImage(const path: string);
var
  fs: TFileStream;
  p, n, k, cnt, off: Int64;
  i: Integer;
  tag: Byte;
begin
  fs := TFileStream.Create(path, fmOpenRead or fmShareDenyNone);
  try
    SetLength(Img, fs.Size);
    if fs.Size > 0 then
      fs.ReadBuffer(Img[0], fs.Size);
  finally
    fs.Free;
  end;
  n := Length(Img);
  if n < 14 then
    raise EBadImage.Create('short');
  if (Img[0] <> $46) or (Img[1] <> $56) or (Img[2] <> $4D) or (Img[3] <> $02) then
    raise EBadImage.Create('magic');
  W := Img[4];
  F := Int64(Img[5]) or (Int64(Img[6]) shl 8) or (Int64(Img[7]) shl 16) or (Int64(Img[8]) shl 24);
  SLim := Img[9] or (Img[10] shl 8);
  DLim := Img[11];
  LLim := Img[12] or (Img[13] shl 8);
  if (W < 8) or (W > 48) or (SLim < 1) or (DLim < 1) then
    raise EBadImage.Create('header');
  Mask := (QWord(1) shl W) - 1;
  Half := QWord(1) shl (W - 1);
  p := 14;
  try
    cnt := Int64(UVar(Img, p, n));
    if (cnt < 0) or (cnt > n) then
      raise EBadImage.Create('constants');
    SetLength(Consts, cnt);
    for k := 0 to cnt - 1 do
    begin
      if p >= n then
        raise EBadImage.Create('short');
      tag := Img[p];
      Inc(p);
      if tag = 0 then
        Consts[k] := IntVal(Red(SVar(Img, p, n)))
      else if tag = 1 then
      begin
        off := Int64(UVar(Img, p, n));
        if (off < 0) or (off > LLim) or (p + off > n) then
          raise EBadImage.Create('string');
        SetLength(Consts[k].S, off);
        if off > 0 then
          Move(Img[p], Consts[k].S[1], off);
        Consts[k].Kind := vkStr;
        Consts[k].I := 0;
        p := p + off;
      end
      else
        raise EBadImage.Create('tag');
    end;
    cnt := Int64(UVar(Img, p, n));
    if (cnt < 1) or (cnt > n) then
      raise EBadImage.Create('functions');
    SetLength(Funcs, cnt);
    for k := 0 to cnt - 1 do
    begin
      Funcs[k].Offset := UVar(Img, p, n);
      if p + 2 > n then
        raise EBadImage.Create('short');
      Funcs[k].P := Img[p];
      Funcs[k].V := Img[p + 1];
      p := p + 2;
      if Funcs[k].P > Funcs[k].V then
        raise EBadImage.Create('params');
    end;
    CodeLen := Int64(UVar(Img, p, n));
    if (CodeLen < 1) or (CodeLen <> n - p) then
      raise EBadImage.Create('code');
  except
    on EDecode do
      raise EBadImage.Create('varint');
  end;
  SetLength(Code, CodeLen);
  Move(Img[p], Code[0], CodeLen);
  for i := 0 to High(Funcs) do
    if Funcs[i].Offset >= QWord(CodeLen) then
      raise EBadImage.Create('offset');
  if Funcs[0].P <> 0 then
    raise EBadImage.Create('entry');
end;

{ ---- the machine }
var
  Stack: array of TValue;
  SP: Integer;
  Frames: array of TFrame;
  FP: Integer;                 { number of live frames }
  Handlers: array of THandler;
  HP: Integer;
  Used: Int64;

procedure Emit(const line: RawByteString);
begin
  OutBuf := OutBuf + line + #10;
end;

procedure PushFrame(fn: Integer; base: Integer; ret: Int64);
var
  i: Integer;
begin
  if FP >= Length(Frames) then
    SetLength(Frames, FP + 8);
  SetLength(Frames[FP].Slots, Funcs[fn].V);
  for i := 0 to Funcs[fn].V - 1 do
    Frames[FP].Slots[i] := IntVal(0);
  Frames[FP].Base := base;
  Frames[FP].Ret := ret;
  Inc(FP);
end;

function DecText(x: Int64): RawByteString;
begin
  Result := IntToStr(x);
end;

function AsText(const v: TValue): RawByteString;
begin
  if v.Kind = vkInt then
    Result := DecText(v.I)
  else
    Result := v.S;
end;

function FloorDiv(a, b: Int64): Int64;
begin
  Result := a div b;
  if ((a mod b) <> 0) and ((a < 0) <> (b < 0)) then
    Dec(Result);
end;

{ A branch or handler target is next + s, exact. next is small, so only a positive s can carry
  the sum past 2^63 - 1; then the sum is kept as its unsigned 64-bit bits and marked far. }
function BranchTarget(nxt, s: Int64; out far: Boolean): Int64;
begin
  Result := Int64(QWord(nxt) + QWord(s));
  far := (s > 0) and (Result < 0);
end;

function AddrText(a: Int64; far: Boolean): RawByteString;
begin
  if far then
    Result := UIntToStr(QWord(a))
  else
    Result := IntToStr(a);
end;

procedure Run;
const
  Names: array[0..$50] of string = (
    'HALT','PUSHI','PUSHK','POP','DUP','SWAP','PICK','','LOAD','STORE','','','','','','',
    'ADD','SUB','MUL','DIV','MOD','NEG','AND','OR','XOR','SHL','SHR','USHR','','','','',
    'EQ','LT','ULT','','','','','','JMP','JZ','JNZ','','','','','',
    'CALL','RET','','','','','','','TRY','ENDTRY','THROW','','','','','',
    'CAT','LEN','SLICE','BYTE','CHR','STR','NUM','','','','','','','','','',
    'PRINT');
var
  pc, at, nxt, arg, cost, newpc, cnt: Int64;
  pcFar, newFar: Boolean;
  uarg: QWord;
  op: Byte;
  name: string;
  hasU, hasS: Boolean;
  npop, pops, npush, i: Integer;
  pushes: array[0..1] of TValue;
  a, b, c, x, v: TValue;
  raised: Boolean;
  rv: TValue;
  printed: RawByteString;
  hasPrint: Boolean;
  r, q, s, n: Int64;
  txt, t: RawByteString;
  neg, ok: Boolean;
  h: THandler;
  ua: QWord;

  procedure Need(k: Int64);
  begin
    if SP - Frames[FP - 1].Base < k then
      raise EFault.Make('STACK', at);
  end;

  procedure RaiseStr(const msg: RawByteString);
  begin
    raise ERaise.Make(StrVal(msg));
  end;

  procedure NeedInts(const p, q: TValue);
  begin
    if (p.Kind <> vkInt) or (q.Kind <> vkInt) then
      RaiseStr('TYPE');
  end;

  procedure Push1(const p: TValue);
  begin
    pushes[0] := p;
    npush := 1;
  end;

begin
  SetLength(Stack, SLim + 1);
  SP := 0;
  FP := 0;
  HP := 0;
  Used := 0;
  PushFrame(0, 0, -1);
  pcFar := False;
  pc := Int64(Funcs[0].Offset);
  while True do
  begin
    at := pc;
    try
      { 1. fetch and decode }
      if (pc < 0) or (pc >= CodeLen) then
        raise EFault.Make('CODE', at);
      op := Code[pc];
      if (op > $50) or (Names[op] = '') then
        raise EFault.Make('CODE', at);
      name := Names[op];
      nxt := pc + 1;
      hasU := (name = 'PUSHK') or (name = 'PICK') or (name = 'LOAD') or (name = 'STORE') or (name = 'CALL');
      hasS := (name = 'PUSHI') or (name = 'JMP') or (name = 'JZ') or (name = 'JNZ') or (name = 'TRY');
      uarg := 0;
      arg := 0;
      try
        if hasU then
          uarg := UVar(Code, nxt, CodeLen)
        else if hasS then
          arg := SVar(Code, nxt, CodeLen);
      except
        on EDecode do
          raise EFault.Make('CODE', at);
      end;

      { 2. indexes }
      if (name = 'PUSHK') and (uarg >= QWord(Length(Consts))) then
        raise EFault.Make('CODE', at);
      if ((name = 'LOAD') or (name = 'STORE')) and (uarg >= QWord(Length(Frames[FP - 1].Slots))) then
        raise EFault.Make('CODE', at);
      if (name = 'CALL') and (uarg >= QWord(Length(Funcs))) then
        raise EFault.Make('CODE', at);
      if (name = 'RET') and (FP = 1) then
        raise EFault.Make('CODE', at);
      if (name = 'ENDTRY') and ((HP = 0) or (Handlers[HP - 1].Frame <> FP - 1)) then
        raise EFault.Make('CODE', at);

      { 3. the values it needs }
      if (name = 'POP') or (name = 'DUP') or (name = 'STORE') or (name = 'NEG') or (name = 'JZ')
        or (name = 'JNZ') or (name = 'RET') or (name = 'THROW') or (name = 'LEN') or (name = 'CHR')
        or (name = 'STR') or (name = 'NUM') or (name = 'PRINT') then
        npop := 1
      else if (name = 'SWAP') or (name = 'BYTE') or (name = 'CAT') or (name = 'EQ') or (name = 'LT')
        or (name = 'ULT') or (name = 'ADD') or (name = 'SUB') or (name = 'MUL') or (name = 'DIV')
        or (name = 'MOD') or (name = 'AND') or (name = 'OR') or (name = 'XOR') or (name = 'SHL')
        or (name = 'SHR') or (name = 'USHR') then
        npop := 2
      else if name = 'SLICE' then
        npop := 3
      else
        npop := 0;
      if name = 'PICK' then
      begin
        if uarg >= QWord(SP - Frames[FP - 1].Base) then
          raise EFault.Make('STACK', at);
      end
      else if name = 'CALL' then
        Need(Funcs[uarg].P)
      else
        Need(npop);

      { 4. anything it raises }
      cost := 1;
      raised := False;
      if (name = 'DUP') or (name = 'PICK') then
        pops := 0
      else if name = 'CALL' then
        pops := Funcs[uarg].P
      else
        pops := npop;
      npush := 0;
      newpc := nxt;
      newFar := False;
      hasPrint := False;
      try
        if name = 'PUSHI' then
          Push1(IntVal(Red(arg)))
        else if name = 'PUSHK' then
          Push1(Consts[uarg])
        else if name = 'DUP' then
          Push1(Stack[SP - 1])
        else if name = 'SWAP' then
        begin
          pushes[0] := Stack[SP - 1];
          pushes[1] := Stack[SP - 2];
          npush := 2;
        end
        else if name = 'PICK' then
          Push1(Stack[SP - 1 - Integer(uarg)])
        else if name = 'LOAD' then
          Push1(Frames[FP - 1].Slots[uarg])
        else if (name = 'ADD') or (name = 'SUB') or (name = 'MUL') or (name = 'DIV') or (name = 'MOD')
          or (name = 'AND') or (name = 'OR') or (name = 'XOR') or (name = 'SHL') or (name = 'SHR')
          or (name = 'USHR') or (name = 'ULT') then
        begin
          a := Stack[SP - 2];
          b := Stack[SP - 1];
          NeedInts(a, b);
          if name = 'ADD' then
            r := a.I + b.I
          else if name = 'SUB' then
            r := a.I - b.I
          else if name = 'MUL' then
            r := Int64(QWord(a.I) * QWord(b.I))
          else if (name = 'DIV') or (name = 'MOD') then
          begin
            if b.I = 0 then
              RaiseStr('DIVZERO');
            q := FloorDiv(a.I, b.I);
            if name = 'DIV' then
              r := q
            else
              r := a.I - b.I * q;
          end
          else if name = 'AND' then
            r := a.I and b.I
          else if name = 'OR' then
            r := a.I or b.I
          else if name = 'XOR' then
            r := a.I xor b.I
          else if name = 'ULT' then
          begin
            if (QWord(a.I) and Mask) < (QWord(b.I) and Mask) then
              r := 1
            else
              r := 0;
          end
          else
          begin
            cnt := Int64(QWord(b.I) and Mask);
            if name = 'SHL' then
            begin
              if cnt >= W then
                r := 0
              else
                r := Int64(QWord(a.I) shl cnt);
            end
            else if name = 'SHR' then
            begin
              if cnt >= W then
              begin
                if a.I < 0 then
                  r := -1
                else
                  r := 0;
              end
              else
                r := SarInt64(a.I, cnt);
            end
            else
            begin
              if cnt >= W then
                r := 0
              else
                r := Int64((QWord(a.I) and Mask) shr cnt);
            end;
          end;
          Push1(IntVal(Red(r)));
        end
        else if name = 'NEG' then
        begin
          a := Stack[SP - 1];
          if a.Kind <> vkInt then
            RaiseStr('TYPE');
          Push1(IntVal(Red(-a.I)));
        end
        else if name = 'EQ' then
        begin
          a := Stack[SP - 2];
          b := Stack[SP - 1];
          if (a.Kind = b.Kind) and (((a.Kind = vkInt) and (a.I = b.I)) or ((a.Kind = vkStr) and (a.S = b.S))) then
            Push1(IntVal(1))
          else
            Push1(IntVal(0));
        end
        else if name = 'LT' then
        begin
          a := Stack[SP - 2];
          b := Stack[SP - 1];
          if a.Kind <> b.Kind then
            RaiseStr('TYPE');
          if a.Kind = vkInt then
            ok := a.I < b.I
          else
            ok := CompareBytes(a.S, b.S) < 0;
          if ok then
            Push1(IntVal(1))
          else
            Push1(IntVal(0));
        end
        else if name = 'JMP' then
          newpc := BranchTarget(nxt, arg, newFar)
        else if (name = 'JZ') or (name = 'JNZ') then
        begin
          v := Stack[SP - 1];
          if v.Kind <> vkInt then
            RaiseStr('TYPE');
          if (v.I = 0) = (name = 'JZ') then
            newpc := BranchTarget(nxt, arg, newFar);
        end
        else if name = 'CALL' then
        begin
          if FP >= DLim then
            RaiseStr('DEPTH');
          cost := 1 + Funcs[uarg].V;
        end
        else if name = 'THROW' then
          raise ERaise.Make(Stack[SP - 1])
        else if name = 'CAT' then
        begin
          txt := AsText(Stack[SP - 2]) + AsText(Stack[SP - 1]);
          if Length(txt) > LLim then
            RaiseStr('LIMIT');
          Push1(StrVal(txt));
          cost := 1 + Length(txt) div 8;
        end
        else if name = 'LEN' then
        begin
          a := Stack[SP - 1];
          if a.Kind <> vkStr then
            RaiseStr('TYPE');
          Push1(IntVal(Red(Length(a.S))));
        end
        else if name = 'SLICE' then
        begin
          x := Stack[SP - 3];
          a := Stack[SP - 2];
          c := Stack[SP - 1];
          if (x.Kind <> vkStr) or (a.Kind <> vkInt) or (c.Kind <> vkInt) then
            RaiseStr('TYPE');
          n := Length(x.S);
          s := a.I;
          if s < 0 then
            s := s + n;
          if s < 0 then
            s := 0;
          if s > n then
            s := n;
          if c.I < 0 then
            RaiseStr('RANGE');
          if c.I < n - s then
            r := c.I
          else
            r := n - s;
          txt := Copy(x.S, s + 1, r);
          Push1(StrVal(txt));
          cost := 1 + Length(txt) div 8;
        end
        else if name = 'BYTE' then
        begin
          x := Stack[SP - 2];
          a := Stack[SP - 1];
          if (x.Kind <> vkStr) or (a.Kind <> vkInt) then
            RaiseStr('TYPE');
          if (a.I < 0) or (a.I >= Length(x.S)) then
            RaiseStr('RANGE');
          Push1(IntVal(Red(Byte(x.S[a.I + 1]))));
        end
        else if name = 'CHR' then
        begin
          a := Stack[SP - 1];
          if a.Kind <> vkInt then
            RaiseStr('TYPE');
          if (a.I < 0) or (a.I > 255) then
            RaiseStr('RANGE');
          if LLim < 1 then
            RaiseStr('LIMIT');
          Push1(StrVal(Chr(a.I)));
        end
        else if name = 'STR' then
        begin
          a := Stack[SP - 1];
          if a.Kind <> vkInt then
            RaiseStr('TYPE');
          txt := DecText(a.I);
          if Length(txt) > LLim then
            RaiseStr('LIMIT');
          Push1(StrVal(txt));
          cost := 1 + Length(txt) div 8;
        end
        else if name = 'NUM' then
        begin
          a := Stack[SP - 1];
          if a.Kind <> vkStr then
            RaiseStr('TYPE');
          t := a.S;
          neg := (Length(t) > 0) and (t[1] = '-');
          if neg then
            Delete(t, 1, 1);
          if Length(t) = 0 then
            RaiseStr('PARSE');
          ua := 0;
          for i := 1 to Length(t) do
          begin
            if (t[i] < '0') or (t[i] > '9') then
              RaiseStr('PARSE');
            ua := ua * 10 + QWord(Ord(t[i]) - Ord('0'));   { wraps mod 2^64, exact mod 2^W }
          end;
          if neg then
            ua := QWord(0) - ua;
          Push1(IntVal(Red(Int64(ua))));
        end
        else if name = 'PRINT' then
        begin
          printed := Render(Stack[SP - 1]);
          hasPrint := True;
          cost := 1 + Length(printed) div 8;
        end;
      except
        on e: ERaise do
        begin
          raised := True;
          rv := e.Value;
          cost := 1;
          npush := 0;
        end;
      end;

      { 5. stack room }
      if (not raised) and (SP - pops + npush > SLim) then
        raise EFault.Make('STACK', at);

      { 6. ticks }
      if Used + cost > F then
        raise EFault.Make('FUEL', at);
      Used := Used + cost;

      { 7. effect }
      if raised then
      begin
        if name <> 'CALL' then
          SP := SP - pops;   { a raising instruction has taken its operands }
        if HP = 0 then
        begin
          Emit('-- error ' + Render(rv) + ' at=' + IntToStr(at) + ' ticks=' + IntToStr(Used));
          Exit;
        end;
        h := Handlers[HP - 1];
        Dec(HP);
        FP := h.Frame + 1;
        if SP > h.Depth then
          SP := h.Depth;
        if SP >= SLim then
          raise EFault.Make('STACK', at);
        Stack[SP] := rv;
        Inc(SP);
        pc := h.Target;
        pcFar := h.Far;
        Continue;
      end;
      if name = 'HALT' then
      begin
        Emit('-- halt ticks=' + IntToStr(Used) + ' stack=' + IntToStr(SP));
        Exit;
      end;
      if name = 'STORE' then
        Frames[FP - 1].Slots[uarg] := Stack[SP - 1];
      if name = 'CALL' then
      begin
        PushFrame(Integer(uarg), SP - Funcs[uarg].P, nxt);
        for i := 0 to Funcs[uarg].P - 1 do
          Frames[FP - 1].Slots[i] := Stack[SP - Funcs[uarg].P + i];
        SP := SP - Funcs[uarg].P;
        pc := Int64(Funcs[uarg].Offset);
        pcFar := False;
        Continue;
      end;
      if name = 'RET' then
      begin
        v := Stack[SP - 1];
        SP := Frames[FP - 1].Base;
        while (HP > 0) and (Handlers[HP - 1].Frame = FP - 1) do
          Dec(HP);
        pc := Frames[FP - 1].Ret;
        pcFar := False;
        Dec(FP);
        Stack[SP] := v;
        Inc(SP);
        Continue;
      end;
      if name = 'TRY' then
      begin
        if HP >= Length(Handlers) then
          SetLength(Handlers, HP * 2 + 8);
        Handlers[HP].Target := BranchTarget(nxt, arg, Handlers[HP].Far);
        Handlers[HP].Depth := SP;
        Handlers[HP].Frame := FP - 1;
        Inc(HP);
      end;
      if name = 'ENDTRY' then
        Dec(HP);
      SP := SP - pops;
      for i := 0 to npush - 1 do
      begin
        Stack[SP] := pushes[i];
        Inc(SP);
      end;
      if hasPrint then
        Emit(printed);
      pc := newpc;
      pcFar := newFar;
    except
      on e: EFault do
      begin
        Emit('-- fault ' + e.Kind + ' at=' + AddrText(e.At, pcFar) + ' ticks=' + IntToStr(Used));
        Exit;
      end;
    end;
  end;
end;

begin
  OutBuf := '';
  if ParamCount < 1 then
  begin
    WriteLn(StdErr, 'usage: fvm IMAGE');
    Halt(2);
  end;
  try
    LoadImage(ParamStr(1));
  except
    on EBadImage do
    begin
      Write('-- bad image'#10);
      Halt(0);
    end;
  end;
  Run;
  Write(OutBuf);
end.
