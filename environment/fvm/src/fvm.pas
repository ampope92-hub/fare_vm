program fvm;
{ FVM-2 interpreter for the back-office replay. Usage: fvm IMAGE }

{$mode objfpc}{$H+}

uses
  SysUtils;

begin
  if ParamCount < 1 then
  begin
    WriteLn(StdErr, 'usage: fvm IMAGE');
    Halt(2);
  end;
end.
