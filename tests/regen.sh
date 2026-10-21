set -eu
for f in tests/ok/*.asm; do
  b="${f%.asm}"
  riscv64-unknown-elf-as -march=rv32i -mabi=ilp32 -mno-relax "$f" -o "$b.o"
  riscv64-unknown-elf-ld -m elf32lriscv -Ttext=0 -Tdata=0x10000000 -e 0 "$b.o" -o "$b.elf"
  riscv64-unknown-elf-objcopy -O binary -j .text "$b.elf" "$b.bin"
  od -An -v -tx4 -w4 "$b.bin" | tr -d ' ' > "$b.hex"
  riscv64-unknown-elf-objcopy -O binary -j .data "$b.elf" "$b.dbin"
  od -An -v -tx4 -w4 "$b.dbin" | tr -d ' ' > "$b.data.hex"
  [ -s "$b.data.hex" ] || rm -f "$b.data.hex"
  rm -f "$b.o" "$b.elf" "$b.bin" "$b.dbin"
done
