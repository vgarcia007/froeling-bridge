#!/usr/bin/env python3
"""Verify documentation vectors using extracted p4d C++ functions, offline.

No serial device or database is opened. Original functions retain their upstream
copyright/license (reference/linux-p4d/LICENSE, GPLv2). Stubs only supply memory IO.
"""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / 'reference/linux-p4d'
PIN = '4d1176c4a9081893e4c2cc27a535bb2bc4737d0a'


def extract(path, signature):
    source = path.read_text()
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    revision = subprocess.check_output(['git', '-C', str(REF), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        raise SystemExit(f'Reference revision differs: {revision}; expected {PIN}')
    vectors = json.loads((ROOT / 'docs/protocol-vectors.json').read_text())
    support = r'''
#include <arpa/inet.h>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <iomanip>
using byte = unsigned char;
using word = unsigned short;
using sword = signed short;
const int success=0, done=0, fail=-1, yes=1, no=0, TB=1, eloAlways=0;
template<class... T> void tell(T...) {}
int isEmpty(const char* t) { return !t || !*t; }
struct Serial {
  enum { wrnTimeout=-100 };
  std::vector<byte> input;
  size_t pos=0;
  bool isOpen() { return true; }
  int look(byte& b, int) {
    if (pos == input.size()) return wrnTimeout;
    b=input[pos++]; return success;
  }
};
#pragma pack(push,1)
struct Header { word id; word size; byte command; };
#pragma pack(pop)
byte crc(const byte*,int);
struct P4Request {
  enum {sizeMaxRequest=260, sizeAddress=2, sizeCrc=1, sizeId=2,
        posSize=2, commId=0x02FD, wrnTimeout=-996};
  Header header{};
  word addresses[127]{};
  int addressCount=0;
  byte bytes[254]{};
  int byteCount=0;
  char* text=nullptr;
  byte buffer[1024]{}, decoded[1024]{};
  int sizeBufferContent=0, sizeDecodedContent=0;
  Serial* s;
  explicit P4Request(Serial* serial):s(serial) {}
  void clear() { header={}; sizeBufferContent=0; sizeDecodedContent=0; }
  int prepareRequest();
  int readByte(byte&,int decode=yes,int tms=1000);
  int readWord(word&,int decode=yes,int tms=1000);
  int readWord(sword&,int decode=yes,int tms=1000);
  int readHeader(int tms=2000);
};
std::vector<byte> unhex(const std::string& s) {
  std::istringstream in(s); unsigned v; std::vector<byte> out;
  while(in>>std::hex>>v) out.push_back(v);
  return out;
}
std::string hex(const byte* data,size_t n) {
  std::ostringstream out;
  for(size_t i=0;i<n;i++) {
    if(i) out<<' ';
    out<<std::hex<<std::uppercase<<std::setw(2)<<std::setfill('0')<<(int)data[i];
  }
  return out.str();
}
int main(int argc,char** argv) {
  if(argc!=4) return 2;
  unsigned command=std::stoul(argv[1],nullptr,16);
  auto payload=unhex(argv[2]); auto expected=unhex(argv[3]);
  Serial serial; P4Request req(&serial);
  req.header.id=htons(P4Request::commId); req.header.command=command;
  req.byteCount=payload.size();
  std::copy(payload.begin(),payload.end(),req.bytes);
  int size=req.prepareRequest();
  if(hex(req.buffer,size)!=hex(expected.data(),expected.size())) return 3;
  serial.input=expected;
  if(req.readHeader()!=success) return 4;
  if(req.header.id!=P4Request::commId || req.header.size!=payload.size()+1 ||
     req.header.command!=command) return 5;
  for(auto want:payload) { byte got; if(req.readByte(got)!=success || got!=want) return 6; }
  byte checksum;
  if(req.readByte(checksum)!=success || serial.pos!=expected.size()) return 7;
  if(crc(req.decoded,req.sizeDecodedContent-1)!=checksum) return 8;
  // Exercise both original readWord overloads on every 16-bit bit pattern.
  for(unsigned value=0;value<65536;value++) {
    Serial words;
    for(byte b:{byte(value>>8),byte(value)}) {
      if(b==2 || b==0x2b || b==0xfe) { words.input.push_back(b); words.input.push_back(0); }
      else if(b==0x11 || b==0x13) { words.input.push_back(0xfe); words.input.push_back(b+1); }
      else words.input.push_back(b);
    }
    P4Request unsignedReq(&words); word u;
    if(unsignedReq.readWord(u)!=success || u!=value) return 9;
    words.pos=0; P4Request signedReq(&words); sword s;
    int want=value<32768 ? value : int(value)-65536;
    if(signedReq.readWord(s)!=success || s!=want) return 10;
  }
  // Invalid escape and truncated escape must fail in the original decoder.
  for(auto input:{std::vector<byte>{2,1},std::vector<byte>{0x2b,1},
                  std::vector<byte>{0xfe,1},std::vector<byte>{0xfe}}) {
    Serial bad; bad.input=input; P4Request decoder(&bad); byte got;
    if(decoder.readByte(got)==success) return 11;
  }
  std::cout<<hex(expected.data(),expected.size())<<'\n';
}
'''
    functions = [extract(REF / 'lib/common.c', 'byte crc(')]
    for signature in ['int P4Request::prepareRequest()', 'int P4Request::readByte(',
                      'int P4Request::readWord(word&', 'int P4Request::readWord(sword&',
                      'int P4Request::readHeader(']:
        functions.append(extract(REF / 'p4io.c', signature))
    # Definitions omit defaults, declarations above provide them, as upstream does.
    with tempfile.TemporaryDirectory(prefix='p4d-doc-check-') as folder:
        source = Path(folder) / 'check.cpp'
        binary = Path(folder) / 'check'
        source.write_text(support + '\n' + '\n'.join(functions))
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', str(source), '-o', str(binary)], check=True)
        for vector in vectors:
            result = subprocess.run([str(binary), vector['command'], vector['payload'], vector['wire']],
                                    text=True, capture_output=True)
            if result.returncode:
                raise SystemExit(f"FAIL {vector['name']}: harness exit {result.returncode}\n{result.stderr}")
            print(f"PASS {vector['name']}: {result.stdout.strip()}")
    print(f'{len(vectors)} synthetic vectors verified; all 65536 signed/unsigned words and invalid escapes checked.')
    print('No hardware or database verification; no parameter write sequence was executed.')


if __name__ == '__main__':
    main()
